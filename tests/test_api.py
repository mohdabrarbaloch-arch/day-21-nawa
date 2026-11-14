"""Auth, security boundaries and the generation API.

Synthesis is patched out: these tests are about the HTTP contract, not about
whether Microsoft's servers are up.
"""

import pytest

from app.models import GenerationStatus
from app.services import synth


@pytest.fixture(autouse=True)
def _fake_synthesis(monkeypatch):
    """Replace the network call with a deterministic fake."""

    async def fake_chunk(text, *, voice, rate=1.0, pitch=0.0, volume=1.0):
        # 100 bytes per character, and one word timing per word.
        words = [
            synth.WordTiming(start_ms=i * 200, end_ms=i * 200 + 180, text=w)
            for i, w in enumerate(text.split())
        ]
        return b"\xff\xf3" + b"\x00" * (len(text) * 100), words

    async def fake_synthesize(chunks, *, voice, rate=1.0, pitch=0.0, volume=1.0, concurrency=3):
        out = []
        for i, text in enumerate(chunks):
            audio, words = await fake_chunk(
                text, voice=voice, rate=rate, pitch=pitch, volume=volume
            )
            out.append(
                synth.ChunkAudio(
                    index=i,
                    audio=audio,
                    duration_ms=len(text) * 100,
                    words=words,
                )
            )
        return out

    monkeypatch.setattr(synth, "synthesize", fake_synthesize)
    monkeypatch.setattr(synth, "synthesize_chunk", fake_chunk)
    monkeypatch.setattr(synth, "mp3_duration_ms", lambda data: len(data) // 100)


class TestRegistration:
    def test_register_returns_token(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "goodpass1234"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["access_token"]
        assert body["user"]["email"] == "new@example.com"

    def test_duplicate_email_conflicts(self, client):
        payload = {"email": "dup@example.com", "password": "goodpass1234"}
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409

    def test_short_password_rejected(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "s@example.com", "password": "short"}
        )
        assert response.status_code == 422

    def test_password_needs_a_digit(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "n@example.com", "password": "onlyletters"}
        )
        assert response.status_code == 422

    def test_invalid_email_rejected(self, client):
        response = client.post(
            "/api/auth/register", json={"email": "not-an-email", "password": "goodpass1234"}
        )
        assert response.status_code == 422

    def test_email_is_normalised_to_lowercase(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "MiXeD@Example.COM", "password": "goodpass1234"},
        )
        assert response.json()["user"]["email"] == "mixed@example.com"


class TestLogin:
    def test_login_succeeds(self, client, user_factory):
        token, user = user_factory()
        response = client.post(
            "/api/auth/login", json={"email": user["email"], "password": "goodpass1234"}
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_wrong_password_is_401(self, client, user_factory):
        _, user = user_factory()
        response = client.post(
            "/api/auth/login", json={"email": user["email"], "password": "wrongpass1234"}
        )
        assert response.status_code == 401

    def test_unknown_email_same_message(self, client):
        response = client.post(
            "/api/auth/login", json={"email": "ghost@example.com", "password": "goodpass1234"}
        )
        assert response.status_code == 401
        # Identical wording to a wrong password: no account enumeration.
        assert response.json()["detail"] == "Email or password is incorrect"

    def test_me_requires_token(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_returns_user(self, client, auth_headers):
        response = client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert "@example.com" in response.json()["email"]

    def test_garbage_token_rejected(self, client):
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == 401


class TestVoices:
    def test_catalog_lists_languages(self, client):
        response = client.get("/api/voices")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] > 10
        assert any(g["language"] == "Urdu" for g in body["languages"])

    def test_urdu_voices_present(self, client):
        body = client.get("/api/voices").json()
        urdu = next(g for g in body["languages"] if g["language"] == "Urdu")
        assert urdu["count"] >= 2


class TestPreview:
    def test_preview_rewrites_numbers(self, client):
        response = client.post("/api/preview", json={"text": "Rs 1,50,000"})
        assert response.status_code == 200
        body = response.json()
        assert body["after"] == "one lakh fifty thousand rupees"
        assert body["before"] == "Rs 1,50,000"

    def test_preview_can_be_disabled(self, client):
        response = client.post("/api/preview", json={"text": "Rs 500", "normalise": False})
        assert response.json()["after"] == "Rs 500"

    def test_preview_rejects_unknown_voice(self, client):
        response = client.post("/api/preview", json={"text": "hi", "voice": "xx-Nope"})
        assert response.status_code == 422


class TestGenerationLifecycle:
    def test_create_returns_202(self, client, auth_headers):
        response = client.post(
            "/api/generations", json={"text": "Hello there friend."}, headers=auth_headers
        )
        assert response.status_code == 202
        assert response.json()["status"] in {"queued", "processing", "completed"}

    def test_requires_auth(self, client):
        assert client.post("/api/generations", json={"text": "hi"}).status_code == 401

    def test_blank_text_rejected(self, client, auth_headers):
        response = client.post("/api/generations", json={"text": "   "}, headers=auth_headers)
        assert response.status_code == 422

    def test_unknown_voice_rejected(self, client, auth_headers):
        response = client.post(
            "/api/generations",
            json={"text": "hello", "voice": "xx-FAKE"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_rate_bounds_enforced(self, client, auth_headers):
        response = client.post(
            "/api/generations",
            json={"text": "hello", "rate": 9.0},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_completes_and_stores_audio(self, client, auth_headers):
        created = client.post(
            "/api/generations",
            json={"text": "One sentence here. Another sentence follows."},
            headers=auth_headers,
        ).json()

        detail = client.get(f"/api/generations/{created['id']}", headers=auth_headers).json()
        assert detail["status"] == GenerationStatus.COMPLETED
        assert detail["duration_ms"] > 0
        assert detail["audio_url"]

    def test_audio_requires_token(self, client, auth_headers):
        created = client.post(
            "/api/generations", json={"text": "Audio test here."}, headers=auth_headers
        ).json()
        assert client.get(f"/api/generations/{created['id']}/audio").status_code == 401

    def test_audio_served_with_capability_token(self, client, auth_headers):
        created = client.post(
            "/api/generations", json={"text": "Audio test here."}, headers=auth_headers
        ).json()
        detail = client.get(f"/api/generations/{created['id']}", headers=auth_headers).json()
        response = client.get(detail["audio_url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert len(response.content) > 0

    def test_other_users_generation_is_404(self, client, user_factory):
        token_a, _ = user_factory()
        token_b, _ = user_factory()
        created = client.post(
            "/api/generations",
            json={"text": "Private words here."},
            headers={"Authorization": f"Bearer {token_a}"},
        ).json()

        response = client.get(
            f"/api/generations/{created['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        # 404, not 403: the caller learns nothing about what exists.
        assert response.status_code == 404

    def test_delete_removes_generation(self, client, auth_headers):
        created = client.post(
            "/api/generations", json={"text": "Delete me please."}, headers=auth_headers
        ).json()
        assert (
            client.delete(f"/api/generations/{created['id']}", headers=auth_headers).status_code
            == 204
        )
        assert (
            client.get(f"/api/generations/{created['id']}", headers=auth_headers).status_code == 404
        )

    def test_library_lists_only_own(self, client, user_factory):
        token_a, _ = user_factory()
        token_b, _ = user_factory()
        client.post(
            "/api/generations",
            json={"text": "Mine only."},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        listing = client.get(
            "/api/generations", headers={"Authorization": f"Bearer {token_b}"}
        ).json()
        assert listing["total"] == 0

    def test_usage_reports_limit(self, client, auth_headers):
        body = client.get("/api/generations/usage", headers=auth_headers).json()
        assert body["limit"] > 0
        assert body["remaining"] == body["limit"] - body["used_today"]


class TestPronunciations:
    def test_create_and_list(self, client, auth_headers):
        created = client.post(
            "/api/pronunciations",
            json={"written": "Nawa", "spoken": "nuh-waa"},
            headers=auth_headers,
        )
        assert created.status_code == 201
        rows = client.get("/api/pronunciations", headers=auth_headers).json()
        assert any(r["written"] == "Nawa" for r in rows)

    def test_duplicate_conflicts(self, client, auth_headers):
        payload = {"written": "Baloch", "spoken": "buh-loch"}
        assert (
            client.post("/api/pronunciations", json=payload, headers=auth_headers).status_code
            == 201
        )
        assert (
            client.post("/api/pronunciations", json=payload, headers=auth_headers).status_code
            == 409
        )

    def test_blank_rejected(self, client, auth_headers):
        response = client.post(
            "/api/pronunciations",
            json={"written": "  ", "spoken": "x"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_delete(self, client, auth_headers):
        created = client.post(
            "/api/pronunciations",
            json={"written": "Temp", "spoken": "temp"},
            headers=auth_headers,
        ).json()
        assert (
            client.delete(f"/api/pronunciations/{created['id']}", headers=auth_headers).status_code
            == 204
        )

    def test_lexicon_applied_to_generation(self, client, auth_headers):
        client.post(
            "/api/pronunciations",
            json={"written": "Nawa", "spoken": "nuh-waa"},
            headers=auth_headers,
        )
        created = client.post(
            "/api/generations", json={"text": "Nawa is a studio."}, headers=auth_headers
        ).json()
        detail = client.get(f"/api/generations/{created['id']}", headers=auth_headers).json()
        assert "nuh-waa" in detail["normalised_text"]


class TestSecurityHeaders:
    def test_headers_present(self, client):
        response = client.get("/api/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "content-security-policy" in response.headers

    def test_health_reports_ok(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["voices"] > 0
