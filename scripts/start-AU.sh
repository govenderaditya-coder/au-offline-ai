#!/bin/bash
export PATH="/Users/aditya/.local/bin:/opt/homebrew/bin:$PATH"

echo ""
echo "╔══════════════════════════════╗"
echo "║        AU — Starting...      ║"
echo "╚══════════════════════════════╝"
echo ""

# Start Ollama if not running
if ! pgrep -x "ollama" &>/dev/null; then
    echo "🧠 Starting AU's brain (Ollama)..."
    brew services start ollama
    sleep 2
fi

# Start Open WebUI if not already on port 8080
if ! lsof -i :8080 &>/dev/null; then
    echo "🌐 Starting AU's interface (Open WebUI)..."
    nohup /Users/aditya/.local/bin/open-webui serve > ~/.offline-ai/webui.log 2>&1 &
    echo "⏳ Warming up... (15 seconds)"
    sleep 15
fi

echo "✅ AU is online!"
echo ""
echo "Opening AU in your browser → http://localhost:8080"
open http://localhost:8080
