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

func configuredVoiceMode() -> String {
    let configPath = NSString(string: "~/.offline-ai/voice_config.json").expandingTildeInPath
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: configPath)),
          let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let mode = config["voice_gender"] as? String else { return "female" }
    return mode
}

func findBestVoice(for mode: String) -> AVSpeechSynthesisVoice? {
    let voices = AVSpeechSynthesisVoice.speechVoices()
    if mode == "male" { return voices.first(where: { $0.name == "Daniel" }) ?? AVSpeechSynthesisVoice(language: "en-US") }
    if mode == "cloned" {
        return voices.first(where: { $0.voiceTraits.contains(.isPersonalVoice) || $0.name.lowercased().contains("ai female") })
            ?? voices.first(where: { $0.name == "Samantha" })
    }
    // Female means a normal system voice. A Personal Voice is opt-in only via Cloned.
    return voices.first(where: { $0.name == "Samantha" })
        ?? voices.first(where: { $0.language == "en-US" && !$0.voiceTraits.contains(.isPersonalVoice) })
}

let voiceMode = configuredVoiceMode()
let voice = findBestVoice(for: voiceMode)
let isPersonal = voiceMode == "cloned" && (voice?.voiceTraits.contains(.isPersonalVoice) ?? false || (voice?.name.lowercased().contains("ai female") ?? false))

fputs("🗣️ [AU Voice: \(voice?.name ?? "Default")\(isPersonal ? " ⭐ (YOUR CLONED VOICE)" : "")]\n", stderr)

let utterance = AVSpeechUtterance(string: textToSpeak)
utterance.voice = voice
utterance.rate = 0.51  // Natural conversational speed
utterance.pitchMultiplier = 1.0

synthesizer.speak(utterance)
_ = delegate.semaphore.wait(timeout: .now() + 60.0)
