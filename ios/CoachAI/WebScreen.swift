import SwiftUI
import WebKit

// An isolated, in-memory website store per login. No JS bridge, no token injection in JavaScript.
struct WebScreen: UIViewRepresentable {
    let api: CoachAPI
    let page: String
    let store: WKWebsiteDataStore
    func makeCoordinator() -> Coordinator { Coordinator(origin: api.origin) }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = store
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.isInspectable = false
        view.allowsBackForwardNavigationGestures = true
        guard let saved = api.saved, let host = api.origin.host,
              let cookie = HTTPCookie(properties: [.domain: host, .path: "/", .name: "coach_session",
                  .value: saved.token, .secure: "TRUE", .expires: saved.expires,
                  HTTPCookiePropertyKey("HttpOnly"): "TRUE",
                  HTTPCookiePropertyKey("SameSite"): "Strict"]) else { return view }
        Task { @MainActor in
            await store.httpCookieStore.setCookie(cookie)
            guard var components = URLComponents(url: api.origin, resolvingAgainstBaseURL: false) else { return }
            components.queryItems = [URLQueryItem(name: "page", value: page)]
            if let url = components.url { view.load(URLRequest(url: url)) }
        }
        return view
    }
    func updateUIView(_ view: WKWebView, context: Context) {}
    final class Coordinator: NSObject, WKNavigationDelegate {
        let origin: URL
        init(origin: URL) { self.origin = origin }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { decisionHandler(.cancel); return }
            if CoachRules.sameOrigin(url, origin) { decisionHandler(.allow); return }
            // External user links open in Safari without the app cookie. Redirects are blocked.
            if action.navigationType == .linkActivated, ["https", "http"].contains(url.scheme ?? "") {
                UIApplication.shared.open(url)
            }
            decisionHandler(.cancel)
        }
    }
}
