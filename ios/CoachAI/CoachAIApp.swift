import SwiftUI
import WebKit

@main
struct CoachAIApp: App {
    @StateObject private var app = AppStore()
    @StateObject private var clock = RestClock()
    var body: some Scene {
        WindowGroup {
            RootScreen().environmentObject(app).environmentObject(clock)
                .tint(Color(red: 0.09, green: 0.28, blue: 0.22))
                .task { await app.restore() }
                .onChange(of: app.authenticated) { _, connected in if !connected { clock.cancel() } }
        }
    }
}
struct RootScreen: View {
    @EnvironmentObject private var app: AppStore
    var body: some View {
        Group {
            if app.authenticated, let api = app.api {
                TabView {
                    NavigationStack { GymScreen() }
                        .tabItem { Label("Muscu", systemImage: "dumbbell.fill") }
                    WebScreen(api: api, page: "coach", store: app.webStore)
                        .tabItem { Label("Coach", systemImage: "bubble.left.and.bubble.right") }
                    WebScreen(api: api, page: "activities", store: app.webStore)
                        .tabItem { Label("Activités", systemImage: "figure.run") }
                    WebScreen(api: api, page: "planning", store: app.webStore)
                        .tabItem { Label("Planning", systemImage: "calendar") }
                    NavigationStack { SettingsScreen(webStore: app.webStore) }
                        .tabItem { Label("Compte", systemImage: "person.crop.circle") }
                }.id(app.webSessionID)
            } else { LoginScreen() }
        }
    }
}
struct LoginScreen: View {
    @EnvironmentObject private var app: AppStore
    @State private var server = UserDefaults.standard.string(forKey: "coach-server") ?? "https://coach-ai-production-1c6b.up.railway.app"
    @State private var key = ""
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Label("Ton coach, dans ta poche", systemImage: "figure.strengthtraining.traditional")
                        .font(.title2.bold()).padding(.vertical)
                    Text("Connecte ton compte existant avec ta clé d’accès personnelle.")
                }
                Section("Connexion sécurisée") {
                    TextField("Adresse HTTPS du serveur", text: $server).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("Clé d’accès Coach AI", text: $key).textContentType(.password)
                    Button {
                        let accessKey = key; key = ""
                        Task {
                            await app.login(server: server, key: accessKey)
                            if app.authenticated { UserDefaults.standard.set(server, forKey: "coach-server") }
                        }
                    } label: { HStack { Text("Se connecter"); Spacer(); if app.busy { ProgressView() } } }
                        .disabled(key.isEmpty || app.busy)
                }
                if let error = app.error { Section { Text(error).foregroundStyle(.red) } }
                Section {
                    Text("Nouveau compte : utilise ton lien d’invitation dans Safari, puis saisis ici la clé obtenue. La clé n’est pas conservée par l’app ; seule la session est protégée dans le trousseau iOS.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }.navigationTitle("Coach AI")
        }
    }
}
struct SettingsScreen: View {
    @EnvironmentObject private var app: AppStore
    let webStore: WKWebsiteDataStore
    @State private var connections = false
    @State private var logout = false
    var body: some View {
        Form {
            Section("Ton compte") {
                Text(app.owner?.name ?? "Coach AI")
                Text(app.api?.origin.host ?? "").font(.footnote).foregroundStyle(.secondary)
            }
            Section("Garmin et ChatGPT") {
                Button("Gérer les connexions et importer une session") { connections = true }
                Text("Retrouve les connexions existantes, les imports de sessions et le renouvellement ChatGPT. Une app iPhone ne débloque pas l’autorisation Garmin ou ChatGPT : la connexion initiale peut encore demander un ordinateur.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section {
                Text("Les activités et échanges restent sur ton serveur. Le brouillon muscu reste protégé sur cet iPhone jusqu’à l’enregistrement ; il n’est jamais envoyé à un autre compte.")
                    .font(.footnote)
                Button("Se déconnecter", role: .destructive) { logout = true }.disabled(app.busy)
            }
        }.navigationTitle("Mon compte")
            .sheet(isPresented: $connections) {
                if let api = app.api {
                    NavigationStack {
                        WebScreen(api: api, page: "settings", store: app.webStore)
                            .navigationTitle("Connexions").navigationBarTitleDisplayMode(.inline)
                            .toolbar { Button("Fermer") { connections = false } }
                    }
                }
            }
            .confirmationDialog("Se déconnecter ? Le brouillon éventuel sera retrouvé à la reconnexion au même compte.", isPresented: $logout, titleVisibility: .visible) {
                Button("Se déconnecter", role: .destructive) { Task { await app.logout() } }
            }
    }
}
