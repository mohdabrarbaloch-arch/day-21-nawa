# API reference

Base URL: `http://127.0.0.1:8000`

All request and response bodies are JSON. Authenticated endpoints expect:

```
Authorization: Bearer <access_token>
```

## Errors

Every error is `{"detail": "..."}`.

| Status | When |
|---|---|
| 400 | Malformed request |
| 401 | Missing, expired or invalid token |
| 404 | Not found, **or** not yours |
| 409 | Email or pronunciation already exists |
| 422 | Validation failed (field-level detail included) |
| 429 | Rate limit exceeded |
| 500 | Server error |

A 404 on someone else's resource is deliberate. A 403 would confirm the record
exists.

---

## Auth

### POST /api/auth/register

```json
{"email": "you@example.com", "password": "goodpass1234", "display_name": "Abrar"}
```

`display_name` is optional. Password needs 10+ characters and at least one
digit. Email is lowercased.

**201**

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "user": {"id": 1, "email": "you@example.com", "display_name": "Abrar", "created_at": "..."}
}
```

**409** if the email exists. **422** if validation fails.

### POST /api/auth/login

```json
{"email": "you@example.com", "password": "goodpass1234"}
```

**200** — same shape as register. **401** with `"Email or password is
incorrect"` for both a wrong password and an unknown email, so the endpoint
cannot be used to enumerate accounts.

### GET /api/auth/me

**200** — the current user.

---

## Voices

### GET /api/voices

Public. Returns the catalog grouped by language.

```json
{
  "total": 22,
  "languages": [
    {
      "language": "English",
      "count": 8,
      "voices": [
        {"id": "en-US-AriaNeural", "name": "Aria", "gender": "Female",
         "locale": "en-US", "accent": "American", "sample": "..."}
      ]
    }
  ]
}
```

### POST /api/preview

Public. Shows the rewrite without synthesising. Rate limited to 40/min.

```json
{"text": "We raised Rs 1,50,000 on 15/11/2026.", "voice": "en-US-AriaNeural", "normalise": true}
```

**200**

```json
{
  "before": "We raised Rs 1,50,000 on 15/11/2026.",
  "after": "We raised one lakh fifty thousand rupees on the fifteenth of November twenty twenty-six.",
  "chunks": 1,
  "estimated_seconds": 4.2
}
```

`normalise: false` returns the text unchanged. An unknown `voice` is **422**.

---

## Generations

### POST /api/generations

Rate limited to 30/min. Returns **202** — synthesis happens in the background.

```json
{
  "text": "Your script here.",
  "voice": "en-US-AriaNeural",
  "title": "Optional title",
  "rate": 1.0,
  "pitch": 0.0,
  "volume": 1.0
}
```

| Field | Bounds |
|---|---|
| `text` | 1 – 4000 characters, not blank |
| `voice` | must exist in the catalog |
| `rate` | 0.5 – 2.0 |
| `pitch` | −20 – 20 |
| `volume` | 0.1 – 2.0 |

**202**

```json
{"id": 12, "status": "queued", "title": "Optional title", "created_at": "..."}
```

**422** for a blank script, unknown voice, or out-of-range setting.
**429** when the daily quota is spent.

### GET /api/generations

Paginated library, newest first. Only your own.

Query: `limit` (1–100, default 20), `offset` (default 0).

```json
{
  "total": 3,
  "limit": 20,
  "offset": 0,
  "items": [
    {"id": 12, "title": "...", "status": "completed", "voice": "en-US-AriaNeural",
     "duration_ms": 9984, "created_at": "..."}
  ]
}
```

### GET /api/generations/{id}

Full detail, including the transcript and word timings.

```json
{
  "id": 12,
  "status": "completed",
  "title": "Final check",
  "voice": "en-US-AriaNeural",
  "duration_ms": 9984,
  "original_text": "On 15/11/2026 we raised Rs 1,50,000 from 3 investors.",
  "normalised_text": "On the fifteenth of November twenty twenty-six we raised one lakh fifty thousand rupees from three investors.",
  "audio_url": "/api/generations/12/audio?t=eyJhbGci...",
  "error": null,
  "chunks": [
    {"index": 0, "text": "...", "duration_ms": 9984, "status": "completed"}
  ],
  "words": [
    {"start_ms": 0, "end_ms": 180, "text": "On"},
    {"start_ms": 180, "end_ms": 420, "text": "the"}
  ]
}
```

`status` is one of `queued`, `processing`, `completed`, `failed`.

### GET /api/generations/{id}/audio

Streams `audio/mpeg`. Requires the `t` query parameter — a short-lived
capability token scoped to this generation. It is included in `audio_url`, so
you normally just fetch that.

**401** without a valid token. **404** if the generation is not yours.

### POST /api/generations/{id}/chunks/{index}/regenerate

Re-synthesises one chunk and rebuilds the audio. Use this when one paragraph
came out wrong.

**200** — the updated generation.

### DELETE /api/generations/{id}

**204**. Removes the generation and its audio.

### GET /api/generations/usage

```json
{"used_today": 3, "limit": 40, "remaining": 37}
```

---

## Pronunciations

Per-user overrides, applied after normalisation.

### GET /api/pronunciations

```json
[{"id": 1, "written": "Nawa", "spoken": "nuh-waa", "created_at": "..."}]
```

### POST /api/pronunciations

```json
{"written": "Nawa", "spoken": "nuh-waa"}
```

**201**. **409** if `written` already exists for this user. **422** if either
field is blank.

Matching is case-insensitive and whole-word. Longer keys win when two overlap.

### DELETE /api/pronunciations/{id}

**204**.

---

## Health

### GET /api/health

Public.

```json
{"status": "ok", "version": "1.0.0", "environment": "development", "voices": 22}
```

---

## Rate limits

| Endpoint | Limit |
|---|---|
| `POST /api/auth/register` | 10/min |
| `POST /api/auth/login` | 10/min |
| `POST /api/generations` | 30/min |
| `POST /api/preview` | 40/min |

Exceeding a limit returns **429**. Limits are per-process; behind multiple
workers they multiply, which is why Redis is on the list for production.
