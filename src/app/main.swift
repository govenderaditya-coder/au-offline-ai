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
    var stateBadge: NSTextField?
    var statusDetailLabel: NSTextField?
    var bannerLabel: NSTextField?
    var voiceSegmentedControl: NSSegmentedControl?
    var bannerStopButton: NSButton?

    // Artifacts Drawer & Persona Engine
    var artifactsDrawer: NSView?
    var artifactsWebView: WKWebView?
    var isArtifactsDrawerOpen: Bool = false
    var personaSegmentedControl: NSSegmentedControl?

    // Hardware Telemetry & Export Engine
    var hardwareStatusLabel: NSTextField?
    var telemetryTimer: Timer?

    func applicationDidFinishLaunching(_ aNotification: Notification) {
        setupMenu()
        ensureBackendRunning()

        telemetryTimer = Timer.scheduledTimer(withTimeInterval: 4.0, repeats: true) { [weak self] _ in
            self?.updateHardwareTelemetry()
        }
        updateHardwareTelemetry()

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
        setupArtifactsDrawer(in: container, windowSize: windowSize)

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

    // MARK: - Banner Setup (Displays Assistant Status & Interactive Controls)
    func setupAssistantBanner(in container: NSView, windowSize: NSSize) {
        let bannerHeight: CGFloat = 76
        let banner = NSView(frame: NSRect(x: 0, y: windowSize.height - bannerHeight, width: windowSize.width, height: bannerHeight))
        banner.autoresizingMask = [.width, .minYMargin]
        banner.wantsLayer = true
        banner.layer?.backgroundColor = CGColor(red: 0.09, green: 0.11, blue: 0.16, alpha: 0.98)
        banner.layer?.borderWidth = 1
        banner.layer?.borderColor = CGColor(red: 0.18, green: 0.22, blue: 0.30, alpha: 0.8)
        banner.isHidden = true
        self.assistantBanner = banner

        // Row 1: State Badge (Left)
        let badge = NSTextField(labelWithString: " 🟢 LISTENING (Your Turn) ")
        badge.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        badge.textColor = NSColor(red: 0.35, green: 0.95, blue: 0.45, alpha: 1.0)
        badge.alignment = .center
        badge.wantsLayer = true
        badge.layer?.cornerRadius = 6
        badge.layer?.backgroundColor = CGColor(red: 0.12, green: 0.26, blue: 0.16, alpha: 0.9)
        badge.frame = NSRect(x: 16, y: 44, width: 200, height: 24)
        badge.autoresizingMask = [.minYMargin]
        banner.addSubview(badge)
        self.stateBadge = badge

        // Row 1: Status Detail (Center)
        let detail = NSTextField(labelWithString: "Microphone active — speak any command anytime.")
        detail.font = NSFont.systemFont(ofSize: 13, weight: .medium)
        detail.textColor = NSColor(red: 0.88, green: 0.90, blue: 0.96, alpha: 1.0)
        detail.frame = NSRect(x: 226, y: 44, width: max(200, windowSize.width - 550), height: 24)
        detail.autoresizingMask = [.width, .minYMargin]
        banner.addSubview(detail)
        self.statusDetailLabel = detail

        // Row 1: Voice Selector (Right)
        let voiceLabel = NSTextField(labelWithString: "Voice:")
        voiceLabel.font = NSFont.systemFont(ofSize: 12, weight: .medium)
        voiceLabel.textColor = NSColor.secondaryLabelColor
        voiceLabel.alignment = .right
        voiceLabel.frame = NSRect(x: windowSize.width - 325, y: 44, width: 45, height: 24)
        voiceLabel.autoresizingMask = [.minXMargin, .minYMargin]
        banner.addSubview(voiceLabel)

        let voiceSelector = NSSegmentedControl(labels: ["👩 Female", "👨 Male", "🎙️ Cloned"], trackingMode: .selectOne, target: self, action: #selector(voiceSelectionChanged(_:)))
        voiceSelector.selectedSegment = loadVoicePreference()
        voiceSelector.frame = NSRect(x: windowSize.width - 275, y: 44, width: 255, height: 24)
        voiceSelector.autoresizingMask = [.minXMargin, .minYMargin]
        banner.addSubview(voiceSelector)
        self.voiceSegmentedControl = voiceSelector

        // Row 2: Live Transcript (Bottom Left)
        let transcript = NSTextField(labelWithString: "💬 Tip: Say 'Play music on Spotify', 'What is my battery level?', or 'Search offline AI'")
        transcript.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        transcript.textColor = NSColor(red: 0.65, green: 0.78, blue: 0.95, alpha: 1.0)
        transcript.frame = NSRect(x: 16, y: 10, width: max(300, windowSize.width - 280), height: 24)
        transcript.autoresizingMask = [.width, .minYMargin]
        banner.addSubview(transcript)
        self.bannerLabel = transcript

        // Row 2: Studio Button (Bottom Center-Right)
        let studioBtn = NSButton(title: "🎙️ Voice Studio", target: self, action: #selector(launchVoiceCloner))
        studioBtn.bezelStyle = .rounded
        studioBtn.frame = NSRect(x: windowSize.width - 250, y: 8, width: 125, height: 26)
        studioBtn.autoresizingMask = [.minXMargin, .minYMargin]
        banner.addSubview(studioBtn)

        // Row 2: Stop Button (Bottom Right)
        let stopBtn = NSButton(title: "⏹️ Stop", target: self, action: #selector(toggleVoiceAssistant))
        stopBtn.bezelStyle = .rounded
        stopBtn.frame = NSRect(x: windowSize.width - 120, y: 8, width: 100, height: 26)
        stopBtn.autoresizingMask = [.minXMargin, .minYMargin]
        banner.addSubview(stopBtn)
        self.bannerStopButton = stopBtn

        container.addSubview(banner)
    }

    // MARK: - LibreChat-Style Artifacts Drawer Setup
    func setupArtifactsDrawer(in container: NSView, windowSize: NSSize) {
        let drawerWidth: CGFloat = 440
        let drawer = NSView(frame: NSRect(x: windowSize.width - drawerWidth, y: 0, width: drawerWidth, height: windowSize.height))
        drawer.autoresizingMask = [.minXMargin, .height]
        drawer.wantsLayer = true
        drawer.layer?.backgroundColor = CGColor(red: 0.08, green: 0.10, blue: 0.14, alpha: 1.0)
        drawer.layer?.borderWidth = 1
        drawer.layer?.borderColor = CGColor(red: 0.18, green: 0.22, blue: 0.30, alpha: 0.9)
        drawer.isHidden = true
        self.artifactsDrawer = drawer

        let headerHeight: CGFloat = 44
        let header = NSView(frame: NSRect(x: 0, y: windowSize.height - headerHeight, width: drawerWidth, height: headerHeight))
        header.autoresizingMask = [.width, .minYMargin]
        header.wantsLayer = true
        header.layer?.backgroundColor = CGColor(red: 0.12, green: 0.15, blue: 0.20, alpha: 1.0)
        drawer.addSubview(header)

        let titleLabel = NSTextField(labelWithString: "📄 Artifacts & Notes")
        titleLabel.font = NSFont.systemFont(ofSize: 13, weight: .bold)
        titleLabel.textColor = NSColor(red: 0.90, green: 0.80, blue: 0.40, alpha: 1.0)
        titleLabel.frame = NSRect(x: 12, y: 10, width: 170, height: 24)
        header.addSubview(titleLabel)

        let refreshBtn = NSButton(title: "🔄", target: self, action: #selector(refreshArtifacts))
        refreshBtn.bezelStyle = .rounded
        refreshBtn.toolTip = "Reload Notes & Artifacts"
        refreshBtn.frame = NSRect(x: drawerWidth - 195, y: 9, width: 45, height: 26)
        refreshBtn.autoresizingMask = [.minXMargin]
        header.addSubview(refreshBtn)

        let folderBtn = NSButton(title: "📂 Folder", target: self, action: #selector(openNotesFolder))
        folderBtn.bezelStyle = .rounded
        folderBtn.toolTip = "Open Notes Directory in Finder"
        folderBtn.frame = NSRect(x: drawerWidth - 145, y: 9, width: 85, height: 26)
        folderBtn.autoresizingMask = [.minXMargin]
        header.addSubview(folderBtn)

        let closeBtn = NSButton(title: "✖", target: self, action: #selector(toggleArtifactsDrawer))
        closeBtn.bezelStyle = .rounded
        closeBtn.toolTip = "Close Artifacts Drawer"
        closeBtn.frame = NSRect(x: drawerWidth - 55, y: 9, width: 45, height: 26)
        closeBtn.autoresizingMask = [.minXMargin]
        header.addSubview(closeBtn)

        let artConfig = WKWebViewConfiguration()
        let artWeb = WKWebView(frame: NSRect(x: 0, y: 0, width: drawerWidth, height: windowSize.height - headerHeight), configuration: artConfig)
        artWeb.autoresizingMask = [.width, .height]
        artWeb.setValue(false, forKey: "drawsBackground")
        drawer.addSubview(artWeb)
        self.artifactsWebView = artWeb

        container.addSubview(drawer)
    }

    @objc func toggleArtifactsDrawer() {
        guard let drawer = artifactsDrawer, let container = window.contentView else { return }
        isArtifactsDrawerOpen.toggle()

        let drawerWidth: CGFloat = 440
        let bounds = container.bounds

        if isArtifactsDrawerOpen {
            drawer.frame = NSRect(x: bounds.width - drawerWidth, y: 0, width: drawerWidth, height: bounds.height)
            drawer.isHidden = false
            webView.frame = NSRect(x: 0, y: 0, width: bounds.width - drawerWidth, height: bounds.height)
            loadArtifactsContent()
        } else {
            drawer.isHidden = true
            webView.frame = bounds
        }
    }

    @objc func refreshArtifacts() {
        loadArtifactsContent()
    }

    @objc func openNotesFolder() {
        let path = NSString(string: "~/Documents/AU_Notes").expandingTildeInPath
        let fm = FileManager.default
        if !fm.fileExists(atPath: path) {
            try? fm.createDirectory(atPath: path, withIntermediateDirectories: true)
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    func loadArtifactsContent() {
        let notesDir = NSString(string: "~/Documents/AU_Notes").expandingTildeInPath
        let fm = FileManager.default
        var notesListHTML = ""

        if let files = try? fm.contentsOfDirectory(atPath: notesDir) {
            let mdFiles = files.filter { $0.hasSuffix(".md") || $0.hasSuffix(".txt") }.sorted(by: >)
            for f in mdFiles {
                let fullPath = (notesDir as NSString).appendingPathComponent(f)
                let content = (try? String(contentsOfFile: fullPath, encoding: .utf8)) ?? ""
                let escapedContent = content
                    .replacingOccurrences(of: "&", with: "&amp;")
                    .replacingOccurrences(of: "<", with: "&lt;")
                    .replacingOccurrences(of: ">", with: "&gt;")

                notesListHTML += """
                <div class="note-card">
                    <div class="note-header">
                        <span class="note-title">📝 \(f)</span>
                        <a class="open-link" href="file://\(fullPath)">Open</a>
                    </div>
                    <pre class="note-body">\(escapedContent)</pre>
                </div>
                """
            }
        }

        if notesListHTML.isEmpty {
            notesListHTML = """
            <div class="empty-state">
                <h3>No Artifacts Stored Yet</h3>
                <p>AU writes markdown notes and system reports on command.</p>
                <p>Try saying to AU:<br>
                   <em>"Create a note titled Project Ideas with my goals"</em><br>
                   <em>"Check my system status"</em>
                </p>
            </div>
            """
        }

        let html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {
                background-color: #0d1117;
                color: #c9d1d9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                margin: 0;
                padding: 16px;
            }
            h2 { color: #f0883e; margin-top: 0; font-size: 15px; border-bottom: 1px solid #21262d; padding-bottom: 8px; }
            .note-card {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 12px;
            }
            .note-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }
            .note-title { font-weight: 600; color: #58a6ff; font-size: 13px; }
            .open-link {
                color: #8b949e;
                text-decoration: none;
                font-size: 11px;
                background: #21262d;
                padding: 3px 8px;
                border-radius: 4px;
            }
            .open-link:hover { color: #58a6ff; background: #30363d; }
            .note-body {
                font-size: 12px;
                line-height: 1.5;
                color: #c9d1d9;
                white-space: pre-wrap;
                max-height: 220px;
                overflow-y: auto;
                background: #0d1117;
                padding: 8px;
                border-radius: 4px;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                margin: 0;
            }
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: #8b949e;
            }
            .empty-state h3 { color: #c9d1d9; }
            .empty-state em { color: #58a6ff; }
        </style>
        </head>
        <body>
            <h2>📄 AU Artifacts & Notes Store</h2>
            \(notesListHTML)
        </body>
        </html>
        """
        artifactsWebView?.loadHTMLString(html, baseURL: nil)
    }

    // MARK: - Persona Studio Engine
    @objc func personaSelectionChanged(_ sender: NSSegmentedControl) {
        let index = sender.selectedSegment
        let personaKeys = ["automator", "researcher", "podcast", "coder"]
        let personaKey = personaKeys[max(0, min(index, personaKeys.count - 1))]
        savePersonaPreference(persona: personaKey)

        let descriptions = [
            "Persona: ⚡ Mac Automator (System actions, apps, volume, Spotify, macOS control)",
            "Persona: 🧠 Research Partner (Grounded document RAG, citations, and summaries)",
            "Persona: 🎙️ Podcast Studio (Dialogue synthesis & two-host audio generation)",
            "Persona: 💻 Code Architect (Bash terminal execution, script editing, coding)"
        ]
        statusDetailLabel?.stringValue = descriptions[max(0, min(index, descriptions.count - 1))]
    }

    func savePersonaPreference(persona: String) {
        let path = NSString(string: "~/.offline-ai/persona_config.json").expandingTildeInPath
        let dict: [String: String] = [
            "active_persona": persona,
            "updated_at": ISO8601DateFormatter().string(from: Date())
        ]
        if let data = try? JSONSerialization.data(withJSONObject: dict, options: .prettyPrinted) {
            try? data.write(to: URL(fileURLWithPath: path))
        }
    }

    func loadPersonaPreference() -> Int {
        let path = NSString(string: "~/.offline-ai/persona_config.json").expandingTildeInPath
        if let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
           let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let p = dict["active_persona"] as? String {
            if p == "researcher" { return 1 }
            if p == "podcast" { return 2 }
            if p == "coder" { return 3 }
        }
        return 0 // default automator
    }

    // MARK: - Mem0 Memory Management Action
    @objc func openMemoryManager() {
        let scriptPath = NSString(string: "~/Downloads/offline ai/tools/au-memory").expandingTildeInPath
        let terminalScript = """
        osascript -e 'tell application "Terminal" to do script "\(scriptPath) list"'
        """
        let process = Process()
        process.launchPath = "/bin/bash"
        process.arguments = ["-c", terminalScript]
        try? process.run()
    }

    // MARK: - Voice Settings Dispatcher
    @objc func voiceSelectionChanged(_ sender: NSSegmentedControl) {
        var mode = "female"
        if sender.selectedSegment == 1 { mode = "male" }
        else if sender.selectedSegment == 2 { mode = "cloned" }
        saveVoicePreference(mode: mode)
        statusDetailLabel?.stringValue = "Assistant Voice changed to: \(sender.label(forSegment: sender.selectedSegment) ?? mode)"
        // Personal Voice permission is an isolated, opt-in capability; never request it
        // while AU is using its normal Male or Female system voices.
        if mode == "cloned", #available(macOS 14.0, *) {
            AVSpeechSynthesizer.requestPersonalVoiceAuthorization { _ in }
        }
    }

    func saveVoicePreference(mode: String) {
        let path = NSString(string: "~/.offline-ai/voice_config.json").expandingTildeInPath
        let dict: [String: String] = [
            "voice_gender": mode,
            "male_voice": "Daniel",
            "female_voice": "Samantha"
        ]
        if let data = try? JSONSerialization.data(withJSONObject: dict, options: .prettyPrinted) {
            try? data.write(to: URL(fileURLWithPath: path))
        }
    }

    func loadVoicePreference() -> Int {
        let path = NSString(string: "~/.offline-ai/voice_config.json").expandingTildeInPath
        if let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
           let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let gender = dict["voice_gender"] as? String {
            if gender == "male" { return 1 }
            if gender == "cloned" { return 2 }
        }
        return 0 // default female
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
            // Give the Python signal handler a moment to stop its recorder/speaker child.
            DispatchQueue.global().asyncAfter(deadline: .now() + 1.0) {
                if process.isRunning { process.interrupt() }
            }
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
            updateStateBadge(state: "LISTENING")
        } else {
            voiceToolbarButton?.title = " Start Assistant"
            voiceToolbarButton?.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Mic")
            assistantBanner?.isHidden = true
        }
    }

    func updateStateBadge(state: String) {
        guard let badge = stateBadge else { return }
        switch state {
        case "LISTENING":
            badge.stringValue = " 🟢 LISTENING (Your Turn) "
            badge.textColor = NSColor(red: 0.35, green: 0.95, blue: 0.45, alpha: 1.0)
            badge.layer?.backgroundColor = CGColor(red: 0.12, green: 0.26, blue: 0.16, alpha: 0.9)
            statusDetailLabel?.stringValue = "Microphone active — speak your command now."
        case "HEARING":
            badge.stringValue = " 🔴 RECORDING SPEECH "
            badge.textColor = NSColor(red: 1.0, green: 0.4, blue: 0.4, alpha: 1.0)
            badge.layer?.backgroundColor = CGColor(red: 0.35, green: 0.12, blue: 0.12, alpha: 0.9)
            statusDetailLabel?.stringValue = "Hearing speech... Speak clearly."
        case "THINKING":
            badge.stringValue = " 🟡 THINKING (M4 Brain) "
            badge.textColor = NSColor(red: 1.0, green: 0.85, blue: 0.3, alpha: 1.0)
            badge.layer?.backgroundColor = CGColor(red: 0.32, green: 0.26, blue: 0.10, alpha: 0.9)
            statusDetailLabel?.stringValue = "Running local Ollama model (au-assistant)..."
        case "EXECUTING":
            badge.stringValue = " ⚡ AUTOMATING MAC "
            badge.textColor = NSColor(red: 0.4, green: 0.85, blue: 1.0, alpha: 1.0)
            badge.layer?.backgroundColor = CGColor(red: 0.10, green: 0.25, blue: 0.35, alpha: 0.9)
            statusDetailLabel?.stringValue = "Executing Mac system automation..."
        case "SPEAKING":
            badge.stringValue = " 🔵 AU SPEAKING "
            badge.textColor = NSColor(red: 0.55, green: 0.75, blue: 1.0, alpha: 1.0)
            badge.layer?.backgroundColor = CGColor(red: 0.15, green: 0.22, blue: 0.35, alpha: 0.9)
            statusDetailLabel?.stringValue = "Answering your request with voice..."
        case "STANDBY":
            badge.stringValue = " 💤 STANDBY "
            badge.textColor = NSColor.secondaryLabelColor
            badge.layer?.backgroundColor = CGColor(red: 0.2, green: 0.2, blue: 0.2, alpha: 0.9)
            statusDetailLabel?.stringValue = "Assistant asleep. Say 'Wake up AU'..."
        default:
            break
        }
    }

    func handleAssistantLog(_ log: String) {
        let lines = log.components(separatedBy: .newlines)
        for rawLine in lines {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty { continue }

            if line.contains("[AU_STATE:") {
                let state = line.components(separatedBy: "[AU_STATE:").last?.components(separatedBy: "]").first ?? ""
                updateStateBadge(state: state)
            } else if line.contains("[AU_USER_TEXT:") {
                let text = line.components(separatedBy: "[AU_USER_TEXT:").last?.components(separatedBy: "]").first ?? ""
                bannerLabel?.stringValue = "👤 You: \"\(text)\""
            } else if line.contains("[AU_RESPONSE_TEXT:") {
                let text = line.components(separatedBy: "[AU_RESPONSE_TEXT:").last?.components(separatedBy: "]").first ?? ""
                bannerLabel?.stringValue = "🤖 AU: \"\(text)\""
            } else if line.contains("[AU_ACTION:") {
                let act = line.components(separatedBy: "[AU_ACTION:").last?.components(separatedBy: "]").first ?? ""
                bannerLabel?.stringValue = "⚡ Executed: \(act)"
            }
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

    // MARK: - Voice Studio Actions (Isolated)
    @objc func launchVoiceCloner() {
        let scriptPath = NSString(string: "~/Downloads/offline ai/tools/au-clone-voice").expandingTildeInPath
        let terminalScript = """
        osascript -e 'tell application "Terminal" to do script "\(scriptPath)"'
        """
        let process = Process()
        process.launchPath = "/bin/bash"
        process.arguments = ["-c", terminalScript]
        try? process.run()
    }

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

    // MARK: - M4 Hardware Telemetry Engine (Jan-style)
    func updateHardwareTelemetry() {
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
        let hostPort = mach_host_self()
        let kerr = withUnsafeMutablePointer(to: &stats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics64(hostPort, HOST_VM_INFO64, $0, &count)
            }
        }

        if kerr == KERN_SUCCESS {
            let pageSize = UInt64(vm_kernel_page_size)
            let active = UInt64(stats.active_count) * pageSize
            let wired = UInt64(stats.wire_count) * pageSize
            let usedGB = Double(active + wired) / 1_073_741_824.0
            let totalGB = Double(ProcessInfo.processInfo.physicalMemory) / 1_073_741_824.0

            let icon = usedGB > 13.0 ? "🟡" : "🟢"
            let text = String(format: "%@ RAM: %.1f / %.0f GB (M4)", icon, usedGB, totalGB)
            DispatchQueue.main.async {
                self.hardwareStatusLabel?.stringValue = text
            }
        }
    }

    // MARK: - Multimodal Vision Inspector (LobeChat-style)
    @objc func inspectImageWithVision() {
        let openPanel = NSOpenPanel()
        openPanel.allowedContentTypes = [.image]
        openPanel.allowsMultipleSelection = false
        openPanel.prompt = "Analyze Image"
        openPanel.message = "Choose an image for local vision inspection"

        openPanel.beginSheetModal(for: self.window) { [weak self] response in
            if response == .OK, let url = openPanel.url {
                let path = url.path
                self?.statusDetailLabel?.stringValue = "Analyzing image: \(url.lastPathComponent) with local vision..."
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString("Please inspect and analyze this local image: \(path)", forType: .string)

                let alert = NSAlert()
                alert.messageText = "Image Selected for Local Vision"
                alert.informativeText = "Path: \(url.lastPathComponent)\n\nPrompt copied to clipboard. Paste into chat to inspect with local vision models."
                alert.alertStyle = .informational
                alert.addButton(withTitle: "OK")
                alert.beginSheetModal(for: self!.window, completionHandler: nil)
            }
        }
    }

    // MARK: - 1-Click Chat Transcript Exporter (NextChat-style)
    @objc func exportChatToMarkdown() {
        let desktop = NSString(string: "~/Desktop").expandingTildeInPath
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        let filename = "AU_Chat_\(df.string(from: Date())).md"
        let fullPath = (desktop as NSString).appendingPathComponent(filename)

        let script = """
        Array.from(document.querySelectorAll('.chat-message, [data-message]')).map(el => el.innerText).join('\\n\\n---\\n\\n')
        """

        webView.evaluateJavaScript(script) { [weak self] (result, error) in
            guard let self = self else { return }
            let text = (result as? String) ?? ""
            let content: String
            if !text.isEmpty {
                content = "# AU Chat Transcript\n\n*Exported on \(Date().description)*\n\n---\n\n" + text
            } else {
                content = "# AU Assistant Activity Log\n\n*Exported on \(Date().description)*\n\nAU Assistant is online on Apple Silicon M4 with 16GB Unified RAM.\n"
            }

            try? content.write(toFile: fullPath, atomically: true, encoding: .utf8)
            let alert = NSAlert()
            alert.messageText = "Transcript Exported"
            alert.informativeText = "Chat transcript saved to Desktop:\n\(filename)"
            alert.alertStyle = .informational
            alert.addButton(withTitle: "Open in Finder")
            alert.addButton(withTitle: "Done")
            alert.beginSheetModal(for: self.window) { resp in
                if resp == .alertFirstButtonReturn {
                    NSWorkspace.shared.selectFile(fullPath, inFileViewerRootedAtPath: desktop)
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
            NSToolbarItem.Identifier("PersonaItem"),
            NSToolbarItem.Identifier("ArtifactsItem"),
            NSToolbarItem.Identifier("MemoryItem"),
            .flexibleSpace,
            NSToolbarItem.Identifier("CloneVoiceItem"),
            NSToolbarItem.Identifier("PodcastItem"),
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
        } else if itemIdentifier.rawValue == "PersonaItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "AI Persona"
            item.paletteLabel = "AI Persona"
            item.toolTip = "Switch AI persona between Automator, Researcher, Podcast Studio, and Code Architect"

            let selector = NSSegmentedControl(labels: ["⚡ Auto", "🧠 Research", "🎙️ Podcast", "💻 Code"], trackingMode: .selectOne, target: self, action: #selector(personaSelectionChanged(_:)))
            selector.selectedSegment = loadPersonaPreference()
            self.personaSegmentedControl = selector
            item.view = selector
            return item
        } else if itemIdentifier.rawValue == "ArtifactsItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "Artifacts"
            item.paletteLabel = "Artifacts & Notes"
            item.toolTip = "Toggle slide-over drawer for notes, artifacts, and generated documents"

            let btn = NSButton(title: " Artifacts", target: self, action: #selector(toggleArtifactsDrawer))
            btn.bezelStyle = .rounded
            btn.image = NSImage(systemSymbolName: "doc.text.magnifyingglass", accessibilityDescription: "Artifacts")
            btn.imagePosition = .imageLeading
            item.view = btn
            return item
        } else if itemIdentifier.rawValue == "MemoryItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "Mem0 Memory"
            item.paletteLabel = "Mem0 Memory Store"
            item.toolTip = "View and manage remembered personal preferences and episodic facts"

            let btn = NSButton(title: " Memory", target: self, action: #selector(openMemoryManager))
            btn.bezelStyle = .rounded
            btn.image = NSImage(systemSymbolName: "brain.head.profile", accessibilityDescription: "Memory")
            btn.imagePosition = .imageLeading
            item.view = btn
            return item
        } else if itemIdentifier.rawValue == "CloneVoiceItem" {
            let item = NSToolbarItem(itemIdentifier: itemIdentifier)
            item.label = "Clone Voice"
            item.paletteLabel = "Instant Voice Clone"
            item.toolTip = "Record a 5-10 second clip to clone your voice instantly offline using M4 MLX"

            let btn = NSButton(title: " Clone Voice", target: self, action: #selector(launchVoiceCloner))
            btn.bezelStyle = .rounded
            btn.image = NSImage(systemSymbolName: "waveform.badge.plus", accessibilityDescription: "Clone Voice")
            btn.imagePosition = .imageLeading
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
            let label = NSTextField(labelWithString: "🟢 RAM: 4.0 / 16 GB (M4)")
            label.font = NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .semibold)
            label.textColor = NSColor.secondaryLabelColor
            self.hardwareStatusLabel = label
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
        assistantMenu.addItem(withTitle: "Toggle Artifacts & Notes Drawer", action: #selector(toggleArtifactsDrawer), keyEquivalent: "D")
        assistantMenu.addItem(withTitle: "Manage Personal Memory (Mem0)...", action: #selector(openMemoryManager), keyEquivalent: "M")
        assistantMenu.addItem(NSMenuItem.separator())
        assistantMenu.addItem(withTitle: "Make Audio Podcast", action: #selector(generatePodcast), keyEquivalent: "P")
        assistantMenu.addItem(withTitle: "Open Saved Podcasts", action: #selector(openPodcastsFolder), keyEquivalent: "O")
        assistantMenu.addItem(NSMenuItem.separator())
        assistantMenu.addItem(withTitle: "Clone Voice (Instant 10s MLX)...", action: #selector(launchVoiceCloner), keyEquivalent: "K")
        assistantMenu.addItem(withTitle: "Test Personal Voice (AI female)", action: #selector(testPersonalVoice), keyEquivalent: "T")
        assistantMenu.addItem(withTitle: "Personal Voice Settings...", action: #selector(showPersonalVoiceGuide), keyEquivalent: "")
        assistantMenu.addItem(NSMenuItem.separator())
        assistantMenu.addItem(withTitle: "Inspect Image with Local Vision...", action: #selector(inspectImageWithVision), keyEquivalent: "I")
        assistantMenu.addItem(withTitle: "Export Chat to Markdown...", action: #selector(exportChatToMarkdown), keyEquivalent: "E")

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
        telemetryTimer?.invalidate()
        telemetryTimer = nil
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

    let configPath = NSString(string: "~/.offline-ai/voice_config.json").expandingTildeInPath
    let mode: String
    if let data = try? Data(contentsOf: URL(fileURLWithPath: configPath)),
       let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
       let savedMode = config["voice_gender"] as? String {
        mode = savedMode
    } else {
        mode = "female"
    }

    // Personal Voice is exclusively opt-in via the Cloned Voice segment.
    if mode == "male" {
        selectedVoice = voices.first(where: { $0.name == "Daniel" })
    } else if mode == "female" {
        selectedVoice = voices.first(where: { $0.name == "Samantha" })
    }

    // Look for a Personal Voice only when the user selected Cloned Voice.
    if mode == "cloned" {
        for v in voices {
            if isVoiceClonedOrPersonal(v) {
                selectedVoice = v
                break
            }
        }
    }

    let isPersonal = mode == "cloned" && isVoiceClonedOrPersonal(selectedVoice)
    if isPersonal {
        fputs("🗣️ [AU Voice: \(selectedVoice?.name ?? "AI female") ⭐ (YOUR CLONED PERSONAL VOICE)]\n", stderr)
    } else {
        fputs("ℹ️ [AU Voice: 'AI female' is generating in macOS Neural Engine. Using Mac System Voice until ready]\n", stderr)
    }

    let utterance = AVSpeechUtterance(string: trimmed)
    if let voice = selectedVoice {
        utterance.voice = voice
    }
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
