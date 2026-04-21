import Foundation
import Net

public struct SavedGifsFactory {
    public let gifs: SavedGifs
    public init(http: HttpClient) { self.gifs = HttpSavedGifs(http: http) }
}
