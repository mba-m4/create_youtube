# Usage Guide (English)

English Phrase Video Pipeline — automatically turns English phrases (with Japanese translations)
into videos with narration and on-screen text.

This document covers only "how to run it." For design rationale and development rules, see
`README.md` / `CLAUDE.md` (both in Japanese). For the internal processing flow, see
`docs/pipeline_flow.md`.

## What this tool does

- For each "English phrase + Japanese translation" pulled from a CSV file or the phrase database,
  it generates:
  - narration audio (TTS)
  - an image (phrase + translation laid out on one image)
  - a video clip (image + audio)

  then concatenates all clips into a single MP4.
- It can also auto-generate English phrases from a theme using the Claude API.
- A browser-based Web UI lets you do all of the above without touching the CLI.

**Current scope**: this covers local video generation only. Scheduled runs (cron), Slack
notifications, and automatic YouTube uploads are not implemented yet (see the roadmap in
`README.md`).

## Prerequisites (setup)

### 1. System commands

- **ffmpeg** (required for combining clips into a video)
  ```bash
  # macOS
  brew install ffmpeg
  # Linux (Ubuntu, etc.)
  sudo apt-get install ffmpeg
  ```
- **A Japanese-capable font** (needed to render the Japanese translation on the image)
  - macOS ships with `AppleSDGothicNeo` by default, so no extra install is required.
    For nicer rendering, you can optionally run `brew install --cask font-noto-sans-cjk-jp`.
  - Linux needs `sudo apt-get install fonts-noto-cjk`.

### 2. Python packages

```bash
cd backend
uv sync
```

### 3. API keys (create `.env`)

Copy `backend/.env.example` to `backend/.env` and fill in the values.

| Variable | Purpose | Required? |
|---|---|---|
| `ELEVENLABS_API_KEY` | Audio generation (TTS) | Required for video generation |
| `ANTHROPIC_API_KEY` | Phrase auto-generation via Claude API | Only required if you use phrase auto-generation |
| `PHRASE_GEN_MODEL` | Override the model used for phrase generation | Optional (defaults to `claude-sonnet-5`) |
| `EN_FONT_PATH` / `JP_FONT_PATH` | Explicitly pin the fonts used for image rendering | Optional (falls back to an OS-appropriate default path) |

**Never commit `.env`** (it's already covered by `.gitignore`).

## Using the Web UI (recommended)

### Start the server

```bash
cd backend
python3 src/app.py
# or: uv run python3 src/app.py
```

Open `http://localhost:8000` in your browser.

### Walkthrough

1. **(Optional) Generate new phrases** — enter a theme (e.g. "restaurant conversation") and a
   count, then click "Generate". This calls the Claude API to generate phrases, saving them to a
   CSV and inserting them into the phrase database at the same time.
2. **Select/upload a CSV, or generate from the phrase bank**
   - Pick an existing CSV from the dropdown (files under `data/`), or upload your own.
   - Or use "Or Generate From Phrase Bank" to generate a video directly from unused phrases
     already stored in the DB, by theme and count (once a video succeeds, those phrases are
     automatically marked "used" and won't be picked again).
3. **Preview phrases** — check the contents of the selected CSV.
4. **Click "Generate Video"** — generation starts, with real-time progress. If another
   generation job is already running, your request is automatically queued and starts as soon
   as the running job finishes.
5. **Play or download** — once done, play the video in the browser or download the MP4.

Job state (running / queued / completed / error) survives a server restart.

### CSV format

Column 1 = English phrase, column 2 = Japanese translation, with a header row. See
`data/sample_phrases.csv`.

```csv
english,japanese
Break a leg!,頑張ってね!(舞台などの本番前の決まり文句)
It's a piece of cake.,それは朝飯前だよ。
```

## Using the CLI directly

You can also run the underlying scripts without the Web UI.

```bash
# Run the video pipeline from a CSV
python3 src/video_pipeline.py data/sample_phrases.csv
# With no argument, it uses a built-in 3-phrase sample
python3 src/video_pipeline.py

# Auto-generate phrases via Claude API (saved as CSV under data/generated/)
python3 src/phrase_generator.py "restaurant conversation" 50

# Manage the phrase database
python3 src/phrase_db.py init                              # initialize the DB
python3 src/phrase_db.py stats                              # show unused/total counts per theme
python3 src/phrase_db.py import data/sample_phrases.csv restaurant   # import a CSV into the DB

# Inspect video-generation job history
python3 src/job_store.py list
```

## Troubleshooting

- **Japanese text renders as garbled boxes (□)** → set `JP_FONT_PATH` explicitly in `.env`. On
  macOS, `/System/Library/Fonts/AppleSDGothicNeo.ttc` should work out of the box.
- **`ffmpeg: command not found`** → install it per the "System commands" section above.
- **Phrase auto-generation fails** → check that `ANTHROPIC_API_KEY` is set in `.env`.
- **No "another job is already running" error** → sending two or more requests at once won't
  error out; extra requests are automatically queued (shown as `queued` status) instead.
