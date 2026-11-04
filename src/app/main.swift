import Cocoa
import WebKit
import AVFoundation

class AUApplicationDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, NSToolbarDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var loadingView: NSView!
    var spinner: NSProgressIndicator!
    var statusLabel: NSTextField!
    var retryTimer: Timer?

    // Independent Voice Assistant Process & UI
    var assistantProcess: Process?
    var isAssistantActive = false
    var voiceToolbarButton: NSButton?
    var assistantBanner: NSView?
    var bannerLabel: NSTextField?
    var bannerStopButton: NSButton?

    func applicationDidFinishLaunching(_ aNotification: Notification) {
        setupMenu()
        ensureBackendRunning()

        if #available(macOS 14.0, *) {
            AVSpeechSynthesizer.requestPersonalVoiceAuthorization { status in
                DispatchQueue.main.async {
                    switch status {
                    case .authorized:
                        print("✅ Personal Voice authorized for AU!")
                    case .denied:
                        print("ℹ️ Personal Voice access awaiting permission or toggle in System Settings.")
                    default:
                        break
                    }
                }
            }
        }

        let windowSize = NSSize(width: 1280, height: 860)
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(origin: .zero, size: windowSize)
        let origin = NSPoint(
            x: screenRect.midX - windowSize.width / 2,
            y: screenRect.midY - windowSize.height / 2
        )
        let windowRect = NSRect(origin: origin, size: windowSize)

        window = NSWindow(
            contentRect: windowRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "AU — Offline AI & Personal Assistant"
        window.center()
        window.minSize = NSSize(width: 850, height: 600)
        window.titlebarAppearsTransparent = false
        window.backgroundColor = NSColor(red: 0.08, green: 0.09, blue: 0.12, alpha: 1.0)
        window.isMovableByWindowBackground = false

        setupToolbar()

        let config = WKWebViewConfiguration()
        let prefs = WKWebpagePreferences()
        prefs.allowsContentJavaScript = true
        config.defaultWebpagePreferences = prefs
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        let container = NSView(frame: NSRect(origin: .zero, size: windowSize))
        container.autoresizingMask = [.width, .height]
        window.contentView = container

        // Web view
        webView = WKWebView(frame: container.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        container.addSubview(webView)

        setupAssistantBanner(in: container, windowSize: windowSize)

        // Loading Overlay
        loadingView = NSView(frame: container.bounds)
        loadingView.autoresizingMask = [.width, .height]
        loadingView.wantsLayer = true
        loadingView.layer?.backgroundColor = CGColor(red: 0.08, green: 0.09, blue: 0.12, alpha: 1.0)
        container.addSubview(loadingView)

        spinner = NSProgressIndicator(frame: NSRect(x: (windowSize.width - 36)/2, y: windowSize.height/2 + 20, width: 36, height: 36))
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.isDisplayedWhenStopped = false
        spinner.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        spinner.startAnimation(nil)
        loadingView.addSubview(spinner)

        statusLabel = NSTextField(labelWithString: "Starting AU Offline AI Engine...")
        statusLabel.font = NSFont.systemFont(ofSize: 15, weight: .medium)
        statusLabel.textColor = NSColor(red: 0.90, green: 0.80, blue: 0.40, alpha: 1.0)
        statusLabel.alignment = .center
        statusLabel.frame = NSRect(x: 20, y: windowSize.height/2 - 30, width: windowSize.width - 40, height: 26)
        statusLabel.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        loadingView.addSubview(statusLabel)

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        loadAU()
    }

    // MARK: - Banner Setup (Displays Assistant Status)
    func setupAssistantBanner(in container: NSView, windowSize: NSSize) {
        let bannerHeight: CGFloat = 40
        let banner = NSView(frame: NSRect(x: 0, y: windowSize.height - bannerHeight, width: windowSize.width, height: bannerHeight))
        banner.autoresizingMask = [.width, .minYMargin]
        banner.wantsLayer = true
        banner.layer?.backgroundColor = CGColor(red: 0.12, green: 0.14, blue: 0.20, alpha: 0.95)
        banner.isHidden = true
        self.assistantBanner = banner

        let label = NSTextField(labelWithString: "🟢 Personal Voice Assistant is active across your Mac — speak commands anytime.")
        label.font = NSFont.systemFont(ofSize: 13, weight: .medium)
        label.textColor = NSColor(red: 0.4, green: 0.9, blue: 0.5, alpha: 1.0)
        label.frame = NSRect(x: 20, y: 8, width: windowSize.width - 150, height: 24)
        label.autoresizingMask = [.width, .minYMargin]
        banner.addSubview(label)
        self.bannerLabel = label

        let stopBtn = NSButton(title: "Stop Assistant", target: self, action: #selector(toggleVoiceAssistant))
        stopBtn.bezelStyle = .inline
        stopBtn.frame = NSRect(x: windowSize.width - 120, y: 8, width: 100, height: 24)
        stopBtn.autoresizingMask = [.minXMargin, .minYMargin]
        banner.addSubview(stopBtn)
        self.bannerStopButton = stopBtn

        container.addSubview(banner)
    }

    // MARK: - Independent Voice Assistant Controller
    @objc func toggleVoiceAssistant() {
        if isAssistantActive {
            stopVoiceAssistant()
        } else {
            startVoiceAssistant()
        }
    }

    func startVoiceAssistant() {
        let pythonPath = "/Users/aditya/.local/share/uv/tools/open-webui/bin/python"
        let scriptPath = "/Users/aditya/Downloads/offline ai/au_voice_assistant.py"

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [scriptPath]
        process.environment = ProcessInfo.processInfo.environment

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        do {
            try process.run()
            self.assistantProcess = process
            self.isAssistantActive = true
            updateAssistantUI(active: true)

            pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if let str = String(data: data, encoding: .utf8), !str.isEmpty {
                    DispatchQueue.main.async {
                        self?.handleAssistantLog(str)
                    }
                }
            }
        } catch {
            print("Failed to run assistant: \(error)")
        }
    }

    func stopVoiceAssistant() {
        if let process = assistantProcess, process.isRunning {
            process.terminate()
        }
        assistantProcess = nil
        isAssistantActive = false
        updateAssistantUI(active: false)
    }

    func updateAssistantUI(active: Bool) {
        if active {
            voiceToolbarButton?.title = " Assistant: ACTIVE"
            voiceToolbarButton?.image = NSImage(systemSymbolName: "waveform.circle.fill", accessibilityDescription: "Active")
            assistantBanner?.isHidden = false
        } else {
            voiceToolbarButton?.title = " Start Assistant"
            voiceToolbarButton?.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Mic")
            assistantBanner?.isHidden = true
        }
    }

    func handleAssistantLog(_ log: String) {
        if log.contains("[YOU SAID]:") {
            let clean = log.components(separatedBy: "[YOU SAID]:").last?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            bannerLabel?.stringValue = "🎙️ Heard: \(clean)"
        } else if log.contains("[AU SPEAKING]:") {
            let clean = log.components(separatedBy: "[AU SPEAKING]:").last?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            bannerLabel?.stringValue = "🤖 AU: \(clean)"
        }
    }

    // MARK: - Podcast Studio Action
    @objc func generatePodcast() {
        let scriptPath = "/Users/aditya/Downloads/offline ai/make-podcast.sh"
        let task = Process()
        task.launchPath = "/bin/bash"
        task.arguments = [scriptPath]
        try? task.run()
    }

    @objc func openPodcastsFolder() {
        let path = NSString(string: "~/Downloads/offline ai/podcasts").expandingTildeInPath
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    // MARK: - Personal Voice Actions
    @objc func testPersonalVoice() {
        DispatchQueue.global(qos: .userInitiated).async {
            speakWithPersonalVoice(text: "Hello Aditya! Your AI female personal voice is now connected to AU.")
        }
    }

    @objc func showPersonalVoiceGuide() {
        let alert = NSAlert()
        alert.messageText = "Personal Voice Setup (AI female)"
        alert.informativeText = """
        To ensure your cloned 'AI female' voice works seamlessly across AU:

        1. In System Settings → Accessibility → Personal Voice:
           Ensure 'Allow apps to request to use' is toggled ON.
           (If the voice still says 'Generating', plug in power and lock your screen).

        2. In System Settings → Accessibility → Spoken Content:
           Set 'System Voice' to 'AI female'. This makes it the system-wide default voice.
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Open Personal Voice Settings")
        alert.addButton(withTitle: "Open Spoken Content")
        alert.addButton(withTitle: "Done")
        alert.beginSheetModal(for: self.window) { response in
            if response == .alertFirstButtonReturn {
                if let url = URL(string: "x-apple.systempreferences:com.apple.preference.universalaccess?PersonalVoice") {
                    NSWorkspace.shared.open(url)
                }
            } else if response == .alertSecondButtonReturn {
                if let url = URL(string: "x-apple.systempreferences:com.apple.preference.universalaccess?SpokenContent") {
                    NSWorkspace.shared.open(url)
                }
            }
        }
    }

    // MARK: - NSToolbarDelegate
    func setupToolbar() {
        let toolbar = NSToolbar(identifier: "AUToolbar")
        toolbar.delegate = self
        toolbar.displayMode = .iconAndLabel
        window.toolbar = toolbar
    }

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        return [
            NSToolbarItem.Identifier("VoiceAssistantItem"),
            NSToolbarItem.Identifier("PodcastItem"),
            .flexibleSpace,
            NSToolbarItem.Identifier("OpenPodcastsItem"),
            NSToolbarItem.Identifier("StatusItem")
        ]
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        return toolbarDefaultItemIdentifiers(toolbar)
    }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier itemIdentifier: NSToolbarItem.Identifier, willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        if itemIdentifier.rawValue == "VoiceAssistantItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "Personal Assistant"
            item.paletteLabel = "Personal Assistant"
            item.toolTip = "Toggle independent hands-free Mac automation assistant"

            let btn = NSButton(title: " Start Assistant", target: self, action: #selector(toggleVoiceAssistant))
            btn.bezelStyle = .rounded
            btn.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Mic")
            btn.imagePosition = .imageLeading
            voiceToolbarButton = btn
            item.view = btn
            return item
        } else if itemIdentifier.rawValue == "PodcastItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "Audio Podcast"
            item.paletteLabel = "Audio Podcast"
            item.toolTip = "Synthesize two-host audio podcast (.m4a) from current chat notes"

            let btn = NSButton(title: " Make Podcast", target: self, action: #selector(generatePodcast))
            btn.bezelStyle = .rounded
            btn.image = NSImage(systemSymbolName: "headphones", accessibilityDescription: "Podcast")
            btn.imagePosition = .imageLeading
            item.view = btn
            return item
        } else if itemIdentifier.rawValue == "OpenPodcastsItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "Saved Audio"
            item.paletteLabel = "Saved Audio"
            item.toolTip = "Open podcasts archive in Finder"

            let btn = NSButton(title: " Saved Audio", target: self, action: #selector(openPodcastsFolder))
            btn.bezelStyle = .rounded
            btn.image = NSImage(systemSymbolName: "folder.fill", accessibilityDescription: "Folder")
            btn.imagePosition = .imageLeading
            item.view = btn
            return item
        } else if itemIdentifier.rawValue == "StatusItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            let label = NSTextField(labelWithString: "🟢 M4 Metal Engine")
            label.font = NSFont.systemFont(ofSize: 11, weight: .semibold)
            label.textColor = NSColor.secondaryLabelColor
            item.view = label
            return item
        }
        return nil
    }

    // MARK: - Backend Verification
    func ensureBackendRunning() {
        let task = Process()
        task.launchPath = "/bin/bash"
        task.arguments = ["-c", """
        export PATH="/Users/aditya/.local/bin:/opt/homebrew/bin:$PATH"
        if ! pgrep -x "ollama" &>/dev/null; then
            brew services start ollama
        fi
        if ! lsof -i :8080 &>/dev/null; then
            nohup /Users/aditya/.local/bin/open-webui serve > ~/.offline-ai/webui.log 2>&1 &
        fi
        """]
        try? task.run()
    }

    func loadAU() {
        guard let url = URL(string: "http://127.0.0.1:8080") else { return }
        let request = URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 5)
        webView.load(request)
    }

    // MARK: - WKUIDelegate & Permissions
    @available(macOS 12.0, *)
    func webView(
        _ webView: WKWebView,
        requestMediaCapturePermissionFor origin: WKSecurityOrigin,
        initiatedByFrame frame: WKFrameInfo,
        type: WKMediaCaptureType,
        decisionHandler: @escaping (WKPermissionDecision) -> Void
    ) {
        decisionHandler(.grant)
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        let openPanel = NSOpenPanel()
        openPanel.canChooseFiles = true
        openPanel.canChooseDirectories = parameters.allowsDirectories
        openPanel.allowsMultipleSelection = parameters.allowsMultipleSelection
        openPanel.resolvesAliases = true
        openPanel.prompt = "Upload"

        openPanel.beginSheetModal(for: self.window) { response in
            if response == .OK {
                completionHandler(openPanel.urls)
            } else {
                completionHandler(nil)
            }
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.alertStyle = .informational
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: self.window) { _ in
            completionHandler()
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: self.window) { response in
            completionHandler(response == .alertFirstButtonReturn)
        }
    }

    // MARK: - WKNavigationDelegate
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        retryTimer?.invalidate()
        retryTimer = nil
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.3
            self.loadingView.animator().alphaValue = 0.0
        }, completionHandler: {
            self.loadingView.isHidden = true
            self.spinner.stopAnimation(nil)
        })
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        statusLabel.stringValue = "Connecting to AU brain..."
        loadingView.isHidden = false
        loadingView.alphaValue = 1.0
        spinner.startAnimation(nil)

        retryTimer?.invalidate()
        retryTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: false) { [weak self] _ in
            self?.loadAU()
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.navigationType == .linkActivated,
           let url = navigationAction.request.url,
           let host = url.host,
           host != "127.0.0.1" && host != "localhost" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    @objc func reloadPage() {
        webView.reload()
    }

    @objc func toggleFullScreen() {
        window.toggleFullScreen(nil)
    }

    func setupMenu() {
        let mainMenu = NSMenu()

        // App Menu
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenuItem.submenu = appMenu
        appMenu.addItem(withTitle: "About AU", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Hide AU", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthersItem = appMenu.addItem(withTitle: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthersItem.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit AU", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        // Assistant Menu
        let assistantMenuItem = NSMenuItem()
        mainMenu.addItem(assistantMenuItem)
        let assistantMenu = NSMenu(title: "Assistant")
        assistantMenuItem.submenu = assistantMenu
        assistantMenu.addItem(withTitle: "Toggle Voice Assistant", action: #selector(toggleVoiceAssistant), keyEquivalent: "A")
        assistantMenu.addItem(withTitle: "Make Audio Podcast", action: #selector(generatePodcast), keyEquivalent: "P")
        assistantMenu.addItem(withTitle: "Open Saved Podcasts", action: #selector(openPodcastsFolder), keyEquivalent: "O")
        assistantMenu.addItem(NSMenuItem.separator())
        assistantMenu.addItem(withTitle: "Test Personal Voice (AI female)", action: #selector(testPersonalVoice), keyEquivalent: "T")
        assistantMenu.addItem(withTitle: "Personal Voice Settings...", action: #selector(showPersonalVoiceGuide), keyEquivalent: "")

        // Edit Menu
        let editMenuItem = NSMenuItem()
        mainMenu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "Edit")
        editMenuItem.submenu = editMenu
        editMenu.addItem(withTitle: "Undo", action: #selector(UndoManager.undo), keyEquivalent: "z")
        editMenu.addItem(withTitle: "Redo", action: #selector(UndoManager.redo), keyEquivalent: "Z")
        editMenu.addItem(NSMenuItem.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        // View Menu
        let viewMenuItem = NSMenuItem()
        mainMenu.addItem(viewMenuItem)
        let viewMenu = NSMenu(title: "View")
        viewMenuItem.submenu = viewMenu
        viewMenu.addItem(withTitle: "Reload", action: #selector(reloadPage), keyEquivalent: "r")
        viewMenu.addItem(withTitle: "Toggle Full Screen", action: #selector(toggleFullScreen), keyEquivalent: "f")

        // Window Menu
        let windowMenuItem = NSMenuItem()
        mainMenu.addItem(windowMenuItem)
        let windowMenu = NSMenu(title: "Window")
        windowMenuItem.submenu = windowMenu
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")

        NSApp.mainMenu = mainMenu
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopVoiceAssistant()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

// MARK: - Voice Synthesis Helper
class SpeakerDelegate: NSObject, AVSpeechSynthesizerDelegate {
    let sem = DispatchSemaphore(value: 0)
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        sem.signal()
    }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        sem.signal()
    }
}

func isVoiceClonedOrPersonal(_ voice: AVSpeechSynthesisVoice?) -> Bool {
    guard let voice = voice else { return false }
    if voice.name.lowercased().contains("ai female") || voice.name.lowercased() == "ai female" {
        return true
    }
    if #available(macOS 14.0, *) {
        return voice.voiceTraits.contains(.isPersonalVoice)
    }
    return false
}

func speakWithPersonalVoice(text: String) {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty { return }

    let synthesizer = AVSpeechSynthesizer()
    let delegate = SpeakerDelegate()
    synthesizer.delegate = delegate

    let voices = AVSpeechSynthesisVoice.speechVoices()
    var selectedVoice: AVSpeechSynthesisVoice? = nil

    // 1. Look for AI female or Personal Voice
    for v in voices {
        if isVoiceClonedOrPersonal(v) {
            selectedVoice = v
            break
        }
    }

    // 2. Look for female / aditya voice
    if selectedVoice == nil {
        for v in voices {
            let nameLower = v.name.lowercased()
            if nameLower.contains("female") || nameLower.contains("aditya") {
                selectedVoice = v
                break
            }
        }
    }

    // 3. Fallback to Samantha
    if selectedVoice == nil {
        selectedVoice = voices.first(where: { $0.name == "Samantha" }) ?? AVSpeechSynthesisVoice(language: "en-US")
    }

    let isPersonal = isVoiceClonedOrPersonal(selectedVoice)
    fputs("🗣️ [AU Voice: \(selectedVoice?.name ?? "Default")\(isPersonal ? " ⭐ (YOUR CLONED PERSONAL VOICE)" : "")]\n", stderr)

    let utterance = AVSpeechUtterance(string: trimmed)
    utterance.voice = selectedVoice
    utterance.rate = 0.51
    utterance.pitchMultiplier = 1.0

    synthesizer.speak(utterance)
    _ = delegate.sem.wait(timeout: .now() + 120.0)
}

// MARK: - CLI Mode Dispatcher
if CommandLine.arguments.contains("--speak") {
    if let idx = CommandLine.arguments.firstIndex(of: "--speak"), idx + 1 < CommandLine.arguments.count {
        let textToSpeak = CommandLine.arguments[(idx + 1)...].joined(separator: " ")
        speakWithPersonalVoice(text: textToSpeak)
        exit(0)
    }
}

if CommandLine.arguments.contains("--list-voices") {
    let voices = AVSpeechSynthesisVoice.speechVoices()
    print("Total voices available: \(voices.count)")
    for v in voices {
        let isPersonal = isVoiceClonedOrPersonal(v)
        print("- \(v.name) (\(v.language))\(isPersonal ? " ⭐ [PERSONAL VOICE]" : "")")
    }
    exit(0)
}

let app = NSApplication.shared
let delegate = AUApplicationDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
