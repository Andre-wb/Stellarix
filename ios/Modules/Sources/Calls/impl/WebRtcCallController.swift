import Foundation
import WebRTC
import WS

/// libwebrtc-backed [CallController].
///
/// Mirrors Android's `WebRtcCallController`:
///   * Signaling (offer/answer/ICE) flows through [WsClient].
///   * Media over SRTP via the node's SFU; TURN/STUN URLs come from
///     [IceConfigProvider].
///   * `localVideoTrack` / `remoteVideoTrack` are exposed as
///     AsyncStreams so the SwiftUI layer binds `RTCMTLVideoView` without
///     knowing anything about PeerConnection lifecycle.
///
/// Concurrency: single actor — every WebRTC mutation hops onto the
/// actor's executor, so we never need explicit locks around `peer`.
public actor WebRtcCallController: CallController {

    // MARK: outputs
    public nonisolated var state: AsyncStream<CallState> { stateBridge.stream() }

    /// Exposed as `nonisolated` so SwiftUI can subscribe without await.
    public nonisolated var localVideoTrack: AsyncStream<RTCVideoTrack?>  { localTrackBridge.stream() }
    public nonisolated var remoteVideoTrack: AsyncStream<RTCVideoTrack?> { remoteTrackBridge.stream() }

    // MARK: deps
    private let ws: WsClient
    private let ice: IceConfigProvider

    // MARK: state
    private lazy var factory: RTCPeerConnectionFactory = {
        RTCInitializeSSL()
        return RTCPeerConnectionFactory(
            encoderFactory: RTCDefaultVideoEncoderFactory(),
            decoderFactory: RTCDefaultVideoDecoderFactory(),
        )
    }()
    private var peer: RTCPeerConnection?
    private var peerObserver: PeerObserver?
    private var audioTrack: RTCAudioTrack?
    private var videoTrack: RTCVideoTrack?
    private var videoCapturer: RTCCameraVideoCapturer?
    private var currentCallId: String?
    /// SDP offer we received before the user tapped Answer.
    private var pendingRemoteOffer: RTCSessionDescription?

    private let stateBridge        = Bridge<CallState>(initial: .idle)
    private let localTrackBridge   = Bridge<RTCVideoTrack?>(initial: nil)
    private let remoteTrackBridge  = Bridge<RTCVideoTrack?>(initial: nil)

    private var signalingTask: Task<Void, Never>?

    public init(ws: WsClient, ice: IceConfigProvider) {
        self.ws = ws
        self.ice = ice
    }

    // MARK: CallController ---------------------------------------------

    public func start(roomId: Int64, video: Bool) async -> CallHandle {
        await ensureSignalingObserver()
        let callId = UUID().uuidString
        currentCallId = callId
        stateBridge.publish(.connecting)

        await buildPeer()
        attachLocalMedia(video: video)

        guard let peer else { return CallHandle(callId: callId) }
        let offer = await createOffer(peer: peer, video: video)
        if let offer {
            await setLocalDescription(peer, offer)
            await sendSignal(Signal(
                type: "call_offer", call_id: callId, room_id: roomId,
                sdp: offer.sdp, video: video,
            ))
        }
        return CallHandle(callId: callId)
    }

    public func answer(_ invitation: CallInvitation) async {
        await ensureSignalingObserver()
        currentCallId = invitation.callId
        stateBridge.publish(.connecting)
        await buildPeer()
        attachLocalMedia(video: invitation.video)

        if let offer = pendingRemoteOffer {
            pendingRemoteOffer = nil
            await setRemoteThenAnswer(offer: offer, video: invitation.video)
        }
    }

    public func hangup() async {
        await sendSignal(Signal(type: "call_hangup", call_id: currentCallId))
        teardown()
        stateBridge.publish(.ended(reason: "local_hangup"))
    }

    public func toggleMic(_ on: Bool) async    { audioTrack?.isEnabled = on }
    public func toggleCamera(_ on: Bool) async { videoTrack?.isEnabled = on }

    // MARK: WebRTC plumbing --------------------------------------------

    private func buildPeer() async {
        let servers = await ice.current().map { s in
            RTCIceServer(urlStrings: s.urls,
                         username: s.username,
                         credential: s.credential)
        }
        let cfg = RTCConfiguration()
        cfg.iceServers = servers
        cfg.sdpSemantics = .unifiedPlan
        cfg.continualGatheringPolicy = .gatherContinually

        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let observer = PeerObserver(owner: self)
        self.peerObserver = observer
        self.peer = factory.peerConnection(with: cfg, constraints: constraints, delegate: observer)
    }

    private func attachLocalMedia(video: Bool) {
        guard let peer else { return }

        let audioConstraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let audioSource = factory.audioSource(with: audioConstraints)
        let audio = factory.audioTrack(with: audioSource, trackId: "audio0")
        peer.add(audio, streamIds: ["vortex-local"])
        self.audioTrack = audio

        if video {
            let videoSource = factory.videoSource()
            let video = factory.videoTrack(with: videoSource, trackId: "video0")
            peer.add(video, streamIds: ["vortex-local"])
            self.videoTrack = video
            localTrackBridge.publish(video)

            // Start front camera. Production would pick resolution from
            // call settings; defaults stay conservative to keep bandwidth
            // low out of the box.
            let capturer = RTCCameraVideoCapturer(delegate: videoSource)
            self.videoCapturer = capturer
            startFrontCamera(capturer: capturer)
        }
    }

    private func startFrontCamera(capturer: RTCCameraVideoCapturer) {
        guard let device = RTCCameraVideoCapturer.captureDevices().first(where: { $0.position == .front }),
              let format = RTCCameraVideoCapturer.supportedFormats(for: device).first
        else { return }
        let fps = Int(format.videoSupportedFrameRateRanges
            .map { Int($0.maxFrameRate) }.max() ?? 30)
        capturer.startCapture(with: device, format: format, fps: min(fps, 30))
    }

    private func createOffer(peer: RTCPeerConnection, video: Bool) async -> RTCSessionDescription? {
        let constraints = RTCMediaConstraints(
            mandatoryConstraints: [
                "OfferToReceiveAudio": "true",
                "OfferToReceiveVideo": video ? "true" : "false",
            ],
            optionalConstraints: nil,
        )
        return await withCheckedContinuation { cont in
            peer.offer(for: constraints) { sdp, _ in cont.resume(returning: sdp) }
        }
    }

    private func setLocalDescription(_ peer: RTCPeerConnection, _ sdp: RTCSessionDescription) async {
        _ = await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            peer.setLocalDescription(sdp) { _ in cont.resume() }
        }
    }
    private func setRemoteDescription(_ peer: RTCPeerConnection, _ sdp: RTCSessionDescription) async {
        _ = await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            peer.setRemoteDescription(sdp) { _ in cont.resume() }
        }
    }

    /// Callee path — we already have a peer with local media attached.
    /// Set the remote offer, build and send our answer.
    private func setRemoteThenAnswer(offer: RTCSessionDescription, video: Bool) async {
        guard let peer else { return }
        await setRemoteDescription(peer, offer)
        let constraints = RTCMediaConstraints(
            mandatoryConstraints: [
                "OfferToReceiveAudio": "true",
                "OfferToReceiveVideo": video ? "true" : "false",
            ],
            optionalConstraints: nil,
        )
        let answer = await withCheckedContinuation { (cont: CheckedContinuation<RTCSessionDescription?, Never>) in
            peer.answer(for: constraints) { sdp, _ in cont.resume(returning: sdp) }
        }
        guard let answer else { return }
        await setLocalDescription(peer, answer)
        await sendSignal(Signal(
            type: "call_accept", call_id: currentCallId,
            sdp: answer.sdp, video: video,
        ))
    }

    private func teardown() {
        videoCapturer?.stopCapture()
        videoCapturer = nil
        peer?.close(); peer = nil
        peerObserver = nil
        audioTrack = nil; videoTrack = nil
        currentCallId = nil
        pendingRemoteOffer = nil
        localTrackBridge.publish(nil)
        remoteTrackBridge.publish(nil)
    }

    // MARK: signaling ---------------------------------------------------

    private func ensureSignalingObserver() async {
        guard signalingTask == nil else { return }
        let stream = ws.incoming
        signalingTask = Task { [weak self] in
            for await text in stream {
                await self?.onIncoming(text)
            }
        }
    }

    private func onIncoming(_ text: String) async {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = obj["type"] as? String else { return }

        switch type {
        case "call_offer", "call_invite":
            stateBridge.publish(.ringing)
            if let sdp = obj["sdp"] as? String {
                pendingRemoteOffer = RTCSessionDescription(type: .offer, sdp: sdp)
            }
        case "call_accept":
            guard let sdp = obj["sdp"] as? String, let peer else { return }
            await setRemoteDescription(peer, RTCSessionDescription(type: .answer, sdp: sdp))
        case "call_hangup":
            teardown()
            stateBridge.publish(.ended(reason: "remote_hangup"))
        case "ice_candidate":
            guard let candidate = obj["candidate"] as? String else { return }
            let mid = obj["sdp_mid"] as? String
            let mline = (obj["sdp_m_line_index"] as? Int) ?? 0
            peer?.add(RTCIceCandidate(sdp: candidate, sdpMLineIndex: Int32(mline), sdpMid: mid)) { _ in }
        default: break
        }
    }

    fileprivate func publishRemoteVideo(_ track: RTCVideoTrack) {
        remoteTrackBridge.publish(track)
    }

    fileprivate func publishIceCandidate(_ candidate: RTCIceCandidate) async {
        await sendSignal(Signal(
            type: "ice_candidate",
            call_id: currentCallId,
            candidate: candidate.sdp,
            sdp_mid: candidate.sdpMid,
            sdp_m_line_index: Int(candidate.sdpMLineIndex),
        ))
    }

    fileprivate func publishConnectionChange(_ s: RTCIceConnectionState) {
        switch s {
        case .connected, .completed: stateBridge.publish(.connected(participantCount: 2))
        case .disconnected, .failed, .closed: stateBridge.publish(.ended(reason: "ice_\(s.rawValue)"))
        default: break
        }
    }

    private func sendSignal(_ s: Signal) async {
        guard let data = try? JSONEncoder().encode(s),
              let text = String(data: data, encoding: .utf8) else { return }
        await ws.send(text)
    }

    private struct Signal: Codable {
        let type: String
        let call_id: String?
        var room_id: Int64? = nil
        var sdp: String? = nil
        var video: Bool? = nil
        var candidate: String? = nil
        var sdp_mid: String? = nil
        var sdp_m_line_index: Int? = nil
    }
}

/// RTCPeerConnectionDelegate bridge — forwards events to the actor.
/// A plain class (not actor-isolated) because delegate callbacks come
/// from libwebrtc's private thread; we hop to the actor by `Task`.
private final class PeerObserver: NSObject, RTCPeerConnectionDelegate {
    weak var owner: WebRtcCallController?
    init(owner: WebRtcCallController) { self.owner = owner }

    func peerConnection(_ pc: RTCPeerConnection, didAdd rtpReceiver: RTCRtpReceiver, streams: [RTCMediaStream]) {
        guard let track = rtpReceiver.track as? RTCVideoTrack, let owner else { return }
        Task { await owner.publishRemoteVideo(track) }
    }
    func peerConnection(_ pc: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        guard let owner else { return }
        Task { await owner.publishIceCandidate(candidate) }
    }
    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        guard let owner else { return }
        Task { await owner.publishConnectionChange(newState) }
    }

    // Unused but required by the protocol.
    func peerConnection(_ pc: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ pc: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ pc: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ pc: RTCPeerConnection) {}
    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ pc: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ pc: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}

/// Thread-safe one-value fan-out.
final class Bridge<Value: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var subs: [UUID: AsyncStream<Value>.Continuation] = [:]
    private var last: Value?

    init(initial: Value?) { self.last = initial }

    func publish(_ v: Value) {
        lock.lock()
        last = v
        let copy = subs.values
        lock.unlock()
        for c in copy { c.yield(v) }
    }

    func stream() -> AsyncStream<Value> {
        AsyncStream { cont in
            lock.lock()
            if let last { cont.yield(last) }
            let id = UUID(); subs[id] = cont
            lock.unlock()
            cont.onTermination = { @Sendable _ in
                self.lock.lock(); self.subs.removeValue(forKey: id); self.lock.unlock()
            }
        }
    }
}
