// อ่านข้อความในภาพด้วย Vision ของ macOS (ไม่ต้องลง tesseract) -- ใช้อ่านเวลาที่มุมขวาล่างของภาพเรดาร์
// ใช้: ocr_time <image> [x y w h]   (crop เป็น pixel, จุดเริ่มมุมซ้ายบน) -- พิมพ์ข้อความทีละบรรทัด
// build: swiftc -O ocr_time.swift -o ocr_time   (frames.py build ให้เองครั้งแรก ~40 วินาที)
import AppKit
import Foundation
import Vision

let a = CommandLine.arguments
guard a.count >= 2, let img = NSImage(contentsOfFile: a[1]),
      var cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(2) }
if a.count >= 6, let x = Int(a[2]), let y = Int(a[3]), let w = Int(a[4]), let h = Int(a[5]),
   let c = cg.cropping(to: CGRect(x: x, y: y, width: w, height: h)) { cg = c }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
for o in req.results ?? [] { if let t = o.topCandidates(1).first { print(t.string) } }
