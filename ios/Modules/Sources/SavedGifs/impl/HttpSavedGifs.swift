import Foundation
import Net

public actor HttpSavedGifs: SavedGifs {
    private let http: HttpClient
    public init(http: HttpClient) { self.http = http }

    private struct Wrap: Codable { let gifs: [SavedGif] }
    private struct AddBody: Codable { let url: String; let width: Int; let height: Int }

    public func list() async -> [SavedGif] {
        let req = HttpRequest.get("/api/saved_gifs")
        return (try? await http.send(req, Wrap.self).gifs) ?? []
    }

    public func add(url: String, width: Int, height: Int) async -> SavedGif? {
        guard let req = try? HttpRequest.postJson("/api/saved_gifs", body: AddBody(url: url, width: width, height: height)) else { return nil }
        return try? await http.send(req, SavedGif.self)
    }

    public func remove(id: Int64) async {
        let req = HttpRequest.delete("/api/saved_gifs/\(id)")
        _ = try? await http.send(req)
    }
}
