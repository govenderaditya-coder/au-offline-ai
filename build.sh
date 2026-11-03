#!/bin/bash
# ============================================================
#  Build Script for AU Offline AI Native Binaries
# ============================================================
set -e

echo "🔨 Building AU Native App and Tools..."

# 1. Compile au-podcast-builder
echo "🎙️ Compiling au-podcast-builder..."
mkdir -p tools
swiftc -O src/podcast_builder/main.swift -o tools/au-podcast-builder -framework AVFoundation
chmod +x tools/au-podcast-builder
echo "✅ au-podcast-builder compiled!"

# 2. Generate Icon
echo "🎨 Generating App Icon..."
mkdir -p /tmp/AU.iconset
swiftc src/app/generate_icon.swift -o /tmp/generate_icon
/tmp/generate_icon
sips -z 16 16     /tmp/au_1024.png --out /tmp/AU.iconset/icon_16x16.png >/dev/null
sips -z 32 32     /tmp/au_1024.png --out /tmp/AU.iconset/icon_16x16@2x.png >/dev/null
sips -z 32 32     /tmp/au_1024.png --out /tmp/AU.iconset/icon_32x32.png >/dev/null
sips -z 64 64     /tmp/au_1024.png --out /tmp/AU.iconset/icon_32x32@2x.png >/dev/null
sips -z 128 128   /tmp/au_1024.png --out /tmp/AU.iconset/icon_128x128.png >/dev/null
sips -z 256 256   /tmp/au_1024.png --out /tmp/AU.iconset/icon_128x128@2x.png >/dev/null
sips -z 256 256   /tmp/au_1024.png --out /tmp/AU.iconset/icon_256x256.png >/dev/null
sips -z 512 512   /tmp/au_1024.png --out /tmp/AU.iconset/icon_256x256@2x.png >/dev/null
sips -z 512 512   /tmp/au_1024.png --out /tmp/AU.iconset/icon_512x512.png >/dev/null
sips -z 1024 1024 /tmp/au_1024.png --out /tmp/AU.iconset/icon_512x512@2x.png >/dev/null
iconutil -c icns /tmp/AU.iconset -o /tmp/AppIcon.icns
echo "✅ AppIcon.icns created!"

# 3. Compile AU.app
echo "🖥️ Compiling AU native macOS application..."
APP_DIR="AU.app"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

swiftc -O src/app/main.swift -o "$APP_DIR/Contents/MacOS/AU" -framework Cocoa -framework WebKit
chmod +x "$APP_DIR/Contents/MacOS/AU"

cp /tmp/AppIcon.icns "$APP_DIR/Contents/Resources/AppIcon.icns"
cp src/app/Info.plist "$APP_DIR/Contents/Info.plist"

touch "$APP_DIR"
echo "✅ AU.app built successfully!"
echo "🎉 Build finished!"
