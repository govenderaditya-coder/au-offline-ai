#!/bin/bash
# ============================================================
#  AU Podcast Generator (1-Click Auto Extractor)
#  Converts AU's latest chat script into a real audio podcast!
# ============================================================

PODCAST_DIR="$HOME/Downloads/offline ai/podcasts"
BUILDER="$HOME/Downloads/offline ai/tools/au-podcast-builder"
DB_PATH="$HOME/.local/share/uv/tools/open-webui/lib/python3.11/site-packages/open_webui/data/webui.db"
mkdir -p "$PODCAST_DIR"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
OUTPUT_FILE="$PODCAST_DIR/AU_Podcast_$TIMESTAMP.m4a"
SCRIPT_FILE="/tmp/au_script_$TIMESTAMP.txt"

echo "🎙️ Extracting latest podcast script from AU..."

python3 - << 'EOF' > "$SCRIPT_FILE"
import sqlite3, json, re, os

db_path = os.path.expanduser("~/.local/share/uv/tools/open-webui/lib/python3.11/site-packages/open_webui/data/webui.db")
if not os.path.exists(db_path):
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT chat FROM chat ORDER BY updated_at DESC LIMIT 1")
row = c.fetchone()
if not row:
    exit(1)

chat_data = json.loads(row[0])
messages = chat_data.get("history", {}).get("messages", {})

assistant_text = ""
for mid, msg in messages.items():
    if msg.get("role") == "assistant":
        assistant_text = msg.get("content", "")

if not assistant_text:
    exit(1)

# Check for explicit podcast section or use whole text
podcast_match = re.search(r"\*\*Podcast Script:\*\*(.*)", assistant_text, re.DOTALL | re.IGNORECASE)
script_body = podcast_match.group(1) if podcast_match else assistant_text

lines = script_body.split("\n")
dialogue = []
hosts = ["Samantha", "Daniel"]
host_idx = 0

for line in lines:
    line = line.strip()
    if not line or line.startswith("* Online") or line.startswith("Note:") or line.startswith("**Title:"):
        continue
    cleaned = re.sub(r"\*\*.*?\*\*:?", "", line).strip()
    cleaned = re.sub(r"^[#\*\-]+\s*", "", cleaned).strip()
    if len(cleaned) < 15:
        continue
    
    # Check if already has host name
    if cleaned.lower().startswith("samantha:"):
        dialogue.append(cleaned)
    elif cleaned.lower().startswith("daniel:"):
        dialogue.append(cleaned)
    else:
        current_host = hosts[host_idx % 2]
        dialogue.append(f"{current_host}: {cleaned}")
        host_idx += 1

print("\n".join(dialogue))
EOF

if [ ! -s "$SCRIPT_FILE" ]; then
    echo "⚠️ Could not auto-detect from chat, checking clipboard..."
    pbpaste > "$SCRIPT_FILE"
fi

if [ ! -s "$SCRIPT_FILE" ]; then
    echo "❌ No script found! Ask AU for a podcast script first."
    exit 1
fi

"$BUILDER" "$SCRIPT_FILE" "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Podcast created successfully!"
    echo "📁 Saved to: $OUTPUT_FILE"
    echo "🎧 Opening in QuickTime..."
    open "$OUTPUT_FILE"
else
    echo "❌ Error generating podcast."
fi

rm -f "$SCRIPT_FILE"
