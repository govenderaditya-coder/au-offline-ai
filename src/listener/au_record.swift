import Foundation
import AVFoundation

let args = CommandLine.arguments
let targetPath = args.count > 1 ? args[1] : "/tmp/au_speech.wav"
let outputURL = URL(fileURLWithPath: targetPath)

try? FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
try? FileManager.default.removeItem(at: outputURL)

let audioEngine = AVAudioEngine()
let inputNode = audioEngine.inputNode
let recordingFormat = inputNode.outputFormat(forBus: 0)

guard let audioFile = try? AVAudioFile(forWriting: outputURL, settings: recordingFormat.settings) else {
    fputs("ERROR: Cannot create audio file at \(targetPath)\n", stderr)
    exit(1)
}

var isSpeechDetected = false
var lastSpeechTime = Date()
let startTime = Date()
var isDone = false
let semaphore = DispatchSemaphore(value: 0)

// Sensitive speech threshold calibrated for Mac microphone
let speechThreshold: Float = 0.008

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
            fputs("[STATE:HEARING]\n", stderr)
        }
        lastSpeechTime = Date()
    }
    
    if isSpeechDetected {
        try? audioFile.write(from: buffer)
    }
}

do {
    try audioEngine.start()
    fputs("[STATE:LISTENING]\n", stderr)
} catch {
    fputs("ERROR: Cannot start audio engine: \(error)\n", stderr)
    exit(1)
}

DispatchQueue.global().async {
    while !isDone {
        Thread.sleep(forTimeInterval: 0.08)
        let now = Date()
        
        // If speaking and paused for 1.1s, finalize capture
        if isSpeechDetected && now.timeIntervalSince(lastSpeechTime) > 1.1 {
            break
        }
        
        // If no speech heard after 4.5 seconds, cycle
        if !isSpeechDetected && now.timeIntervalSince(startTime) > 4.5 {
            break
        }
        
        // Safety cap: 15 seconds
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
