#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "  Branding Bot — Render Build Script"
echo "========================================"

# ── Install Python dependencies ───────────────────────────────────────
echo "-> Installing Python requirements..."
pip install -r requirements.txt

# ── Install FFmpeg ────────────────────────────────────────────────────
echo "-> Installing FFmpeg..."
apt-get update -qq
apt-get install -y -qq ffmpeg > /dev/null 2>&1

# ── Verify FFmpeg ─────────────────────────────────────────────────────
echo "-> Verifying FFmpeg installation..."
if ! command -v ffmpeg &> /dev/null; then
    echo "ERROR: FFmpeg installation failed. Video processing will not work."
    exit 1
fi

FFMPEG_VERSION=$(ffmpeg -version | head -n 1)
echo "-> FFmpeg OK: $FFMPEG_VERSION"

echo "========================================"
echo "  Build complete. Starting worker..."
echo "========================================"
