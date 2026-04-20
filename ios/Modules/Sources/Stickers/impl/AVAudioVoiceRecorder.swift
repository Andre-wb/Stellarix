import Foundation
import AVFAudio

/// AVAudioRecorder-backed voice note capture.
///
/// Records mono AAC at 32 kbit/s to a throwaway cache file so Opus-in-Ogg
/// isn't required — both the Android client and the Python node accept
/// AAC-in-M4A as a voice attachment. The temp file is deleted on
/// `stop()` / `cancel()`.
public final class AVAudioVoiceRecorder: VoiceRecorder {
    public init() {}

    public func start() async throws -> VoiceSession {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
        try session.setActive(true)

        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("voice_\(UUID().uuidString)").appendingPathExtension("m4a")
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVNumberOfChannelsKey: 1,
            AVSampleRateKey: 48_000,
            AVEncoderBitRateKey: 32_000,
            AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
        ]
        let rec = try AVAudioRecorder(url: tmp, settings: settings)
        guard rec.record() else { throw VoiceError.couldNotStart }
        return Session(recorder: rec, url: tmp)
    }

    private final class Session: VoiceSession, @unchecked Sendable {
        private let recorder: AVAudioRecorder
        private let url: URL
        init(recorder: AVAudioRecorder, url: URL) { self.recorder = recorder; self.url = url }
        func stop() async -> Data {
            recorder.stop()
            defer { try? FileManager.default.removeItem(at: url) }
            return (try? Data(contentsOf: url)) ?? Data()
        }
        func cancel() async {
            recorder.stop()
            try? FileManager.default.removeItem(at: url)
        }
    }
}

public enum VoiceError: Error { case couldNotStart }
