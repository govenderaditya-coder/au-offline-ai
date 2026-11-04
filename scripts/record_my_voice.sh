#!/bin/bash
# ============================================================
#  AU Voice Cloning — Reference Voice Recorder
#  Records a 15-second clean voiceover sample from your Mac mic
# ============================================================

VOICES_DIR="$HOME/Downloads/offline ai/voices"
mkdir -p "$VOICES_DIR"

OUTPUT_FILE="$VOICES_DIR/my_voice_sample.wav"
TEMP_FILE="/tmp/voice_clone_raw.wav"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║          🎙️ AU VOICE CLONING RECORDER                ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "You will record a 15-second sample to clone your voice."
echo "Please read the following sample sentence out loud clearly:"
echo ""
echo "👉 \"Hello, my name is Aditya. This is my voice sample for AU."
echo "    AU is my private personal assistant running on my Mac,"
echo "    and from now on, AU will use my voice to speak.\""
echo ""
read -p "Press [Enter] when ready to start recording..."

echo ""
echo "🔴 RECORDING NOW... (Speak clearly into your Mac microphone)"

# Record for 15 seconds using Swift CoreAudio recorder
swift - << 'EOF'
import Foundation
import AVFoundation

let audioEngine = AVAudioEngine()
let inputNode = audioEngine.inputNode
let recordingFormat = inputNode.outputFormat(forBus: 0)

let outputURL = URL(fileURLWithPath: "/tmp/voice_clone_raw.wav")
try? FileManager.default.removeItem(at: outputURL)

guard let audioFile = try? AVAudioFile(forWriting: outputURL, settings: recordingFormat.settings) else {
    exit(1)
}

inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
    try? audioFile.write(from: buffer)
}

do {
    try audioEngine.start()
    for i in (1...15).reversed() {
        print("\r⏱️  Time remaining: \(i) seconds...  ", terminator: "")
        fflush(stdout)
        Thread.sleep(forTimeInterval: 1.0)
    }
    print("")
    audioEngine.stop()
    inputNode.removeTap(onBus: 0)
} catch {
    print("Recording failed: \(error)")
}
EOF

if [ -f "$TEMP_FILE" ]; then
    mv "$TEMP_FILE" "$OUTPUT_FILE"
    echo ""
    echo "✅ Voice sample saved successfully!"
    echo "📁 File: $OUTPUT_FILE"
    echo ""
    echo "🎧 Playing your recording back to you..."
    afplay "$OUTPUT_FILE"
else
    echo "❌ Failed to record sample."
fi
