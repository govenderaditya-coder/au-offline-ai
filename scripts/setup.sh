#!/bin/bash
# ============================================================
#  Offline AI — First-Time Setup Script
#  Run this ONCE when you have internet to set everything up.
#  After this, everything works offline forever.
# ============================================================

set -e  # Stop on any error

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       Offline AI — Setup for Mac M4      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# --- 1. Install Ollama (the AI engine) ---
echo "📦 Step 1: Installing Ollama (AI engine)..."
if command -v ollama &>/dev/null; then
    echo "   ✅ Ollama already installed. Updating..."
    brew upgrade ollama 2>/dev/null || true
else
    brew install ollama
    echo "   ✅ Ollama installed!"
fi

# --- 2. Start Ollama server ---
echo ""
echo "🚀 Step 2: Starting Ollama server..."
pkill ollama 2>/dev/null || true
sleep 1
ollama serve &>/dev/null &
OLLAMA_PID=$!
sleep 3
echo "   ✅ Ollama server running (PID: $OLLAMA_PID)"

# --- 3. Download the AI model ---
echo ""
echo "🤖 Step 3: Downloading AI model (llama3.1 ~5GB)..."
echo "   ⏳ This will take a few minutes depending on your internet speed..."
ollama pull llama3.1
echo "   ✅ Model downloaded!"

# --- 4. Install Open WebUI (the chat GUI) ---
echo ""
echo "🌐 Step 4: Installing Open WebUI (your chat interface)..."

# Check if python3 / pip is available
if ! command -v pip3 &>/dev/null; then
    echo "   📥 Installing Python via Homebrew..."
    brew install python
fi

pip3 install open-webui 2>&1 | grep -E "(Successfully|already|error)" || true
echo "   ✅ Open WebUI installed!"

# --- 5. Install the auto-updater ---
echo ""
echo "🔄 Step 5: Setting up auto-updater (runs when internet detected)..."
chmod +x ~/Downloads/"offline ai"/auto-update-models.sh

cp ~/Downloads/"offline ai"/com.offlineai.autoupdate.plist \
   ~/Library/LaunchAgents/com.offlineai.autoupdate.plist

launchctl unload ~/Library/LaunchAgents/com.offlineai.autoupdate.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.offlineai.autoupdate.plist
echo "   ✅ Auto-updater installed! Will check for updates every 6 hours."

# --- 6. Create a launcher shortcut ---
echo ""
echo "🎯 Step 6: Creating easy-launch script..."

cat > ~/Downloads/"offline ai"/start-ai.sh << 'EOF'
#!/bin/bash
echo "🚀 Starting your Offline AI..."

# Start Ollama server if not running
if ! pgrep -x "ollama" &>/dev/null; then
    ollama serve &>/dev/null &
    sleep 2
fi

# Open the chat UI in browser
echo "🌐 Opening AI chat in your browser..."
sleep 1
open-webui serve &>/dev/null &
sleep 3
open http://localhost:8080
echo "✅ Done! Chat with your AI at http://localhost:8080"
EOF

chmod +x ~/Downloads/"offline ai"/start-ai.sh
echo "   ✅ Launcher created!"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║           ✅ SETUP COMPLETE!              ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  To START your AI anytime, run:          ║"
echo '║  bash ~/Downloads/offline\ ai/start-ai.sh'
echo "║                                          ║"
echo "║  Your AI chat will open at:              ║"
echo "║  http://localhost:8080                   ║"
echo "║                                          ║"
echo "║  Auto-updates: Every 6hrs when online    ║"
echo "║                                          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
