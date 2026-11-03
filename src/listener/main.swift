import Foundation
import Speech
import AVFoundation

let audioEngine = AVAudioEngine()
guard let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    exit(1)
}

if !speechRecognizer.isAvailable {
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
    exit(1)
}

let task = speechRecognizer.recognitionTask(with: request) { result, error in
    if let result = result {
        let text = result.bestTranscription.formattedString
        if !text.isEmpty && text != finalTranscription {
            finalTranscription = text
            lastWordTime = Date()
            fputs("\r🎙️ Hearing: \"\(text)\"  ", stderr)
            fflush(stderr)
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

// Background silence & timeout monitor
DispatchQueue.global().async {
    let startTime = Date()
    while !isDone {
        Thread.sleep(forTimeInterval: 0.2)
        // If we heard speech and user stopped for 1.3s, finalize
        if !finalTranscription.isEmpty && Date().timeIntervalSince(lastWordTime) > 1.3 {
            break
        }
        // If no speech at all after 4.5 seconds, reset cycle
        if finalTranscription.isEmpty && Date().timeIntervalSince(startTime) > 4.5 {
            break
        }
        // Hard safety timeout
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
let output = finalTranscription.trimmingCharacters(in: .whitespacesAndNewlines)
if !output.isEmpty {
    fputs("\n", stderr)
    print(output)
}
