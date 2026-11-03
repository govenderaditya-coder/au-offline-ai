import Foundation
import AVFoundation

let audioEngine = AVAudioEngine()
let inputNode = audioEngine.inputNode
let recordingFormat = inputNode.outputFormat(forBus: 0)

let outputURL = URL(fileURLWithPath: "/tmp/au_speech.wav")
try? FileManager.default.removeItem(at: outputURL)

guard let audioFile = try? AVAudioFile(forWriting: outputURL, settings: recordingFormat.settings) else {
    exit(1)
}

var isSpeechDetected = false
var lastSpeechTime = Date()
let startTime = Date()
var isDone = false
let semaphore = DispatchSemaphore(value: 0)

// Threshold for human speech vs room noise
let speechThreshold: Float = 0.012

inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { buffer, _ in
    guard let channelData = buffer.floatChannelData?[0] else { return }
    let frameLength = Int(buffer.frameLength)
    
    var sum: Float = 0.0
    for i in 0..<frameLength {
        sum += channelData[i] * channelData[i]
    }
    let rms = sqrt(sum / Float(frameLength))
    
    if rms > speechThreshold {
        if !isSpeechDetected {
            isSpeechDetected = true
            fputs("🎙️ [LISTENING] Voice detected...\n", stderr)
        }
        lastSpeechTime = Date()
    }
    
    if isSpeechDetected {
        try? audioFile.write(from: buffer)
    }
}

do {
    try audioEngine.start()
} catch {
    exit(1)
}

DispatchQueue.global().async {
    while !isDone {
        Thread.sleep(forTimeInterval: 0.1)
        let now = Date()
        
        // If speaking and paused for 1.2 seconds, finalize
        if isSpeechDetected && now.timeIntervalSince(lastSpeechTime) > 1.2 {
            break
        }
        
        // If no speech heard after 4 seconds, cycle
        if !isSpeechDetected && now.timeIntervalSince(startTime) > 4.0 {
            break
        }
        
        // Safety cap 15 seconds
        if now.timeIntervalSince(startTime) > 15.0 {
            break
        }
    }
    
    audioEngine.stop()
    inputNode.removeTap(onBus: 0)
    isDone = true
    semaphore.signal()
}

_ = semaphore.wait(timeout: .now() + 16.0)

if isSpeechDetected && FileManager.default.fileExists(atPath: outputURL.path) {
    print("AUDIO_READY")
} else {
    print("SILENCE")
}
