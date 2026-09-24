import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOf: URL(fileURLWithPath: path)),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("ERROR: cannot load \(path)\n".data(using: .utf8)!); exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do { try handler.perform([request]) } catch {
    FileHandle.standardError.write("ERROR: \(error)\n".data(using: .utf8)!); exit(1)
}
for obs in (request.results ?? []) {
    if let top = obs.topCandidates(1).first {
        print(top.string)
    }
}
