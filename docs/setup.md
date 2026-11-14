# Setup

## Requirements

- Python 3.11 or newer
- No database server needed for local development (SQLite is the default)
- No API keys — the synthesis engine is free and keyless

## Local install

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-21-nawa.git
cd day-21-nawa

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
```

Then set a real signing key. The app will start with the placeholder, but every
token it issues is forgeable until you change it:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env
```

Every variable is documented in `.env.example`. The ones that matter:

| Variable | Default | What it does |
|---|---|---|
| `SECRET_KEY` | placeholder | Signs session and audio tokens. **Change it.** |
| `DATABASE_URL` | `sqlite:///./nawa.db` | Swap for PostgreSQL in production |
| `DAILY_GENERATION_LIMIT` | `40` | Generations per user per day |
| `MAX_TEXT_CHARS` | `4000` | Longest accepted script |
| `SYNTH_CONCURRENCY` | `3` | Parallel synthesis calls |
| `AUDIO_TOKEN_MINUTES` | `60` | How long an audio link lives |

## Seed the demo data

```bash
python -m app.seed
```

This creates `demo@nawa.app` / `nawademo2026` and synthesises three real
generations so the library is not empty on first load. It takes about 15
seconds because it actually calls the synthesiser.

## Run

```bash
uvicorn app.main:app --reload
```

- App: <http://127.0.0.1:8000>
- API docs: <http://127.0.0.1:8000/docs> (development only)

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Brings up the app and PostgreSQL. The app waits for the database health check
before starting, so the first boot takes a few seconds longer.

To run the seed inside the container:

```bash
docker compose exec app python -m app.seed
```

## Tests

```bash
pytest -q
```

120 tests, about 7 seconds, no network access required — synthesis is patched
out in the test fixtures.

## Lint and format

```bash
ruff check .
ruff format .
```

## Troubleshooting

**`ModuleNotFoundError: No module named 'app'`**
Run commands from the repository root, or install with `pip install -e .`.

**Synthesis fails with a connection error**
edge-tts calls Microsoft's servers. Check outbound HTTPS. The rest of the app
works without it — the preview endpoint and the normaliser are entirely local.

**`422 Unprocessable Entity` on register**
The password needs at least 10 characters and at least one digit. The email
must be valid.

**Audio link returns 401**
Audio links expire after `AUDIO_TOKEN_MINUTES`. Reload the generation to get a
fresh one.

**`sqlite3.OperationalError: database is locked`**
Two processes writing to the same SQLite file. Use PostgreSQL, or run a single
worker.
