import Foundation
import AVFoundation

let args = CommandLine.arguments
if args.count < 3 {
    print("Usage: au-podcast-builder <input_script.txt> <output.m4a>")
    exit(1)
}

let inputFile = args[1]
let outputFile = URL(fileURLWithPath: args[2])

guard let content = try? String(contentsOfFile: inputFile, encoding: .utf8) else {
    print("Error reading input file: \(inputFile)")
    exit(1)
}

let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
let clonedVoiceWav = "\(homeDir)/Downloads/offline ai/voice_profile/my_voice.wav"
let clonedVoiceTxt = "\(homeDir)/Downloads/offline ai/voice_profile/my_voice.txt"
let clonerPython = "\(homeDir)/Downloads/offline ai/.venv-cloner/bin/python"
let hasClonedVoice = FileManager.default.fileExists(atPath: clonedVoiceWav)

func getHost1Voice() -> String {
    if hasClonedVoice {
        return "Aditya (Cloned Voice)"
    }
    let task = Process()
    task.launchPath = "/usr/bin/say"
    task.arguments = ["-v", "?"]
    let pipe = Pipe()
    task.standardOutput = pipe
    try? task.run()
    task.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    if let out = String(data: data, encoding: .utf8) {
        for l in out.components(separatedBy: .newlines) {
            let lower = l.lowercased()
            if lower.contains("ai female") || lower.contains("aditya") || lower.contains("personal") {
                let parts = l.components(separatedBy: .whitespaces)
                if let name = parts.first, !name.isEmpty {
                    return name
                }
            }
        }
    }
    return "Samantha"
}

let host1Voice = getHost1Voice()
let host2Voice = "Daniel"

let lines = content.components(separatedBy: .newlines)
let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try? FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

var audioFiles: [URL] = []
var step = 0

print("🎙️ Synthesizing podcast dialogue (Host 1: \(host1Voice), Host 2: \(host2Voice))...")

for rawLine in lines {
    let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
    if line.isEmpty { continue }

    var isHost1 = true
    var dialogue = line

    if line.lowercased().hasPrefix("aditya:") {
        isHost1 = true
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("samantha:") {
        isHost1 = true
        dialogue = String(line.dropFirst(9)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("daniel:") {
        isHost1 = false
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("host 1:") {
        isHost1 = true
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("host 2:") {
        isHost1 = false
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    }

    if dialogue.isEmpty { continue }

    step += 1
    let lineExt = (isHost1 && hasClonedVoice) ? "wav" : "m4a"
    let lineFile = tempDir.appendingPathComponent("line_\(step).\(lineExt)")

    if isHost1 && hasClonedVoice {
        var refText = "Hello, this is my personal AI assistant AU running offline on my Mac."
        if let savedText = try? String(contentsOfFile: clonedVoiceTxt, encoding: .utf8) {
            let t = savedText.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { refText = t }
        }

        let process = Process()
        process.launchPath = clonerPython
        process.arguments = [
            "-m", "f5_tts_mlx.generate",
            "--text", dialogue,
            "--ref-audio", clonedVoiceWav,
            "--ref-text", refText,
            "--steps", "16",
            "--q", "8",
            "--output", lineFile.path
        ]
        process.launch()
        process.waitUntilExit()
    } else {
        let voiceName = isHost1 ? (host1Voice == "Aditya (Cloned Voice)" ? "Samantha" : host1Voice) : host2Voice
        let process = Process()
        process.launchPath = "/usr/bin/say"
        process.arguments = ["-v", voiceName, "-o", lineFile.path, dialogue]
        process.launch()
        process.waitUntilExit()
    }

    if FileManager.default.fileExists(atPath: lineFile.path) {
        audioFiles.append(lineFile)
        let speakerName = isHost1 ? host1Voice : host2Voice
        print("  [\(step)] \(speakerName): \(dialogue.prefix(40))...")
    }
}

if audioFiles.isEmpty {
    print("No dialogue lines processed.")
    exit(1)
}

print("🎶 Assembling final podcast audio...")

let composition = AVMutableComposition()
guard let compositionTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else {
    print("Failed to create audio composition track")
    exit(1)
}

var currentTime = CMTime.zero

for fileURL in audioFiles {
    let asset = AVURLAsset(url: fileURL)
    guard let assetTrack = asset.tracks(withMediaType: .audio).first else { continue }
    let timeRange = CMTimeRange(start: .zero, duration: asset.duration)
    do {
        try compositionTrack.insertTimeRange(timeRange, of: assetTrack, at: currentTime)
        currentTime = CMTimeAdd(currentTime, asset.duration)
    } catch {
        print("Error stitching: \(error)")
    }
}

guard let exportSession = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetAppleM4A) else {
    print("Failed to initialize export session")
    exit(1)
}

try? FileManager.default.removeItem(at: outputFile)
exportSession.outputURL = outputFile
exportSession.outputFileType = .m4a

let semaphore = DispatchSemaphore(value: 0)
var success = false

exportSession.exportAsynchronously {
    success = (exportSession.status == .completed)
    semaphore.signal()
}

_ = semaphore.wait(timeout: .distantFuture)
try? FileManager.default.removeItem(at: tempDir)

if success {
    print("✅ Podcast generated successfully at: \(outputFile.path)")
    exit(0)
} else {
    print("Failed to export podcast: \(String(describing: exportSession.error))")
    exit(1)
}
