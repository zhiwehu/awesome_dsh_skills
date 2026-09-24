import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOf: URL(fileURLWithPath: path)),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("ERROR: cannot load\n".data(using: .utf8)!); exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try? handler.perform([request])
for obs in (request.results ?? []) {
    if let top = obs.topCandidates(1).first {
        let b = obs.boundingBox
        let W = Double(cg.width), H = Double(cg.height)
        let rect = String(format: "[%.0f,%.0f,%.0f,%.0f]", b.origin.x * W, (1 - b.origin.y - b.height) * H, b.width * W, b.height * H)
        print("\(rect)\t\(top.string)")
    }
}
