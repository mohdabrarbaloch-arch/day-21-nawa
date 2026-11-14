# Usage

## The studio

Sign in, paste a script, pick a voice, press **Speak it**.

The left panel is where you write. The right panel is the player and the
library.

### The rewrite preview

As you type, the app asks the server what the text will become. The preview
appears under the text box:

```
You wrote
  On 15/11/2026 we raised Rs 1,50,000 from 3 investors.

It will say
  On the fifteenth of November twenty twenty-six we raised one lakh fifty
  thousand rupees from three investors.
```

This costs nothing — it never calls the synthesiser. It exists so you can catch
a bad rewrite before you spend a generation.

If a rewrite is wrong, turn off **Rewrite numbers into words** and the text goes
through untouched.

### Voices

22 voices, grouped by language. Each shows the accent and gender:

- **English** — American, British, Indian, Australian, Irish
- **Urdu** — Asad, Uzma (Pakistan)
- **Hindi** — Swara, Madhur
- **Arabic, Spanish, French, German, Chinese, Japanese**

The voice list is a data structure in `app/voices.py`. Adding one is a single
line.

### Rate, pitch, volume

| Control | Range | What it does |
|---|---|---|
| Speed | 0.5× – 2.0× | Overall speaking rate |
| Pitch | −20 to +20 st | Semitones. Small moves; ±5 is a lot |
| Volume | 10% – 200% | Output gain |

These are applied per chunk, so they stay consistent across a long script.

### Word highlighting

While audio plays, the word being spoken is highlighted in the transcript. This
uses word-level timings returned by the synthesiser, not client-side audio
analysis — so it stays accurate even when you seek.

### Regenerating one paragraph

If one line came out wrong, open the generation and regenerate just that chunk.
The rest of the audio is untouched. This is the main reason the text is chunked
at all.

### Pronunciation overrides

The **Voice** tab holds a per-user dictionary:

| Written | Spoken |
|---|---|
| Nawa | nuh-waa |
| Baloch | buh-loch |

Overrides are applied after normalisation and before chunking, so they affect
every future generation. Matching is case-insensitive and whole-word only —
"Nawa" will not touch "Nawaz".

This is the fix for the thing every TTS gets wrong: names.

### Library

Every generation is saved with its title, voice, duration and status. Click one
to load it into the player. Delete removes the audio too.

The quota pill in the header shows generations left today.

## Common workflows

### A product demo voiceover

1. Paste the script.
2. Check the preview — make sure prices read correctly.
3. Pick a voice that matches the brand.
4. Generate, listen, regenerate any line that sounds off.
5. Download the MP3.

### A lecture note

1. Paste the notes.
2. Turn **Rewrite numbers into words** on — dates and figures are the usual
   failure point.
3. Use a slower rate (0.9×) for anything technical.

### Urdu content

1. Pick Asad or Uzma.
2. Write in Urdu script. The normaliser leaves non-Latin text alone.
3. English loanwords that come out wrong go in the pronunciation dictionary.

## API usage

See [api.md](api.md) for the full reference. The short version:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"goodpass1234"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# Create — returns 202 immediately
ID=$(curl -s -X POST localhost:8000/api/generations \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"We raised Rs 1,50,000.","voice":"en-US-AriaNeural"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

# Poll until completed
curl -s localhost:8000/api/generations/$ID -H "Authorization: Bearer $TOKEN"
```

The response includes `audio_url`, which already carries a short-lived token —
fetch it directly, no header needed.
