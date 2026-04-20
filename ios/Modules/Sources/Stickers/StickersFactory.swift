import Foundation
import Net

public struct StickersFactory {
    public let catalog: StickerCatalog
    public let recorder: VoiceRecorder

    public init(http: HttpClient) {
        self.catalog = HttpStickerCatalog(http: http)
        self.recorder = AVAudioVoiceRecorder()
    }
}
