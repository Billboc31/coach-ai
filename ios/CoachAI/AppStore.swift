import SwiftUI
import Combine
import UserNotifications
import WebKit

@MainActor
final class AppStore: ObservableObject {
    @Published var api: CoachAPI?
    @Published var owner: Dashboard.Account?
    @Published var overview: GymOverview?
    @Published var workout: Workout?
    @Published var index = 0
    @Published var dirty = false
    @Published var busy = false
    @Published var error: String?
    @Published var progression: [String: Double] = [:]
    @Published var conflict = false
    @Published var webSessionID = UUID()
    private(set) var webStore = WKWebsiteDataStore.nonPersistent()
    var authenticated: Bool { api != nil && owner != nil }
    var exercise: Exercise? {
        guard let workout, workout.exercises.indices.contains(index) else { return nil }
        return workout.exercises[index]
    }
    func restore() async {
        guard let saved = SessionVault.load(), saved.expires > Date(),
              (try? CoachRules.origin(saved.origin.absoluteString)) != nil else { return }
        await connect(CoachAPI(origin: saved.origin, saved: saved), key: nil)
    }
    func login(server: String, key: String) async {
        do { await connect(CoachAPI(origin: try CoachRules.origin(server)), key: key) }
        catch { self.error = error.localizedDescription }
    }
    private func connect(_ client: CoachAPI, key: String?) async {
        guard !busy else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            if let key { try await client.login(key: key) }
            let dashboard: Dashboard = try await client.get("/api/dashboard")
            webStore = .nonPersistent(); webSessionID = UUID(); api = client; owner = dashboard.account
            if let draft = DraftVault.load(owner: dashboard.account.id, origin: client.origin) {
                workout = draft.workout; progression = draft.progression
                index = min(max(0, draft.index), max(0, draft.workout.exercises.count - 1)); dirty = true
                do {
                    let remote: Workout = try await client.get("/api/gym/workouts/\(draft.workout.id)")
                    conflict = remote.revision != draft.workout.revision || remote.locked
                } catch { self.error = "Brouillon récupéré sur cet iPhone. Vérification serveur indisponible ; réessaie avant de continuer." }
            }
            overview = try await client.get("/api/gym")
        } catch { report(error) }
    }
    func refresh() async {
        guard let api, !busy else { return }
        busy = true; defer { busy = false }
        do { overview = try await api.get("/api/gym"); error = nil } catch { report(error) }
    }
    func start(program: String, day: String) async {
        guard let api, !busy, !dirty else { return }
        busy = true; defer { busy = false }
        do {
            workout = try await api.start(program: program, day: day)
            workout?.applySuggestions(); index = 0; progression = [:]; conflict = false; dirty = false; error = nil
        } catch { report(error) }
    }
    func resume(_ value: Workout) async {
        guard let api, !busy, !dirty else { return }
        busy = true; defer { busy = false }
        do {
            workout = try await api.get("/api/gym/workouts/\(value.id)")
            workout?.applySuggestions(); progression = [:]; index = 0; conflict = false; error = nil
        } catch { report(error) }
    }
    func edit(row: Int, _ change: (inout LoggedSet) -> Void) {
        guard !busy, !conflict, var value = workout, !value.locked,
              value.exercises.indices.contains(index),
              var rows = value.exercises[index].logged_sets, rows.indices.contains(row) else { return }
        change(&rows[row])
        value.exercises[index].logged_sets = rows
        // Editing a completed exercise cancels its previous next-load proposal.
        if !rows.allSatisfy(\.done) { progression.removeValue(forKey: value.exercises[index].id) }
        workout = value; dirty = true; persist()
    }
    func addSet() {
        guard !busy, !conflict, var value = workout, !value.locked,
              let e = exercise, (e.logged_sets?.count ?? 0) < 30 else { return }
        value.exercises[index].logged_sets = (e.logged_sets ?? []) + [LoggedSet(weight: nil, reps: nil, seconds: nil, done: false)]
        workout = value; progression.removeValue(forKey: e.id); dirty = true; persist()
    }
    func setIncrease(_ amount: Double) {
        guard let e = exercise, let rows = e.logged_sets, rows.allSatisfy(\.done),
              rows.contains(where: { $0.weight != nil }), amount.isFinite, amount >= 0,
              rows.allSatisfy({ ($0.weight ?? 0) + amount <= 2000 }), !busy, !conflict else { return }
        progression[e.id] = amount; dirty = true; persist()
    }
    func select(_ n: Int) {
        guard let workout, workout.exercises.indices.contains(n), !busy else { return }
        index = n
        if dirty { persist() }
    }
    private func clearDraft() throws {
        guard let api, let owner else { throw CoachFailure.signedOut }
        try DraftVault.clear(owner: owner.id, origin: api.origin)
    }
    private func persist() {
        guard let api, let owner, let workout else { return }
        do { try DraftVault.save(WorkoutDraft(owner: owner.id, origin: api.origin, workout: workout, progression: progression, index: index)) }
        catch { self.error = "Brouillon non enregistré sur l’iPhone. Garde l’app ouverte et enregistre sur le serveur." }
    }
    func save(finish: Bool = false) async {
        guard let api, let workout, !busy, !conflict, !workout.locked else { return }
        busy = true; error = nil; defer { busy = false }
        // Persist before sending. A lost response never triggers an automatic replay.
        dirty = true; persist()
        do {
            self.workout = try await api.save(workout, progression: progression, finish: finish)
            dirty = false; progression = [:]
            try clearDraft()
            if finish { overview = try await api.get("/api/gym") }
        } catch { report(error) }
    }
    func reloadDiscardingDraft() async {
        guard let api, let workout, !busy else { return }
        busy = true; defer { busy = false }
        do {
            self.workout = try await api.get("/api/gym/workouts/\(workout.id)")
            self.workout?.applySuggestions()
            try clearDraft(); progression = [:]; dirty = false; conflict = false; error = nil
        } catch { report(error) }
    }
    func delete(_ value: Workout) async {
        guard let api, !busy, !value.locked else { return }
        busy = true; defer { busy = false }
        do {
            try await api.delete(value)
            if workout?.id == value.id {
                try clearDraft(); workout = nil; dirty = false; progression = [:]; conflict = false
            }
            overview = try await api.get("/api/gym"); error = nil
        } catch { report(error) }
    }
    func leave() {
        guard !busy, !dirty else { return }
        workout = nil; progression = [:]; index = 0; conflict = false
        Task { await refresh() }
    }
    func logout() async {
        guard !busy else { return }
        if let api { _ = try? await api.send("/api/logout", method: "POST") }
        SessionVault.clear()
        // Draft stays protected and can be restored only after authentication to its owner.
        api = nil; owner = nil; overview = nil; workout = nil; progression = [:]
        dirty = false; conflict = false; error = nil; webStore = .nonPersistent(); webSessionID = UUID()
    }
    private func report(_ failure: Error) {
        if let failure = failure as? CoachFailure {
            error = failure.localizedDescription
            switch failure {
            case .signedOut:
                api = nil; owner = nil; overview = nil; workout = nil; progression = [:]; dirty = false
                webStore = .nonPersistent(); webSessionID = UUID(); SessionVault.clear()
            case .conflict: conflict = true
            default: break
            }
        } else {
            error = "Connexion indisponible. Le brouillon reste sur cet iPhone. Réessaie ou compare la version serveur avant de recharger."
        }
    }
}

@MainActor
final class RestClock: ObservableObject {
    @Published var deadline: Date?
    @Published var notificationDenied = false
    func start(seconds: Int) async {
        guard (1...7200).contains(seconds) else { return }
        cancel()
        let end = Date().addingTimeInterval(Double(seconds)); deadline = end
        let center = UNUserNotificationCenter.current()
        let allowed = (try? await center.requestAuthorization(options: [.alert, .sound])) == true
        notificationDenied = !allowed
        guard allowed, deadline == end else { return }
        let content = UNMutableNotificationContent()
        content.title = "Repos terminé"; content.body = "Prêt pour la prochaine série ?"; content.sound = .default
        let remaining = end.timeIntervalSinceNow
        guard remaining > 0 else { return }
        try? await center.add(UNNotificationRequest(identifier: "coach-rest", content: content,
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: max(1, remaining), repeats: false)))
    }
    func cancel() {
        deadline = nil
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["coach-rest"])
        UNUserNotificationCenter.current().removeDeliveredNotifications(withIdentifiers: ["coach-rest"])
    }
}
