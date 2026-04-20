import SwiftUI
import WebRTC

/// Wave 17 call UI.
///
/// Remote track fills the screen, local track shows as a PIP in the
/// top-right. Start/hangup buttons are fixed at the bottom. The screen
/// takes the concrete controller type so we can read the nonisolated
/// track streams directly (protocols can't carry the WebRTC types
/// without leaking libwebrtc into Calls/api).
@MainActor
public final class CallViewModel: ObservableObject {
    @Published public private(set) var state: CallState = .idle
    @Published public fileprivate(set) var local: RTCVideoTrack?
    @Published public fileprivate(set) var remote: RTCVideoTrack?
    @Published public var micOn: Bool = true
    @Published public var camOn: Bool = true

    private let controller: WebRtcCallController
    private var observers: [Task<Void, Never>] = []

    public init(controller: WebRtcCallController, initialCamera: Bool) {
        self.controller = controller
        self.camOn = initialCamera

        observers.append(Task { [state = controller.state] in
            for await s in state { await MainActor.run { self.state = s } }
        })
        observers.append(Task { [track = controller.localVideoTrack] in
            for await t in track { await MainActor.run { self.local = t } }
        })
        observers.append(Task { [track = controller.remoteVideoTrack] in
            for await t in track { await MainActor.run { self.remote = t } }
        })
    }

    deinit { observers.forEach { $0.cancel() } }

    public func start(roomId: Int64, video: Bool) async {
        _ = await controller.start(roomId: roomId, video: video)
    }

    public func hangup() async { await controller.hangup() }

    public func toggleMic() async {
        micOn.toggle()
        await controller.toggleMic(micOn)
    }
    public func toggleCam() async {
        camOn.toggle()
        await controller.toggleCamera(camOn)
    }
}

public struct CallScreen: View {
    @StateObject private var vm: CallViewModel
    private let roomId: Int64
    private let initialVideo: Bool
    private let onExit: () -> Void

    public init(
        controller: WebRtcCallController,
        roomId: Int64,
        initialVideo: Bool,
        onExit: @escaping () -> Void,
    ) {
        _vm = StateObject(wrappedValue: CallViewModel(controller: controller, initialCamera: initialVideo))
        self.roomId = roomId
        self.initialVideo = initialVideo
        self.onExit = onExit
    }

    public var body: some View {
        ZStack {
            if let remote = vm.remote {
                VideoTrackView(track: remote)
                    .ignoresSafeArea()
            } else {
                Color.black.ignoresSafeArea()
                VStack {
                    Text(statusText)
                        .font(.title3).foregroundStyle(.white)
                }
            }

            if let local = vm.local {
                VideoTrackView(track: local)
                    .frame(width: 120, height: 160)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding()
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
            }

            VStack { Spacer(); controlBar }
        }
        .task { await vm.start(roomId: roomId, video: initialVideo) }
    }

    private var controlBar: some View {
        HStack(spacing: 16) {
            ControlButton(systemImage: vm.micOn ? "mic.fill" : "mic.slash.fill",
                          tint: .white.opacity(0.15)) {
                Task { await vm.toggleMic() }
            }
            ControlButton(systemImage: vm.camOn ? "video.fill" : "video.slash.fill",
                          tint: .white.opacity(0.15)) {
                Task { await vm.toggleCam() }
            }
            ControlButton(systemImage: "phone.down.fill", tint: .red) {
                Task { await vm.hangup(); onExit() }
            }
        }
        .padding(.bottom, 48)
    }

    private var statusText: String {
        switch vm.state {
        case .idle:          "Idle"
        case .ringing:       "Ringing…"
        case .connecting:    "Connecting…"
        case .connected(let n): "Connected · \(n)"
        case .ended(let r):  "Ended · \(r)"
        }
    }
}

private struct ControlButton: View {
    let systemImage: String
    let tint: Color
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 22))
                .foregroundStyle(.white)
                .frame(width: 60, height: 60)
                .background(tint, in: Circle())
        }
    }
}

/// RTCMTLVideoView wrapper for SwiftUI. Re-binds `track` via
/// `updateUIView` so the same surface smoothly swaps when the remote
/// peer reconnects mid-call.
struct VideoTrackView: UIViewRepresentable {
    let track: RTCVideoTrack

    func makeUIView(context: Context) -> RTCMTLVideoView {
        let view = RTCMTLVideoView()
        view.videoContentMode = .scaleAspectFill
        track.add(view)
        context.coordinator.bound = (track, view)
        return view
    }

    func updateUIView(_ view: RTCMTLVideoView, context: Context) {
        if context.coordinator.bound?.0 !== track {
            context.coordinator.bound?.0.remove(view)
            track.add(view)
            context.coordinator.bound = (track, view)
        }
    }

    static func dismantleUIView(_ view: RTCMTLVideoView, coordinator: Coordinator) {
        coordinator.bound?.0.remove(view)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var bound: (RTCVideoTrack, RTCMTLVideoView)?
    }
}
