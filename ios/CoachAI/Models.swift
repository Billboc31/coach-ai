import Foundation

struct GymOverview: Decodable {
    let programs: [Program]
    let workouts: [Workout]
}
struct Program: Decodable, Identifiable {
    let id: String
    let title: String
    let archived: Bool?
    let hidden_sheets: [String]?
    let days: [ProgramDay]
    var availableDays: [ProgramDay] {
        days.filter { $0.hidden != true && !(hidden_sheets ?? []).contains($0.sheet) && !$0.exercises.filter { $0.hidden != true }.isEmpty }
    }
}
struct ProgramDay: Decodable, Identifiable {
    let id: String
    let name: String
    let sheet: String
    let display_name: String?
    let hidden: Bool?
    let exercises: [Exercise]
}
struct Workout: Codable, Identifiable {
    let id: String
    let title: String
    let started_at: String
    let finished_at: String?
    var revision: Int
    let suggestions_applied: Bool?
    var exercises: [Exercise]
    var locked: Bool { finished_at != nil }
    var sets: [String: [LoggedSet]] { Dictionary(uniqueKeysWithValues: exercises.map { ($0.id, $0.logged_sets ?? []) }) }
    mutating func applySuggestions() {
        guard suggestions_applied != true && !locked else { return }
        for i in exercises.indices {
            // Never replace actual logged work with suggestions.
            if !(exercises[i].logged_sets ?? []).contains(where: { $0.done }), let suggested = exercises[i].suggested_sets {
                exercises[i].logged_sets = suggested
            }
        }
    }
}
struct Exercise: Codable, Identifiable {
    let id: String
    let name: String
    let canonical_name: String?
    let movement_name: String?
    let hidden: Bool?
    let reps: String?
    let rest: String?
    let short_rest: String?
    let tempo: String?
    let training_instruction: String?
    let weight_convention: String?
    let weight_context: String?
    let is_document: Bool?
    let document_links: [String]?
    let thumbnail: Thumbnail?
    var logged_sets: [LoggedSet]?
    let suggested_sets: [LoggedSet]?
    let next_load_increase_kg: Double?
    var title: String { canonical_name ?? movement_name ?? name }
    func restText(at index: Int) -> String {
        let raw = rest ?? short_rest ?? ""
        let parts = raw.components(separatedBy: .newlines).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return parts.count == logged_sets?.count && parts.indices.contains(index) ? parts[index] : raw
    }
}
struct Thumbnail: Codable {
    let url: String
    let credit: Credit
    struct Credit: Codable { let name: String; let authors: [String] }
}
struct LoggedSet: Codable, Equatable {
    var weight: Double?
    var reps: Int?
    var seconds: Int?
    var done: Bool
    var valid: Bool {
        (weight.map { $0.isFinite && (0...2000).contains($0) } ?? true) &&
        (reps.map { (0...1000).contains($0) } ?? true) &&
        (seconds.map { (0...7200).contains($0) } ?? true) &&
        (!done || reps != nil || seconds != nil)
    }
}
struct WorkoutUpdate: Encodable {
    let revision: Int
    let sets: [String: [LoggedSet]]
    let progression: [String: Double]
    let finish: Bool
    let suggestions_applied = true
}
struct Dashboard: Decodable {
    let account: Account
    struct Account: Decodable { let id: String; let name: String }
}
struct SavedSession: Codable {
    let origin: URL
    let token: String
    let expires: Date
}
struct WorkoutDraft: Codable {
    let owner: String
    let origin: URL
    var workout: Workout
    var progression: [String: Double]
    var index: Int
}

enum CoachFailure: LocalizedError {
    case invalidServer, signedOut, conflict, rejected(Int), invalidData, keychain
    var errorDescription: String? {
        switch self {
        case .invalidServer: return "Saisis l’adresse HTTPS du serveur, sans chemin, identifiant ni paramètres."
        case .signedOut: return "Session expirée. Reconnecte-toi avec la clé du même compte pour retrouver ton brouillon."
        case .conflict: return "Cette séance a changé ailleurs. Ton brouillon est conservé : compare-le avant de recharger."
        case .rejected(let status): return "Opération refusée (\(status)). Vérifie les champs et la connexion dans l’app web."
        case .invalidData: return "Données incompatibles. Vérifie les champs ou actualise l’app."
        case .keychain: return "Impossible de protéger la session sur cet iPhone."
        }
    }
}

enum CoachRules {
    static func origin(_ text: String) throws -> URL {
        guard let c = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              c.scheme == "https", let host = c.host, !host.isEmpty,
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil,
              c.path.isEmpty || c.path == "/", let url = c.url,
              c.port == nil || (1...65535).contains(c.port!) else { throw CoachFailure.invalidServer }
        return url
    }
    static func sameOrigin(_ a: URL, _ b: URL) -> Bool {
        a.scheme == b.scheme && a.host?.lowercased() == b.host?.lowercased() && (a.port ?? 443) == (b.port ?? 443)
    }
    static func restSeconds(_ raw: String) -> Int? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        func match(_ pattern: String) -> [Int]? {
            guard let regex = try? NSRegularExpression(pattern: pattern),
                  let m = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return nil }
            return (1..<m.numberOfRanges).compactMap { Range(m.range(at: $0), in: text).flatMap { Int(text[$0]) } }
        }
        let result: Int?
        if let n = match("^(\\d+)\\s*(?:s|sec|secs|secondes?|''|\"|″)$") { result = n[0] }
        else if let n = match("^(\\d+)\\s*(?:min|minutes?|'|′)$") { result = n[0] * 60 }
        else if let n = match("^(\\d+)\\s*['′:]\\s*(\\d{1,2})\\s*(?:s|''|″)?$"), n[1] < 60 { result = n[0] * 60 + n[1] }
        else { result = nil }
        return result.flatMap { (1...7200).contains($0) ? $0 : nil }
    }
}
