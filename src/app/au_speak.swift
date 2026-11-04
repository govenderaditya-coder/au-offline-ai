import Foundation
import AVFoundation

let args = CommandLine.arguments
if args.count < 2 {
    exit(1)
}

let textToSpeak = args.dropFirst().joined(separator: " ")

class SpeakerDelegate: NSObject, AVSpeechSynthesizerDelegate {
    let semaphore = DispatchSemaphore(value: 0)

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        semaphore.signal()
    }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        semaphore.signal()
    }
}

let synthesizer = AVSpeechSynthesizer()
let delegate = SpeakerDelegate()
synthesizer.delegate = delegate

func findBestVoice() -> AVSpeechSynthesisVoice? {
    let voices = AVSpeechSynthesisVoice.speechVoices()
    
    // 1. Check for AI female or Personal Voice
    for v in voices {
        let nameLower = v.name.lowercased()
        if nameLower.contains("ai female") || nameLower == "ai female" || v.voiceTraits.contains(.isPersonalVoice) {
            return v
        }
    }
    
    // 2. Check for any voice named female or aditya
    for v in voices {
        let nameLower = v.name.lowercased()
        if nameLower.contains("female") || nameLower.contains("aditya") {
            return v
        }
    }
    
    // 3. Fallback to Samantha
    if let samantha = voices.first(where: { $0.name == "Samantha" }) {
        return samantha
    }
    
    return AVSpeechSynthesisVoice(language: "en-US")
}

let voice = findBestVoice()
let isPersonal = voice?.voiceTraits.contains(.isPersonalVoice) ?? false || (voice?.name.lowercased().contains("ai female") ?? false)

fputs("🗣️ [AU Voice: \(voice?.name ?? "Default")\(isPersonal ? " ⭐ (YOUR CLONED VOICE)" : "")]\n", stderr)

let utterance = AVSpeechUtterance(string: textToSpeak)
utterance.voice = voice
utterance.rate = 0.51  // Natural conversational speed
utterance.pitchMultiplier = 1.0

synthesizer.speak(utterance)
_ = delegate.semaphore.wait(timeout: .now() + 60.0)
