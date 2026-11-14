# Architecture

## The problem this solves

A synthesiser reads what you give it. Give it `Rs 1,50,000` and it says
"R S one comma five zero comma zero zero zero" — or skips it, or spells it out
digit by digit. Give it a 900-word blob and it either truncates or rushes
through the last third.

Both failures are fixable before the audio is ever requested. That is what this
project is: a text pipeline that turns written text into speakable text, and a
synthesis layer that speaks it in pieces small enough to sound human.

## System diagram

```
                    ┌──────────────────────────────────────────┐
   browser          │  app/static/  (vanilla JS, no build step) │
   ────────         │  index.html · styles.css · app.js         │
                    └───────────────┬──────────────────────────┘
                                    │  fetch, JSON + JWT
                                    ▼
                    ┌──────────────────────────────────────────┐
                    │  FastAPI  (app/main.py)                  │
                    │  middleware: CORS · security headers ·   │
                    │              rate limit (slowapi)        │
                    └───────────────┬──────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
  routers/auth.py           routers/voices.py          routers/generations.py
  register · login · me     catalog · preview          create · poll · audio
        │                           │                           │
        │                           │                    ┌──────┴──────┐
        │                           │                    ▼             ▼
        │                           │            services/        services/
        │                           │            normaliser.py    chunker.py
        │                           │                    │             │
        │                           │                    └──────┬──────┘
        │                           │                           ▼
        │                           │                   services/synth.py
        │                           │                   edge-tts → MP3
        │                           │                           │
        ▼                           ▼                           ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  SQLAlchemy 2.0  →  SQLite (default)  /  PostgreSQL (compose)    │
  │  users · generations · chunks · pronunciations                   │
  └──────────────────────────────────────────────────────────────────┘
```

## Data flow for one generation

1. **POST /api/generations** with `{text, voice, rate, pitch, volume}`.
2. The handler validates the voice against the catalog, checks the daily quota,
   and writes a `Generation` row with status `queued`. It returns **202** with
   the id — it does not wait for audio.
3. A background task picks the row up:
   - `normaliser.normalise()` rewrites numbers, currency, dates, times,
     ordinals, phone numbers and abbreviations into words.
   - The user's pronunciation overrides are applied on top.
   - `chunker.split()` cuts the result into speakable pieces.
   - `synth.synthesize()` calls edge-tts for each piece, three at a time, and
     collects the MP3 bytes plus word-level timings.
   - The pieces are concatenated, timings are offset by each piece's real
     duration, and everything is written back.
4. The browser polls **GET /api/generations/{id}** every 2.5s until status is
   `completed` or `failed`.
5. **GET /api/generations/{id}/audio?t=…** streams the MP3.

## Why audio lives in the database

A generation is at most a few megabytes. Storing it as a `LargeBinary` column
means the app has no filesystem dependency at all — it runs identically on a
laptop, in Docker, and on a read-only serverless filesystem. The trade is that
large libraries would bloat the database; past a few thousand generations per
user this should move to object storage with a signed URL, and the `audio`
column becomes a key.

## Why the normaliser is the product

Every TTS wrapper on the market passes text straight through. The result is
that the same sentence sounds fine in English prose and broken the moment it
contains a number, which is most business content.

The normaliser is a sequence of ordered rules, each with a specific reason:

| Order | Rule | Why it must run here |
|---|---|---|
| 1 | Protect URLs, emails | Later rules would destroy them |
| 2 | Currency | Must see `Rs 1,50,000` before the integer rule splits it |
| 3 | Magnitudes | `$2.5 million` must become "two point five million dollars", not "two point five dollars million" |
| 4 | Dates | `15/11/2026` before the integer rule reads the parts |
| 5 | Times | `09:30` before the integer rule |
| 6 | Decimals, percent | Before integers, so `12.5` is not "twelve point five" twice |
| 7 | Ordinals | `3rd` before integers |
| 8 | Phone numbers | Digit-by-digit, before integers |
| 9 | Abbreviations | `Mr.` before sentence handling |
| 10 | Integers | Last, on whatever is left |
| 11 | Restore protected spans | URLs and invalid dates come back untouched |

Two details that took real debugging:

- **South Asian grouping.** `1,50,000` is lakh notation, not a malformed
  Western number. The rule detects the 2-digit group and reads it as
  "one lakh fifty thousand". `1,500,000` stays Western.
- **Year vs quantity.** `in 2026` is a year ("twenty twenty-six"); `1000 days`
  is a count ("one thousand days"). A four-digit number is only read as a year
  when the preceding word introduces one, or when it ends the sentence.

## Why chunking matters

edge-tts synthesises per request. A 4000-character request produces audio with
flat prosody — the model has no room to breathe. Splitting on sentence
boundaries and synthesising each piece separately gives natural pauses, and
lets a single bad paragraph be regenerated without redoing the whole file.

The chunker prefers sentence ends, falls back to clause breaks, and only splits
mid-clause when one sentence exceeds the limit. A too-short tail is merged into
its neighbour — but only if the merge still fits the limit, which is a bug I
hit and fixed (a 79-char chunk plus a 39-char tail became 119).

## Word timings

edge-tts emits `WordBoundary` events with offsets in 100-nanosecond ticks.
Those are converted to milliseconds and offset by the cumulative duration of
all preceding chunks. The result is a monotonic list of `{start_ms, end_ms,
text}` that the UI uses to highlight the word being spoken.

This is why the player can highlight in sync without any client-side audio
analysis.

## Security model

- **Passwords**: bcrypt, cost 12.
- **Session**: JWT, HS256, 7-day expiry, `sub` = user id.
- **Audio access**: a *separate* short-lived token scoped to one generation id.
  The `<audio>` element cannot send an `Authorization` header, so the audio URL
  carries a capability token instead. It is signed with the same secret but
  carries `scope: "audio"` and the generation id, so it cannot be replayed
  against another generation or used as a session token.
- **Ownership**: another user's generation returns **404**, not 403. A 403
  confirms the record exists; a 404 does not.
- **Rate limits**: 30/min on generation, 10/min on auth, 40/min on preview.
- **Headers**: `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`, and a CSP that allows only self.
- **Input**: every field bounded by Pydantic. Text capped at 4000 characters,
  rate 0.5–2.0, pitch −20 to +20, volume 0.1–2.0.

## Scaling notes

| Concern | Now | Next step |
|---|---|---|
| Synthesis | in-process background task | Celery/RQ worker; the task is already a pure function of (text, voice, settings) |
| Rate limiting | in-process memory | Redis backend for slowapi — required before running more than one worker |
| Audio storage | DB column | S3/R2 with signed URLs |
| Database | SQLite | PostgreSQL (compose file already configured); add Alembic before the first real migration |
| Caching | none | Hash (normalised text + voice + settings) → reuse audio; identical requests are common in product demos |
| Quota | per-user daily count | Redis counter with TTL |

## What this deliberately does not do

- **No voice cloning.** That needs a model and a GPU; edge-tts gives 22 curated
  neural voices instead. The catalog is a data structure, so swapping in a
  cloning backend means implementing one function.
- **No streaming playback.** Audio is assembled then served. Streaming would
  need chunked transfer and a different player.
- **No SSML editor.** Rate/pitch/volume cover the common cases; raw SSML is a
  power feature that would need its own validation layer.
