import XCTest
@testable import CoachAI

final class CoachAITests: XCTestCase {
    func testDraftsStaySeparateAcrossOwnersAndServers() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let origin = URL(string: "https://example.com")!
        let other = URL(string: "https://other.example.com")!
        var workout = Workout(id: "synthetic", title: "Demo", started_at: "2026-01-01", finished_at: nil, revision: 1, suggestions_applied: true, exercises: [])
        try DraftVault.save(WorkoutDraft(owner: "owner-a", origin: origin, workout: workout, progression: [:], index: 0), directory: directory)
        workout.revision = 2
        try DraftVault.save(WorkoutDraft(owner: "owner-b", origin: origin, workout: workout, progression: [:], index: 0), directory: directory)
        XCTAssertEqual(DraftVault.load(owner: "owner-a", origin: origin, directory: directory)?.workout.revision, 1)
        XCTAssertEqual(DraftVault.load(owner: "owner-b", origin: origin, directory: directory)?.workout.revision, 2)
        XCTAssertNil(DraftVault.load(owner: "owner-a", origin: other, directory: directory))
        try DraftVault.clear(owner: "owner-b", origin: origin, directory: directory)
        XCTAssertNotNil(DraftVault.load(owner: "owner-a", origin: origin, directory: directory))
        XCTAssertNil(DraftVault.load(owner: "owner-b", origin: origin, directory: directory))
    }
    func testOriginsRejectSecretAndCallbackURLs() throws {
        for bad in ["http://example.com", "https://user:secret@example.com", "https://example.com/api", "https://example.com?token=private", "https://example.com/#callback", "file:///tmp/test"] {
            XCTAssertThrowsError(try CoachRules.origin(bad))
        }
        let base = try CoachRules.origin(" https://example.com/ ")
        XCTAssertTrue(CoachRules.sameOrigin(base, URL(string: "https://example.com:443/api/gym")!))
        XCTAssertFalse(CoachRules.sameOrigin(base, URL(string: "https://other.example.com")!))
        XCTAssertFalse(CoachRules.sameOrigin(base, URL(string: "https://example.com:8443")!))
        XCTAssertFalse(CoachRules.sameOrigin(base, URL(string: "http://example.com")!))
    }
    func testRestParserDoesNotGuessAmbiguousPrescriptions() {
        XCTAssertEqual(CoachRules.restSeconds("30\""), 30)
        XCTAssertEqual(CoachRules.restSeconds("1'"), 60)
        XCTAssertEqual(CoachRules.restSeconds("1'30"), 90)
        XCTAssertEqual(CoachRules.restSeconds("2 min"), 120)
        for raw in ["", "30 à 60 s", "1'\n2'", "0 s", "121 min", "1:90", "à volonté"] {
            XCTAssertNil(CoachRules.restSeconds(raw))
        }
    }
    func testMissingValuesAreNotZeroAndCompletionNeedsARecord() throws {
        let raw = Data(#"{"weight":null,"reps":null,"seconds":null,"done":false}"#.utf8)
        var row = try JSONDecoder().decode(LoggedSet.self, from: raw)
        XCTAssertNil(row.weight); XCTAssertNil(row.reps); XCTAssertTrue(row.valid)
        row.done = true; XCTAssertFalse(row.valid)
        row.seconds = 30; XCTAssertTrue(row.valid)
        row.weight = .infinity; XCTAssertFalse(row.valid)
        row.weight = 2001; XCTAssertFalse(row.valid)
        row.weight = 10; row.reps = -1; XCTAssertFalse(row.valid)
    }
    func testBackendFixtureRampAndRecordedSetsRemainDistinct() throws {
        let data = Data(#"{"id":"sample","title":"Demo","started_at":"2026-01-01T12:00:00Z","finished_at":null,"revision":3,"suggestions_applied":false,"exercises":[{"id":"press","name":"Presse","reps":"12\n8\n5","rest":"30\"\n1'\n1'","logged_sets":[{"weight":25,"reps":12,"done":true}],"suggested_sets":[{"weight":30,"reps":12,"done":false},{"weight":35,"reps":8,"done":false},{"weight":40,"reps":5,"done":false}]}]}"#.utf8)
        var workout = try JSONDecoder().decode(Workout.self, from: data)
        workout.applySuggestions()
        XCTAssertEqual(workout.exercises[0].logged_sets?.first?.weight, 25)
        XCTAssertEqual(workout.exercises[0].logged_sets?.count, 1)
        workout.exercises[0].logged_sets?[0].done = false
        workout.applySuggestions()
        XCTAssertEqual(workout.exercises[0].logged_sets?.map(\.reps), [12, 8, 5])
        XCTAssertEqual(workout.exercises[0].restText(at: 0), "30\"")
        XCTAssertEqual(workout.exercises[0].restText(at: 1), "1'")
        XCTAssertEqual(workout.exercises[0].logged_sets?.filter(\.done).count, 0)
    }
    func testRevisionAndUnknownMeasurementsSurviveUpdateEncoding() throws {
        let update = WorkoutUpdate(revision: 7, sets: ["demo": [LoggedSet(weight: nil, reps: 8, seconds: nil, done: true)]], progression: ["demo": 2.5], finish: false)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(update)) as? [String: Any])
        XCTAssertEqual(json["revision"] as? Int, 7)
        XCTAssertEqual(json["suggestions_applied"] as? Bool, true)
        let sets = try XCTUnwrap(json["sets"] as? [String: [[String: Any]]])
        XCTAssertNil(sets["demo"]?[0]["weight"])
        XCTAssertEqual(sets["demo"]?[0]["reps"] as? Int, 8)
    }
}

final class MockProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try Self.handler!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}
final class CoachAPITests: XCTestCase {
    @MainActor
    func testAuthenticatedRequestUsesExactOriginAndCookie() async throws {
        let origin = URL(string: "https://example.com")!
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        let saved = SavedSession(origin: origin, token: "synthetic-test-session", expires: Date().addingTimeInterval(100))
        let client = CoachAPI(origin: origin, saved: saved, configuration: configuration)
        MockProtocol.handler = { request in
            XCTAssertEqual(request.url?.absoluteString, "https://example.com/api/gym")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Origin"), "https://example.com")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cookie"), "coach_session=synthetic-test-session")
            return (200, Data(#"{"programs":[],"workouts":[]}"#.utf8))
        }
        defer { MockProtocol.handler = nil }
        let result: GymOverview = try await client.get("/api/gym")
        XCTAssertTrue(result.programs.isEmpty)
        do { _ = try await client.send("https://other.example.com/api/gym"); XCTFail("Origin escape allowed") }
        catch { XCTAssertTrue(error is CoachFailure) }
    }
    @MainActor
    func testConflictIsNotRetriedAndExpiredSessionDoesNotSend() async throws {
        let origin = URL(string: "https://example.com")!
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockProtocol.self]
        var calls = 0
        MockProtocol.handler = { _ in calls += 1; return (409, Data()) }
        defer { MockProtocol.handler = nil }
        let client = CoachAPI(origin: origin, saved: SavedSession(origin: origin, token: "synthetic", expires: Date().addingTimeInterval(100)), configuration: configuration)
        do { _ = try await client.send("/api/gym/workouts/demo", method: "PUT"); XCTFail("Conflict accepted") }
        catch CoachFailure.conflict { } catch { XCTFail("Wrong failure") }
        XCTAssertEqual(calls, 1)
        let expired = CoachAPI(origin: origin, saved: SavedSession(origin: origin, token: "synthetic", expires: .distantPast), configuration: configuration)
        do { _ = try await expired.send("/api/gym"); XCTFail("Expired session sent") }
        catch CoachFailure.signedOut { } catch { XCTFail("Wrong failure") }
        XCTAssertEqual(calls, 1)
    }
}
