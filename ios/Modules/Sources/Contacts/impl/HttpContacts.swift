import Foundation
import Net

public actor HttpContacts: Contacts {
    private let http: HttpClient
    public init(http: HttpClient) { self.http = http }

    private struct Wrap: Codable { let contacts: [Contact] }
    private struct AddBody: Codable { let username: String }

    public func list() async -> [Contact] {
        let req = HttpRequest.get("/api/contacts")
        return (try? await http.send(req, Wrap.self).contacts) ?? []
    }

    public func add(username: String) async -> Contact? {
        guard let req = try? HttpRequest.postJson("/api/contacts", body: AddBody(username: username)) else { return nil }
        return try? await http.send(req, Contact.self)
    }

    public func remove(id: Int64) async {
        let req = HttpRequest.delete("/api/contacts/\(id)")
        _ = try? await http.send(req)
    }

    public func search(_ query: String) async -> [Contact] {
        let req = HttpRequest.get("/api/contacts/search", query: [URLQueryItem(name: "q", value: query)])
        return (try? await http.send(req, Wrap.self).contacts) ?? []
    }
}
