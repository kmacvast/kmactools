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

if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Error: This script is optimized for macOS (Apple Silicon) and cannot run on this OS."
    exit 1
fi

check_prereq() {
    local cmd=$1
    local pkg=$2
    if ! command -v "$cmd" &> /dev/null; then
        echo "Prerequisite '$pkg' is missing."
        read -p "Would you like to install $pkg via Homebrew now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if ! command -v brew &> /dev/null; then
                echo "Homebrew not found. Please install Homebrew first at https://brew.sh"
                exit 1
            fi
            brew install "$pkg"
        else
            echo "Error: $pkg is required for this script to function."
            exit 1
        fi
    fi
}

check_prereq "brew" "brew"
check_prereq "yt-dlp" "yt-dlp"
check_prereq "ffmpeg" "ffmpeg"

if ! brew list whisper-cpp &> /dev/null; then
    echo "Prerequisite 'whisper-cpp' is missing."
    read -p "Would you like to install whisper-cpp via Homebrew now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        brew install whisper-cpp
    else
        echo "Error: whisper-cpp is required."
        exit 1
    fi
fi

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

RAW_TITLE=$(yt-dlp --get-title "$URL")
SAFE_TITLE=$(echo "$RAW_TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g' | sed 's/__*/_/g' | sed 's/^_//;s/_$//')

if [ -z "$SAFE_TITLE" ]; then
    SAFE_TITLE="transcription_$(date +%Y%m%d_%H%M%S)"
fi

MODEL_NAME="ggml-small.en.bin"
MODEL_DIR="$HOME/.cache/whisper-models"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"

mkdir -p "$MODEL_DIR"

if [ ! -f "$MODEL_PATH" ] || [ $(stat -f%z "$MODEL_PATH") -lt 1000000 ]; then
    echo "--- Downloading Whisper Model (Approx 460MB) ---"
    rm -f "$MODEL_PATH"
    curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME" -o "$MODEL_PATH"
fi

echo "--- Downloading: $RAW_TITLE ---"
yt-dlp -f "ba" -x --audio-format wav "$URL" -o "${SAFE_TITLE}_raw.wav"

echo "--- Resampling to 16kHz ---"
ffmpeg -i "${SAFE_TITLE}_raw.wav" -ar 16000 -ac 1 -c:a pcm_s16le "${SAFE_TITLE}_ready.wav" -y

BREW_PATH=$(brew --prefix whisper-cpp)

if [ -f "$BREW_PATH/bin/whisper-cli" ]; then
    WHISPER_EXE="$BREW_PATH/bin/whisper-cli"
else
    WHISPER_EXE="$BREW_PATH/bin/whisper-cpp"
fi

export GGML_METAL_PATH_RESOURCES="$BREW_PATH/share/whisper-cpp"

echo "--- Starting Transcription (Writing to .txt) ---"
"$WHISPER_EXE" -m "$MODEL_PATH" -f "${SAFE_TITLE}_ready.wav" --language en -nt -otxt

echo "--- Process Complete ---"
echo "Transcription saved to: ${SAFE_TITLE}_ready.wav.txt"
echo "Preserved: ${SAFE_TITLE}_raw.wav, ${SAFE_TITLE}_ready.wav"