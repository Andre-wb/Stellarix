package sol.vortexx.android.calls.api

import kotlinx.coroutines.flow.Flow

/**
 * Wave 17 — audio/video calls over WebRTC, routed through the node's
 * SFU bridge. The controller exposes a tiny verb set so screens don't
 * have to know about PeerConnections or SDP.
 */
interface CallController {
    val state: Flow<CallState>
    suspend fun start(roomId: Long, video: Boolean): CallHandle
    suspend fun answer(invitation: CallInvitation)
    suspend fun hangup()
    suspend fun toggleMic(on: Boolean)
    suspend fun toggleCamera(on: Boolean)
}

sealed interface CallState {
    data object Idle : CallState
    data object Ringing : CallState
    data object Connecting : CallState
    data class Connected(val participantCount: Int) : CallState
    data class Ended(val reason: String) : CallState
}

data class CallHandle(val callId: String)
data class CallInvitation(val callId: String, val fromUserId: Long, val video: Boolean)
