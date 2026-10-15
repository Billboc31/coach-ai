import Foundation
import Security
import CryptoKit

// Session only, never the personal access key or provider tokens.
enum SessionVault {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "coach-ai.session", kSecAttrAccount as String: "current"]
    }
    static func load() -> SavedSession? {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(SavedSession.self, from: data)
    }
    static func save(_ session: SavedSession) throws {
        let data = try JSONEncoder().encode(session)
        var q = query
        q[kSecValueData as String] = data
        q[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let result = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if result == errSecItemNotFound {
            guard SecItemAdd(q as CFDictionary, nil) == errSecSuccess else { throw CoachFailure.keychain }
        } else if result != errSecSuccess { throw CoachFailure.keychain }
    }
    static func clear() { SecItemDelete(query as CFDictionary) }
}

enum DraftVault {
    private static func file(owner: String, origin: URL, directory: URL? = nil) throws -> URL {
        var dir = try directory ?? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        dir.appendPathComponent("CoachAI", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try dir.setResourceValues(values)
        let scope = "\(origin.scheme ?? "https")://\(origin.host?.lowercased() ?? ""):\(origin.port ?? 443)|\(owner)"
        let digest = SHA256.hash(data: Data(scope.utf8)).map { String(format: "%02x", $0) }.joined()
        return dir.appendingPathComponent("draft-\(digest).json")
    }
    static func load(owner: String, origin: URL, directory: URL? = nil) -> WorkoutDraft? {
        guard let path = try? file(owner: owner, origin: origin, directory: directory), let data = try? Data(contentsOf: path),
              let draft = try? JSONDecoder().decode(WorkoutDraft.self, from: data),
              draft.owner == owner, CoachRules.sameOrigin(draft.origin, origin) else { return nil }
        return draft
    }
    static func save(_ draft: WorkoutDraft, directory: URL? = nil) throws {
        try JSONEncoder().encode(draft).write(to: file(owner: draft.owner, origin: draft.origin, directory: directory), options: [.atomic, .completeFileProtection])
    }
    static func clear(owner: String, origin: URL, directory: URL? = nil) throws {
        let path = try file(owner: owner, origin: origin, directory: directory)
        if FileManager.default.fileExists(atPath: path.path) { try FileManager.default.removeItem(at: path) }
    }
}
