import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count == 2,
      let image = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write(Data("Unable to load image\n".utf8)); exit(2)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["en-US"]
do {
    try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
    let observations = request.results ?? []
    let boxes: [[String: Any]] = observations.compactMap { observation in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return ["text": candidate.string, "confidence": candidate.confidence, "x": box.origin.x, "y": box.origin.y, "width": box.width, "height": box.height]
    }
    let scores = boxes.compactMap { $0["confidence"] as? Float }
    let output: [String: Any] = ["raw_text": boxes.compactMap { $0["text"] as? String }.joined(separator: "\n"), "confidence": scores.isEmpty ? 0 : scores.reduce(0, +) / Float(scores.count), "boxes": boxes, "engine": "macOS Vision"]
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: output))
} catch { FileHandle.standardError.write(Data("Vision OCR failed: \(error)\n".utf8)); exit(1) }
