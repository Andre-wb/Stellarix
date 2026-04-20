package sol.vortexx.android.calls.impl

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.webrtc.AudioTrack
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnection.RTCConfiguration
import org.webrtc.PeerConnectionFactory
import org.webrtc.SessionDescription
import org.webrtc.VideoSource
import org.webrtc.VideoTrack
import org.webrtc.audio.JavaAudioDeviceModule
import sol.vortexx.android.calls.api.CallController
import sol.vortexx.android.calls.api.CallHandle
import sol.vortexx.android.calls.api.CallInvitation
import sol.vortexx.android.calls.api.CallState
import sol.vortexx.android.ws.api.WsClient
import sol.vortexx.android.ws.api.WsFrame
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * WebRTC call controller — signaling over our WebSocket, media over
 * standard SRTP via a SFU the node brokers. The node exposes the SFU
 * URLs in the JSON payload once the call is authorised.
 *
 * Design split:
 *   - [PeerConnectionFactory] + single [PeerConnection] live here
 *   - SDP offer/answer and ICE candidates flow through [WsClient]
 *   - Lifecycle owned by [CallController.start] / [answer] / [hangup]
 *
 * Media UI (video surfaces, toggles, ringer) is in the CallScreen
 * composable — this class stays headless and testable.
 */
@Singleton
class WebRtcCallController @Inject constructor(
    @ApplicationContext private val appCtx: Context,
    private val ws: WsClient,
) : CallController {

    private val _state = MutableStateFlow<CallState>(CallState.Idle)
    override val state = _state.asStateFlow()

    // Exposed so the Compose layer can attach a SurfaceViewRenderer to
    // whichever track is currently live. Null between calls.
    private val _localVideo  = MutableStateFlow<VideoTrack?>(null)
    private val _remoteVideo = MutableStateFlow<VideoTrack?>(null)
    val localVideo  = _localVideo.asStateFlow()
    val remoteVideo = _remoteVideo.asStateFlow()

    /** Shared [EglBase] — the renderer needs this to init its surface. */
    val eglBaseContext get() = eglBase.eglBaseContext

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val json  = Json { ignoreUnknownKeys = true }

    private lateinit var factory: PeerConnectionFactory
    private var peer: PeerConnection? = null
    private var audioTrack: AudioTrack? = null
    private var videoTrack: VideoTrack? = null
    private var videoSource: VideoSource? = null
    private var currentCallId: String? = null
    // If a `call_offer` arrives before the user taps Answer, park it here
    // so answer() can pick it up without another WS round trip.
    private var pendingRemoteOffer: SessionDescription? = null
    private val eglBase: EglBase = EglBase.create()

    init { scope.launch { observeSignaling() } }

    override suspend fun start(roomId: Long, video: Boolean): CallHandle {
        ensureFactory()
        val callId = UUID.randomUUID().toString()
        currentCallId = callId
        _state.value = CallState.Connecting

        peer = createPeer()
        attachLocalMedia(video)

        val offer = createOffer(video)
        sendSignal(
            Signal(type = "call_offer", call_id = callId,
                   room_id = roomId, sdp = offer.description, video = video),
        )
        return CallHandle(callId)
    }

    override suspend fun answer(invitation: CallInvitation) {
        ensureFactory()
        currentCallId = invitation.callId
        _state.value = CallState.Connecting
        peer = createPeer()
        attachLocalMedia(invitation.video)
        // The remote SDP offer arrived out-of-band via `call_offer`;
        // observeSignaling pushes it into this lambda so we can set
        // remote + create + send answer in one call.
        pendingRemoteOffer?.let { sdp ->
            pendingRemoteOffer = null
            setRemoteThenAnswer(sdp, invitation.video)
        }
    }

    override suspend fun hangup() {
        sendSignal(Signal(type = "call_hangup", call_id = currentCallId))
        peer?.close(); peer = null
        audioTrack = null; videoTrack = null; videoSource?.dispose(); videoSource = null
        _localVideo.value = null; _remoteVideo.value = null
        currentCallId = null
        _state.value = CallState.Ended("local_hangup")
    }

    override suspend fun toggleMic(on: Boolean)    { audioTrack?.setEnabled(on) }
    override suspend fun toggleCamera(on: Boolean) { videoTrack?.setEnabled(on) }

    // ── WebRTC plumbing ─────────────────────────────────────────────────

    private fun ensureFactory() {
        if (::factory.isInitialized) return
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(appCtx)
                .createInitializationOptions(),
        )
        factory = PeerConnectionFactory.builder()
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true))
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(eglBase.eglBaseContext))
            .setAudioDeviceModule(JavaAudioDeviceModule.builder(appCtx).createAudioDeviceModule())
            .createPeerConnectionFactory()
    }

    private fun createPeer(): PeerConnection {
        val cfg = RTCConfiguration(listOf(/* TURN/STUN resolved from node */))
        return factory.createPeerConnection(cfg, object : PeerConnection.Observer {
            override fun onIceCandidate(c: IceCandidate) {
                scope.launch {
                    sendSignal(Signal(
                        type = "ice_candidate",
                        call_id = currentCallId,
                        sdp_mid = c.sdpMid,
                        sdp_m_line_index = c.sdpMLineIndex,
                        candidate = c.sdp,
                    ))
                }
            }
            override fun onIceConnectionChange(s: PeerConnection.IceConnectionState) {
                if (s == PeerConnection.IceConnectionState.CONNECTED) {
                    _state.value = CallState.Connected(participantCount = 2)
                }
                if (s == PeerConnection.IceConnectionState.DISCONNECTED ||
                    s == PeerConnection.IceConnectionState.FAILED
                ) _state.value = CallState.Ended("peer_${s.name.lowercase()}")
            }
            override fun onAddStream(stream: MediaStream) {
                // Publish the first incoming video track so the Compose
                // renderer can attach. Audio tracks are played back by
                // the AudioDeviceModule automatically.
                stream.videoTracks.firstOrNull()?.let { _remoteVideo.value = it }
            }
            override fun onRemoveStream(stream: MediaStream) {}
            override fun onDataChannel(p0: org.webrtc.DataChannel?) {}
            override fun onRenegotiationNeeded() {}
            override fun onSignalingChange(p0: PeerConnection.SignalingState?) {}
            override fun onIceConnectionReceivingChange(p0: Boolean) {}
            override fun onIceGatheringChange(p0: PeerConnection.IceGatheringState?) {}
            override fun onAddTrack(p0: org.webrtc.RtpReceiver?, p1: Array<out MediaStream>?) {}
            override fun onIceCandidatesRemoved(p0: Array<out IceCandidate>?) {}
        }) ?: error("peer connection creation failed")
    }

    private fun attachLocalMedia(video: Boolean) {
        val p = peer ?: return
        val audio = factory.createAudioSource(MediaConstraints())
        audioTrack = factory.createAudioTrack("audio0", audio).also { p.addTrack(it) }
        if (video) {
            videoSource = factory.createVideoSource(false)
            videoTrack  = factory.createVideoTrack("video0", videoSource).also {
                p.addTrack(it); _localVideo.value = it
            }
        }
    }

    private suspend fun createOffer(video: Boolean): SessionDescription {
        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", video.toString()))
        }
        val sdp = kotlinx.coroutines.suspendCancellableCoroutine<SessionDescription?> { cont ->
            peer?.createOffer(object : SdpObserverAdapter() {
                override fun onCreateSuccess(s: SessionDescription) { cont.resumeWith(Result.success(s)) }
                override fun onCreateFailure(error: String?)        { cont.resumeWith(Result.success(null)) }
            }, constraints)
        } ?: error("SDP offer failed")
        peer?.setLocalDescription(SdpObserverAdapter(), sdp)
        return sdp
    }

    private suspend fun observeSignaling() = ws.incoming.collect { frame ->
        val obj = runCatching { json.parseToJsonElement(frame.text).jsonObject }.getOrNull() ?: return@collect
        val type = obj["type"]?.jsonPrimitive?.content ?: return@collect
        if (!type.startsWith("call_") && type != "ice_candidate") return@collect

        when (type) {
            "call_offer", "call_invite" -> {
                // Incoming call: park the remote SDP and flip to Ringing.
                _state.value = CallState.Ringing
                obj["sdp"]?.jsonPrimitive?.content?.let {
                    pendingRemoteOffer = SessionDescription(SessionDescription.Type.OFFER, it)
                }
            }
            "call_accept" -> {
                // Remote side accepted — set their answer SDP so media flows.
                val sdpText = obj["sdp"]?.jsonPrimitive?.content ?: return@collect
                peer?.setRemoteDescription(
                    SdpObserverAdapter(),
                    SessionDescription(SessionDescription.Type.ANSWER, sdpText),
                )
            }
            "call_hangup" -> {
                peer?.close(); peer = null
                pendingRemoteOffer = null
                _state.value = CallState.Ended("remote_hangup")
            }
            "ice_candidate" -> {
                val cand = IceCandidate(
                    obj["sdp_mid"]?.jsonPrimitive?.content,
                    obj["sdp_m_line_index"]?.jsonPrimitive?.content?.toIntOrNull() ?: 0,
                    obj["candidate"]?.jsonPrimitive?.content ?: "",
                )
                peer?.addIceCandidate(cand)
            }
        }
    }

    /**
     * Callee path: we already have a [PeerConnection] with local media
     * attached; set the remote offer, compute our answer, and send it.
     */
    private suspend fun setRemoteThenAnswer(remoteSdp: SessionDescription, video: Boolean) {
        val p = peer ?: return
        p.setRemoteDescription(SdpObserverAdapter(), remoteSdp)

        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", video.toString()))
        }
        val answer = kotlinx.coroutines.suspendCancellableCoroutine<SessionDescription?> { cont ->
            p.createAnswer(object : SdpObserverAdapter() {
                override fun onCreateSuccess(s: SessionDescription) { cont.resumeWith(Result.success(s)) }
                override fun onCreateFailure(e: String?)           { cont.resumeWith(Result.success(null)) }
            }, constraints)
        } ?: return
        p.setLocalDescription(SdpObserverAdapter(), answer)
        sendSignal(Signal(
            type = "call_accept", call_id = currentCallId,
            sdp = answer.description, video = video,
        ))
    }

    private suspend fun sendSignal(s: Signal) {
        ws.send(WsFrame(json.encodeToString(Signal.serializer(), s)))
    }

    @Serializable
    private data class Signal(
        val type: String,
        val call_id: String? = null,
        val room_id: Long? = null,
        val sdp: String? = null,
        val video: Boolean? = null,
        val candidate: String? = null,
        val sdp_mid: String? = null,
        val sdp_m_line_index: Int? = null,
    )
}

/** Convenience base — suppresses the 4 overrides we rarely need. */
private open class SdpObserverAdapter : org.webrtc.SdpObserver {
    override fun onCreateSuccess(p0: SessionDescription?) {}
    override fun onSetSuccess() {}
    override fun onCreateFailure(p0: String?) {}
    override fun onSetFailure(p0: String?) {}
}
