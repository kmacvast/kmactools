#!/bin/bash

###############################################################################
# Script Name: yt-transcribe.sh
# Description: Downloads YouTube audio and generates a local transcription.
# Environment: Optimized for Apple Silicon (M1/M3/M5) using whisper.cpp.
# Dependencies: yt-dlp, ffmpeg, whisper-cpp (installed via Homebrew).
# Author:      Kevin McDonald
# Date:        May 6, 2026
###############################################################################

usage() {
    echo "Usage: $0 --url <youtube_url>"
    echo ""
    echo "Options:"
    echo "  --url    The full YouTube URL to transcribe (Required)"
    echo "  -h       Show this help message"
    exit 1
}

# Fix for long-option --url
for arg in "$@"; do
  shift
  case "$arg" in
    "--url") set -- "$@" "-u" ;;
    "--help") set -- "$@" "-h" ;;
    *) set -- "$@" "$arg" ;;
  esac
done

while getopts "u:h" opt; do
    case "$opt" in
        u) URL=$OPTARG ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [ -z "$URL" ]; then
    echo "Error: The --url parameter is required."
    usage
fi

MODEL_NAME="ggml-small.en.bin"
MODEL_DIR="$HOME/.cache/whisper-models"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"

mkdir -p "$MODEL_DIR"

# Integrity check: Ensure model is present and not a corrupt/partial download
if [ ! -f "$MODEL_PATH" ] || [ $(stat -f%z "$MODEL_PATH") -lt 1000000 ]; then
    echo "--- Downloading Whisper Model (Approx 460MB) ---"
    rm -f "$MODEL_PATH"
    curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME" -o "$MODEL_PATH"
fi

echo "--- Downloading YouTube Audio ---"
# Using a temp name to avoid overlapping runs
yt-dlp -f "ba" -x --audio-format wav "$URL" -o "temp_audio.wav"

echo "--- Resampling to 16kHz ---"
ffmpeg -i "temp_audio.wav" -ar 16000 -ac 1 -c:a pcm_s16le "ready_audio.wav" -y

# Explicitly target the correct Homebrew binaries
BREW_PATH=$(brew --prefix whisper-cpp)
# Priority 1: whisper-cli (standard for newer brew installs)
# Priority 2: whisper-cpp (fallback)
if [ -f "$BREW_PATH/bin/whisper-cli" ]; then
    WHISPER_EXE="$BREW_PATH/bin/whisper-cli"
else
    WHISPER_EXE="$BREW_PATH/bin/whisper-cpp"
fi

export GGML_METAL_PATH_RESOURCES="$BREW_PATH/share/whisper-cpp"

echo "--- Starting Transcription (Writing to .txt) ---"
# -otxt: Automatically creates ready_audio.wav.txt
# -nt:   Removes timestamps for a clean transcript
"$WHISPER_EXE" -m "$MODEL_PATH" -f "ready_audio.wav" --language en -nt -otxt

echo "--- Process Complete ---"
echo "Transcription saved to: ready_audio.wav.txt"
echo "Preserved: temp_audio.wav, ready_audio.wav"