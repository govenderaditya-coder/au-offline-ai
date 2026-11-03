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

let lines = content.components(separatedBy: .newlines)
let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try? FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

var audioFiles: [URL] = []
var step = 0

print("🎙️ Synthesizing podcast dialogue...")

for rawLine in lines {
    let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
    if line.isEmpty { continue }

    var voice = "Samantha"
    var dialogue = line

    if line.lowercased().hasPrefix("samantha:") {
        voice = "Samantha"
        dialogue = String(line.dropFirst(9)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("daniel:") {
        voice = "Daniel"
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("host 1:") {
        voice = "Samantha"
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    } else if line.lowercased().hasPrefix("host 2:") {
        voice = "Daniel"
        dialogue = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
    }

    if dialogue.isEmpty { continue }

    step += 1
    let lineFile = tempDir.appendingPathComponent("line_\(step).m4a")

    let process = Process()
    process.launchPath = "/usr/bin/say"
    process.arguments = ["-v", voice, "-o", lineFile.path, dialogue]
    process.launch()
    process.waitUntilExit()

    if FileManager.default.fileExists(atPath: lineFile.path) {
        audioFiles.append(lineFile)
        print("  [\(step)] \(voice): \(dialogue.prefix(40))...")
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
