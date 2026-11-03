import Cocoa
import WebKit

class AUApplicationDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var loadingView: NSView!
    var spinner: NSProgressIndicator!
    var statusLabel: NSTextField!
    var retryTimer: Timer?

    func applicationDidFinishLaunching(_ aNotification: Notification) {
        setupMenu()
        ensureBackendRunning()

        let windowSize = NSSize(width: 1200, height: 820)
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
        window.title = "AU - Offline AI"
        window.center()
        window.minSize = NSSize(width: 800, height: 600)
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(red: 0.08, green: 0.09, blue: 0.12, alpha: 1.0)
        window.isMovableByWindowBackground = false

        let config = WKWebViewConfiguration()
        let prefs = WKWebpagePreferences()
        prefs.allowsContentJavaScript = true
        config.defaultWebpagePreferences = prefs
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        let container = NSView(frame: NSRect(origin: .zero, size: windowSize))
        container.autoresizingMask = [.width, .height]
        window.contentView = container

        webView = WKWebView(frame: container.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        container.addSubview(webView)

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

        statusLabel = NSTextField(labelWithString: "Starting AU Offline AI...")
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

    // MARK: - WKUIDelegate: File Upload, Alerts & Media Permissions
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

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

let app = NSApplication.shared
let delegate = AUApplicationDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
