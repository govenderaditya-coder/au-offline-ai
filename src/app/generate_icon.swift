import Cocoa

let size = 1024
let img = NSImage(size: NSSize(width: size, height: size))
img.lockFocus()

let ctx = NSGraphicsContext.current!.cgContext

// Background squircle (macOS Big Sur+ style rounded rect)
let rect = CGRect(x: 80, y: 80, width: 864, height: 864)
let path = CGPath(roundedRect: rect, cornerWidth: 200, cornerHeight: 200, transform: nil)

// Shadow
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -20), blur: 40, color: CGColor(gray: 0, alpha: 0.35))
ctx.addPath(path)
ctx.setFillColor(CGColor(red: 0.1, green: 0.12, blue: 0.18, alpha: 1.0))
ctx.fillPath()
ctx.restoreGState()

// Gradient fill
let colorSpace = CGColorSpaceCreateDeviceRGB()
let colors = [
    CGColor(red: 0.12, green: 0.14, blue: 0.22, alpha: 1.0),
    CGColor(red: 0.05, green: 0.06, blue: 0.10, alpha: 1.0)
] as CFArray
let gradient = CGGradient(colorsSpace: colorSpace, colors: colors, locations: [0.0, 1.0])!
ctx.saveGState()
ctx.addPath(path)
ctx.clip()
ctx.drawLinearGradient(gradient, start: CGPoint(x: 512, y: 944), end: CGPoint(x: 512, y: 80), options: [])

// Glowing ring / accent (AU - Gold / Cyan glow)
let ringRect = CGRect(x: 200, y: 200, width: 624, height: 624)
let ringPath = CGPath(ellipseIn: ringRect, transform: nil)
ctx.setStrokeColor(CGColor(red: 0.95, green: 0.77, blue: 0.25, alpha: 0.8)) // Gold
ctx.setLineWidth(14)
ctx.addPath(ringPath)
ctx.strokePath()

// Inner core glow
let coreRect = CGRect(x: 240, y: 240, width: 544, height: 544)
let corePath = CGPath(ellipseIn: coreRect, transform: nil)
ctx.setStrokeColor(CGColor(red: 0.3, green: 0.65, blue: 1.0, alpha: 0.4))
ctx.setLineWidth(6)
ctx.addPath(corePath)
ctx.strokePath()

// Text "AU"
let font = NSFont.systemFont(ofSize: 260, weight: .heavy)
let paragraphStyle = NSMutableParagraphStyle()
paragraphStyle.alignment = .center

let textAttrs: [NSAttributedString.Key: Any] = [
    .font: font,
    .foregroundColor: NSColor(red: 0.98, green: 0.82, blue: 0.30, alpha: 1.0), // Gold
    .paragraphStyle: paragraphStyle
]

let str = NSAttributedString(string: "AU", attributes: textAttrs)
let strRect = CGRect(x: 80, y: 380, width: 864, height: 300)
str.draw(in: strRect)

// Subtitle "OFFLINE AI"
let subFont = NSFont.systemFont(ofSize: 52, weight: .bold)
let subAttrs: [NSAttributedString.Key: Any] = [
    .font: subFont,
    .foregroundColor: NSColor(red: 0.7, green: 0.75, blue: 0.85, alpha: 0.9),
    .paragraphStyle: paragraphStyle
]
let subStr = NSAttributedString(string: "OFFLINE AI", attributes: subAttrs)
let subRect = CGRect(x: 80, y: 310, width: 864, height: 70)
subStr.draw(in: subRect)

ctx.restoreGState()

img.unlockFocus()

if let tiffData = img.tiffRepresentation,
   let bitmap = NSBitmapImageRep(data: tiffData),
   let pngData = bitmap.representation(using: .png, properties: [:]) {
    try! pngData.write(to: URL(fileURLWithPath: "/tmp/au_1024.png"))
    print("PNG generated successfully")
}
