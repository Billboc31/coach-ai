import Foundation

// Cookies are sent explicitly to one origin. Never follow API redirects carrying a session.
final class NoRedirect: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
@MainActor
final class CoachAPI {
    let origin: URL
    private(set) var saved: SavedSession?
    private let delegate = NoRedirect()
    private let configuration: URLSessionConfiguration?
    private lazy var session: URLSession = {
        let c = configuration ?? URLSessionConfiguration.ephemeral
        c.httpShouldSetCookies = false
        c.httpCookieStorage = nil
        c.urlCache = nil
        c.timeoutIntervalForRequest = 30
        c.timeoutIntervalForResource = 90
        return URLSession(configuration: c, delegate: delegate, delegateQueue: nil)
    }()
    init(origin: URL, saved: SavedSession? = nil, configuration: URLSessionConfiguration? = nil) {
        self.origin = origin; self.saved = saved; self.configuration = configuration
    }
    func login(key: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["access_key": key])
        let (_, response) = try await send("/api/login", method: "POST", body: body, authenticated: false)
        let fields = response.allHeaderFields.reduce(into: [String: String]()) { fields, entry in
            if let key = entry.key as? String, let value = entry.value as? String { fields[key] = value }
        }
        guard let cookie = HTTPCookie.cookies(withResponseHeaderFields: fields, for: origin).first(where: { $0.name == "coach_session" }),
              let expiry = cookie.expiresDate, expiry > Date() else { throw CoachFailure.invalidData }
        let value = SavedSession(origin: origin, token: cookie.value, expires: expiry)
        try SessionVault.save(value)
        saved = value
    }
    func send(_ path: String, method: String = "GET", body: Data? = nil, authenticated: Bool = true) async throws -> (Data, HTTPURLResponse) {
        guard path.hasPrefix("/api/"), let url = URL(string: path, relativeTo: origin)?.absoluteURL,
              CoachRules.sameOrigin(url, origin) else { throw CoachFailure.invalidServer }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(origin.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), forHTTPHeaderField: "Origin")
        if authenticated {
            guard let saved, saved.expires > Date() else { throw CoachFailure.signedOut }
            request.setValue("coach_session=\(saved.token)", forHTTPHeaderField: "Cookie")
        }
        let (data, raw) = try await session.data(for: request)
        guard let response = raw as? HTTPURLResponse else { throw CoachFailure.invalidData }
        switch response.statusCode {
        case 200...299: return (data, response)
        case 401: throw CoachFailure.signedOut
        case 409: throw CoachFailure.conflict
        default: throw CoachFailure.rejected(response.statusCode)
        }
    }
    func get<T: Decodable>(_ path: String) async throws -> T {
        let (data, _) = try await send(path)
        return try JSONDecoder().decode(T.self, from: data)
    }
    func start(program: String, day: String) async throws -> Workout {
        let body = try JSONSerialization.data(withJSONObject: ["program_id": program, "day_id": day])
        let (data, _) = try await send("/api/gym/workouts", method: "POST", body: body)
        return try JSONDecoder().decode(Workout.self, from: data)
    }
    func save(_ workout: Workout, progression: [String: Double], finish: Bool) async throws -> Workout {
        let sets = workout.sets
        guard sets.values.allSatisfy({ !$0.isEmpty && $0.count <= 30 && $0.allSatisfy(\.valid) }) else { throw CoachFailure.invalidData }
        let body = WorkoutUpdate(revision: workout.revision, sets: sets, progression: progression, finish: finish)
        let (data, _) = try await send("/api/gym/workouts/\(workout.id)", method: "PUT", body: JSONEncoder().encode(body))
        return try JSONDecoder().decode(Workout.self, from: data)
    }
    func delete(_ workout: Workout) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["revision": workout.revision])
        _ = try await send("/api/gym/workouts/\(workout.id)", method: "DELETE", body: body)
    }
}
