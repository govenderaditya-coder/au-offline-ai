import Foundation
import Speech
import AVFoundation

let audioEngine = AVAudioEngine()
guard let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    print("ERROR: Speech recognizer not available")
    exit(1)
}

if !speechRecognizer.isAvailable {
    print("ERROR: Speech recognizer not available on this system")
    exit(1)
}

let request = SFSpeechAudioBufferRecognitionRequest()
request.shouldReportPartialResults = true
if speechRecognizer.supportsOnDeviceRecognition {
    request.requiresOnDeviceRecognition = true
}

let inputNode = audioEngine.inputNode
let recordingFormat = inputNode.outputFormat(forBus: 0)

var lastWordTime = Date()
var finalTranscription = ""
var isDone = false
let semaphore = DispatchSemaphore(value: 0)

inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
    request.append(buffer)
}

audioEngine.prepare()
do {
    try audioEngine.start()
} catch {
    print("ERROR: Could not start audio engine: \(error)")
    exit(1)
}

fputs("🎙️ Listening (speak now)...\n", stderr)

let task = speechRecognizer.recognitionTask(with: request) { result, error in
    if let result = result {
        let text = result.bestTranscription.formattedString
        if !text.isEmpty && text != finalTranscription {
            finalTranscription = text
            lastWordTime = Date()
            fputs("  🗣️ \"\(text)\"\n", stderr)
        }
        if result.isFinal {
            isDone = true
            semaphore.signal()
        }
    }
    if error != nil {
        isDone = true
        semaphore.signal()
    }
}

// Silence detector timer on background thread
DispatchQueue.global().async {
    let startTime = Date()
    while !isDone {
        Thread.sleep(forTimeInterval: 0.3)
        // If we heard something and silence for 1.8s, finalize
        if !finalTranscription.isEmpty && Date().timeIntervalSince(lastWordTime) > 1.8 {
            fputs("  ✅ Done listening\n", stderr)
            break
        }
        // Max timeout 15 seconds
        if Date().timeIntervalSince(startTime) > 15.0 {
            break
        }
    }
    audioEngine.stop()
    inputNode.removeTap(onBus: 0)
    request.endAudio()
    task.finish()
    semaphore.signal()
}

_ = semaphore.wait(timeout: .now() + 16.0)
print(finalTranscription.trimmingCharacters(in: .whitespacesAndNewlines))
