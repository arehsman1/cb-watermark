# Branding Bot

A production-ready Telegram bot for applying custom PNG watermarks to images and videos, with optional compression. Built for deployment on Render as a Background Worker.

## Features

- **Image watermarking** — JPG, JPEG, PNG, WEBP
- **Video watermarking** — MP4, MOV, AVI, MKV
- **Landscape/Portrait profiles** — separate position, opacity, compression, and old-watermark-removal settings for landscape vs portrait media, shared between images and videos of that orientation
- **Compression presets** — Original, High Quality, Medium Quality
- **Watermark settings** — Position, opacity, easy replacement
- **Progress tracking** — Live progress bar with cancel button
- **Quality-first policy** — Never downscales, never drops frame rate, preserves audio
- **Render-ready** — Single-click deploy with FFmpeg auto-installation

## Landscape vs Portrait Settings

Settings → **📐 Landscape Settings** and **📱 Portrait Settings** are two
independent profiles. Each holds its own watermark position, opacity,
compression quality, and old-watermark-removal config. Orientation is
detected automatically from each upload's actual dimensions (wider than
tall = landscape, taller than wide = portrait) — so a landscape photo and
a landscape video both use the Landscape profile, and any portrait media
(9:16 reel, 4:5 post, 3:4 photo, etc.) uses the Portrait profile regardless
of its exact size, since position/opacity/scale are all computed as
percentages of the actual media dimensions, not fixed pixels.

The watermark **image** itself (Settings → 🖼️ Set Watermark) is shared
across both profiles — only how/where it's applied differs by orientation.

If you're upgrading from an older version of this bot with a single flat
`settings.json`, it's migrated automatically on first run: your old
settings become the starting point for both the Landscape and Portrait
profiles, which you can then adjust independently.

## Project Structure

```
branding_bot/
├── bot.py                  # Entry point & dispatcher
├── config.py               # Centralized configuration
├── settings_manager.py     # Async JSON settings abstraction
├── logger.py               # Console + rotating file logging
├── requirements.txt
├── render.yaml             # Render Background Worker manifest
├── build.sh                # FFmpeg provisioning script
├── .env.example
├── settings.json
├── handlers/               # Telegram update handlers
├── processors/             # Image & video processing engines
├── services/               # Business logic & queue management
├── utilities/              # File helpers & progress tracking
├── keyboards/              # Reply keyboard factories
├── logs/                   # Runtime logs
├── watermark/              # User-uploaded watermark
├── uploads/                # Temporary downloads
├── outputs/                 # Final processed files
└── temp/                   # Scratch space
```

## Local Development

### Prerequisites

- Python 3.12+
- FFmpeg installed system-wide (`ffmpeg -version`)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Installation

```bash
git clone <repo-url>
cd branding_bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment

Copy the example and fill in your token:

```bash
cp .env.example .env
# Edit .env and set BOT_TOKEN
```

### Run

```bash
python bot.py
```

## Render Deployment

1. Push this repo to GitHub.
2. In Render, create a new **Background Worker**.
3. Connect your GitHub repository.
4. Add the environment variable `BOT_TOKEN` in the Render dashboard.
5. Render will automatically run `build.sh` to install FFmpeg, then start `python bot.py`.

## Removing an Old Watermark

Settings → **📐 Landscape Settings** (or **📱 Portrait Settings**) →
**🧹 Old Watermark Removal** lets the bot erase an existing watermark
from your own content before applying yours — configured separately
per orientation, since old watermark size/position often differs
between landscape and portrait content. Toggle it on, set which
corner the old watermark is usually in, and pick a search area size
(Small/Medium/Large — this is a ceiling for detection, not a fixed
removal size). The bot analyzes each upload's corner for
higher-contrast/edge content typical of an overlaid logo and erases
just that region:
- Images: OpenCV inpainting reconstructs the erased area from
  surrounding pixels.
- Video: FFmpeg's `delogo` filter does the equivalent per frame,
  using detection from the first frame.

This is a best-effort reconstruction, not perfect removal — results
are best on a small logo over a simple background, and rougher on
busy/detailed backgrounds. It's off by default; enable it only when
you're rebranding old content that actually has an old mark on it,
since it adds analysis + re-encoding time to every upload.

### How removal quality is chosen automatically

Under the hood, `processors/removal/` is a small modular architecture,
not a single hardcoded technique:

```
processors/removal/
├── base_processor.py       # Abstract interface every processor implements
├── opencv_processor.py     # Fast, always-available, CPU-cheap inpainting
├── lama_processor.py       # Optional AI inpainting for complex backgrounds
├── complexity_analyzer.py  # Classifies a region as simple/complex
└── processor_selector.py   # Picks the right processor automatically
```

Every removal region is analyzed (edge density + local texture
variance) and classified **simple** (flat colors, sky, walls, paper,
gentle gradients) or **complex** (hair, faces, foliage, fabric, water,
shadows, detailed patterns). Simple regions always use OpenCV.
Complex regions use LaMa *if it's installed* — otherwise they also
use OpenCV automatically, no error, no user-facing difference except
reconstruction quality. If LaMa is installed but fails on a given job
(e.g. memory pressure), it falls back to OpenCV for that job instead
of failing the whole request. You never choose manually — this
happens per-region, automatically.

**LaMa is optional and NOT installed by default.** It's a genuine deep
learning model (~200MB weights, needs PyTorch) — meaningfully heavier
than everything else in this project. Install it only if you want
better results on complex backgrounds and can spare the disk/RAM:

```
pip install -r requirements-lama.txt
```

On a 4GB VPS: the model loads fresh per job and is explicitly released
(`del` + `gc.collect()`) immediately after, so it never sits resident
in RAM between jobs — you pay a few seconds of reload time per complex
region, not a permanent memory footprint.

**Video intentionally does not use LaMa** — it stays on OpenCV
detection + FFmpeg's `delogo` filter. Per-frame AI inpainting on a
2 vCPU CPU-only box would turn a short clip into a multi-minute job,
so video trades LaMa's quality for speed by design.

**Video intentionally uses two different paths depending on
complexity and length**, not LaMa unconditionally:
- Simple background, OR LaMa not installed, OR the clip exceeds
  `MAX_LAMA_VIDEO_FRAMES` (300 frames, ~12s at 25fps) → the fast
  single-pass FFmpeg `delogo` filter, same as before.
- Complex background AND LaMa installed AND within the frame cap →
  frames are extracted, LaMa erases the region on each one (the
  model is loaded **once** for the whole video via a batch session,
  not per frame — reloading a 200MB model per frame would make a
  short clip take many minutes instead of seconds), your watermark
  is re-applied per frame, and FFmpeg rebuilds the video with the
  original audio restored.

The frame-count cap exists specifically to protect a 2 vCPU / 4GB
CPU-only VPS from a runaway job — a long complex video automatically
falls back to the fast path rather than risk exhausting memory or
taking an unreasonable amount of time. This is logged clearly (`logs/bot.log`)
whichever path gets used.

Adding a future processor (AI enhancement, super-resolution, etc.)
means writing one class in `processors/removal/` and registering it
in `ProcessorSelector` — no changes needed to Telegram handlers, FSM
states, or `image_processor.py`/`video_processor.py`.

## Metadata Tools

📋 **Metadata Tools** (main menu) lets you view, edit, or clear a
file's metadata — separate from the watermarking flow.

Send an image or video **as a file** (not a compressed photo —
Telegram strips EXIF from compressed photos). Limits: images up to
20MB (JPG/JPEG/PNG/WEBP), video up to 200MB / 10 minutes /
1920x1080 (MP4/MOV/AVI/MKV).

**View** shows File Information, Camera Information, Date
Information, Software, and Copyright for images, plus GPS
(latitude/longitude/altitude/timestamp, reverse-geocoded to a
readable address via OpenStreetMap's Nominatim — free, no API key)
when present. Sections with no data are simply omitted rather than
shown empty. Video shows file info plus whatever container tags
exist (title, artist, comment, etc.) via ffprobe.

**Edit** lets you change Artist/Copyright/Software/Date-Modified on
images, or Title/Artist/Copyright/Comment on video — the fields a
person would actually retype by hand, not sensor-reported facts like
camera model or GPS. Video edits use FFmpeg's `-c copy` (stream
copy), so the actual audio/video data is never re-encoded, only the
container tags change.

**Clear** strips all metadata (all EXIF for images, all container
tags for video, also stream-copied, no re-encoding) and sends back a
clean file.

Reverse geocoding is best-effort: if the network call to Nominatim
fails for any reason, GPS coordinates still display, just without an
address line — metadata viewing never breaks because of it.

## Updating the Watermark

1. Open the bot in Telegram and tap **⚙️ Settings**.
2. Tap **🖼️ Set Watermark**.
3. Send a PNG image with transparency.
4. The new watermark replaces the old one automatically.

## Compression Settings

1. Open **⚙️ Settings** → **📐 Landscape Settings** or **📱 Portrait Settings**.
2. Tap **🗜️ Compression Quality**.
2. Choose:
   - **⭐ Original** — No compression, maximum quality. JPEG uses
     quality=95 (JPEG has no true lossless mode — this is the
     accepted "visually lossless" ceiling). PNG and WEBP are
     genuinely lossless (zero pixel deviation from source). Video
     uses CRF 18 (visually lossless).
   - **⭐⭐ High Quality** — Modest bitrate reduction
   - **⭐⭐⭐ Medium Quality** — Balanced file size

None of these ever reduce resolution or frame rate — only
quality/bitrate changes. Video keeps the original codec via FFmpeg
stream copy (`-c:v copy`) whenever no watermark or old-watermark
removal is applied; re-encoding to libx264 only happens when a
filter (watermark overlay, delogo) actually needs to run.

## File Management

Every job cleans up its own input/output/temp files immediately in a
`finally` block, on success, failure, or cancellation alike — this is
the main defense against disk exhaustion during normal operation.
On top of that, a periodic sweep runs every 15 minutes for the life
of the process (in addition to the one-time sweep at startup) and
removes anything older than 30 minutes left behind in `temp/`,
`uploads/`, or `outputs/` — a safety net for crashes or unexpected
exits, not something normal operation should rely on. All cleanup
(routine and periodic) is logged to `logs/bot.log`.

## Performance Notes (2 vCPU / 4GB target)

- Single-job queue (`QueueManager`) means no concurrent processing —
  the main defense against memory pressure on a small box.
- Images are guarded against decompression-bomb-style uploads: a
  small file on disk can decode to an enormous pixel buffer (verified
  concretely — a 0.42MB solid-color PNG decoded to 549MB as RGBA).
  Dimensions are capped at 64 megapixels, checked via a header-only
  read (~20ms even for a 144MP file) before any pixel data is
  decoded — well above any real camera/phone photo, so this never
  affects legitimate uploads.
- LaMa (when installed) loads its model fresh per image and releases
  it immediately after (`del` + `gc.collect()`); video batches all
  frames under one model load, released once at the end — never
  resident between jobs either way.
- Video's frame-by-frame LaMa pipeline processes one frame at a time
  from disk, not all frames loaded into memory at once, so memory
  use doesn't scale with clip length — length is instead bounded by
  the frame-count cap (see Adaptive Watermark Removal Engine above).
- `-preset slow` for video encoding is intentional: it trades CPU for
  better compression efficiency, safe here specifically because only
  one job runs at a time — there's no contention to make that a
  problem.

## Logging

Everything logs to console and `logs/bot.log`: which processor was
selected and why (OpenCV/LaMa, with the complexity signals that drove
the choice), processing time for every image/video job, FFmpeg's
command and full output (`LOG_LEVEL=DEBUG`) with the last 20 lines
always surfaced on failure regardless of log level, metadata actions
(view/edit/clear, who and what), cleanup events (routine and
periodic), queue events (job start/finish/rejection/cancellation),
and unhandled exceptions with full tracebacks.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "FFmpeg not found" | Missing system package | Ensure `build.sh` ran on Render, or install FFmpeg locally |
| "File too large" | Render disk limit | Send smaller files; bot rejects >45 MB inputs |
| Watermark not applied | Missing or invalid PNG | Upload a valid PNG with transparency via Settings |
| Processing cancelled | User pressed ❌ Cancel | Re-upload the file |
| Bot not responding | Token invalid or worker asleep | Check `BOT_TOKEN`; free workers sleep after inactivity |

## Common Errors

- **Unsupported file type** — Only the listed image/video formats are accepted.
- **Corrupted media** — FFmpeg or Pillow could not decode the file. Try re-exporting it.
- **Insufficient disk space** — Render free tier has limited ephemeral storage. The bot auto-cleans temp files, but very large videos may still fail.
