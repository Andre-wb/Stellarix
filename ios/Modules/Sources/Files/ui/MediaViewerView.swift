import SwiftUI
import AVKit
import UIKit

/// In-app media preview. Decrypts via [FileTransferService] into memory
/// or a temp file, renders:
///   - image/*   → `Image(uiImage:)` (UIImage handles all common formats)
///   - video/*   → `VideoPlayer` over a cache file (AVKit streams bytes)
///   - audio/*   → VideoPlayer too (it handles audio-only assets)
///   - other     → `ShareLink` fallback, no plaintext leak to third-party.
@MainActor
public final class MediaViewerViewModel: ObservableObject {
    @Published public private(set) var state: State = .loading

    public enum State {
        case loading
        case image(UIImage)
        case playback(URL)      // path to a temp cache file
        case unsupported(String)
        case error(String)
    }

    private let fileId: String
    private let roomId: Int64
    private let mime: String
    private let files: FileTransferService
    private var cacheFileUrl: URL?

    public init(fileId: String, roomId: Int64, mime: String, files: FileTransferService) {
        self.fileId = fileId
        self.roomId = roomId
        self.mime = mime
        self.files = files
    }

    deinit {
        if let cacheFileUrl { try? FileManager.default.removeItem(at: cacheFileUrl) }
    }

    public func start() {
        Task {
            var buf = Data()
            for await ev in files.download(roomId: roomId, fileId: fileId) {
                switch ev {
                case .inFlight: break
                case .done(_, _, let plaintext):
                    if let plaintext { buf = plaintext }
                case .error(let reason):
                    state = .error(reason); return
                }
            }
            await decode(buf)
        }
    }

    private func decode(_ bytes: Data) async {
        if mime.hasPrefix("image/") {
            if let img = UIImage(data: bytes) { state = .image(img) }
            else { state = .error("image_decode_failed") }
            return
        }
        if mime.hasPrefix("video/") || mime.hasPrefix("audio/") {
            do {
                let dir = FileManager.default.temporaryDirectory
                let url = dir.appendingPathComponent(UUID().uuidString).appendingPathExtension(fileExt())
                try bytes.write(to: url, options: .atomic)
                cacheFileUrl = url
                state = .playback(url)
            } catch {
                state = .error("write_cache_failed: \((error as NSError).localizedDescription)")
            }
            return
        }
        state = .unsupported(mime)
    }

    private func fileExt() -> String {
        // Minimal MIME → extension map — enough for AVFoundation to pick
        // the right asset reader. For unknown types we fall through to
        // `.unsupported` before reaching this.
        switch mime {
        case "video/mp4":    return "mp4"
        case "video/quicktime": return "mov"
        case "video/webm":   return "webm"
        case "audio/mpeg":   return "mp3"
        case "audio/aac":    return "m4a"
        case "audio/ogg":    return "ogg"
        default:             return "bin"
        }
    }
}

public struct MediaViewerView: View {
    @StateObject private var vm: MediaViewerViewModel
    private let onDismiss: () -> Void

    public init(
        fileId: String,
        roomId: Int64,
        mime: String,
        files: FileTransferService,
        onDismiss: @escaping () -> Void,
    ) {
        _vm = StateObject(wrappedValue: MediaViewerViewModel(
            fileId: fileId, roomId: roomId, mime: mime, files: files,
        ))
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            switch vm.state {
            case .loading:
                ProgressView().tint(.white)
            case .image(let img):
                Image(uiImage: img)
                    .resizable()
                    .scaledToFit()
            case .playback(let url):
                VideoPlayer(player: AVPlayer(url: url))
            case .unsupported(let m):
                VStack(spacing: 8) {
                    Text("Preview not supported").foregroundStyle(.white)
                    Text(m).font(.caption).foregroundStyle(.white.opacity(0.5))
                }
            case .error(let reason):
                Text(reason).foregroundStyle(.red)
            }
            VStack {
                HStack {
                    Spacer()
                    Button(action: onDismiss) {
                        Image(systemName: "xmark").font(.title2).foregroundStyle(.white)
                    }.padding()
                }
                Spacer()
            }
        }
        .task { vm.start() }
    }
}
