package sol.vortexx.android.ws.api

import kotlinx.coroutines.flow.Flow

/**
 * Long-lived WebSocket to the node. Single responsibility: keep a
 * connection open and hand out events. Message encode/decode + room
 * key handling live in higher layers.
 */
interface WsClient {
    val state: Flow<WsState>
    val incoming: Flow<WsFrame>
    suspend fun send(frame: WsFrame)
    suspend fun start()
    suspend fun stop()
}

sealed interface WsState {
    data object Disconnected : WsState
    data object Connecting : WsState
    data object Connected : WsState
    data class Failed(val reason: String) : WsState
}

/**
 * Opaque text frame — the chat feature carries its own JSON shape on top.
 * Keeping this one layer dumb means adding a new message type doesn't
 * require touching the WS layer at all.
 */
@JvmInline
value class WsFrame(val text: String)
