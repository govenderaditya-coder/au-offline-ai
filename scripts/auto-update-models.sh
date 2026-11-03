#!/bin/bash
# ============================================================
#  Offline AI — Auto-Update Script
#  Runs when internet is detected; updates all Ollama models
#  and Open WebUI automatically.
# ============================================================

LOG_FILE="$HOME/.offline-ai/update.log"
mkdir -p "$HOME/.offline-ai"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# --- Check internet connectivity ---
check_internet() {
    ping -c 1 -W 2 8.8.8.8 &>/dev/null
    return $?
}

log "====== Offline AI Auto-Update Started ======"

if ! check_internet; then
    log "❌ No internet detected. Skipping update."
    exit 0
fi

log "✅ Internet detected. Starting updates..."

# --- Update Ollama itself ---
log "📦 Updating Ollama..."
brew upgrade ollama 2>&1 | tee -a "$LOG_FILE"

# --- Pull latest versions of all installed models ---
log "🤖 Updating all installed AI models..."

if ! command -v ollama &>/dev/null; then
    log "⚠️  Ollama not found. Please install it first."
    exit 1
fi

# Make sure ollama server is running
if ! pgrep -x "ollama" &>/dev/null; then
    log "🚀 Starting Ollama server..."
    ollama serve &>/dev/null &
    sleep 3
fi

# Get list of installed models and update each one
MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | grep -v "^$")

if [ -z "$MODELS" ]; then
    log "ℹ️  No models installed yet. Nothing to update."
else
    while IFS= read -r model; do
        log "⬇️  Pulling latest: $model"
        ollama pull "$model" 2>&1 | tee -a "$LOG_FILE"
        log "✅ Done: $model"
    done <<< "$MODELS"
fi

# --- Update Open WebUI (via pip) ---
log "🌐 Updating Open WebUI..."
if command -v pip3 &>/dev/null; then
    pip3 install --upgrade open-webui 2>&1 | tee -a "$LOG_FILE"
    log "✅ Open WebUI updated."
else
    log "ℹ️  pip3 not found — skipping Open WebUI update."
fi

log "🎉 All updates complete!"
log "====== Update Finished ======"
