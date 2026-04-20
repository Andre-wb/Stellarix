package sol.vortexx.android.ws.impl

import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.websocket.DefaultClientWebSocketSession
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocketSession
import io.ktor.client.request.header
import io.ktor.client.request.url
import io.ktor.http.HttpHeaders
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import io.ktor.websocket.send
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.net.api.AuthTokenSource
import sol.vortexx.android.net.api.BaseUrlProvider
import sol.vortexx.android.ws.api.WsClient
import sol.vortexx.android.ws.api.WsFrame
import sol.vortexx.android.ws.api.WsState
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Ktor-backed WebSocket with exponential-backoff reconnect and an
 * outbound queue. The client lazily starts when something calls
 * [start] — the activity triggers it after a successful login.
 */
@Singleton
class KtorWsClient @Inject constructor(
    private val baseUrlProvider: BaseUrlProvider,
    private val tokens: AuthTokenSource,
) : WsClient {

    private val _state   = MutableStateFlow<WsState>(WsState.Disconnected)
    override val state   = _state.asStateFlow()

    private val _incoming = MutableSharedFlow<WsFrame>(
        extraBufferCapacity = 256, onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    override val incoming = _incoming.asSharedFlow()

    private val outgoing = MutableSharedFlow<WsFrame>(
        extraBufferCapacity = 64,  onBufferOverflow = BufferOverflow.SUSPEND,
    )

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loopJob: Job? = null

    // Bounded backoff so a dead node doesn't hammer the network.
    private val backoffMs = longArrayOf(500, 1_000, 2_000, 5_000, 10_000)

    override suspend fun send(frame: WsFrame) { outgoing.emit(frame) }

    override suspend fun start() {
        if (loopJob?.isActive == true) return
        loopJob = scope.launch { runLoop() }
    }

    override suspend fun stop() {
        loopJob?.cancel(); loopJob = null
        _state.value = WsState.Disconnected
    }

    private suspend fun runLoop() {
        var attempt = 0
        while (true) {
            _state.value = WsState.Connecting
            val session = tryConnect()
            if (session == null) {
                val wait = backoffMs[attempt.coerceAtMost(backoffMs.lastIndex)]
                attempt += 1
                _state.value = WsState.Failed("connect_fail — retrying in ${wait}ms")
                delay(wait)
                continue
            }
            attempt = 0
            _state.value = WsState.Connected
            pump(session)
            session.cancel()
            _state.value = WsState.Disconnected
            delay(backoffMs.first())
        }
    }

    private suspend fun tryConnect(): DefaultClientWebSocketSession? {
        val base = baseUrlProvider.current() ?: return null
        val wsBase = base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
        val token = tokens.accessToken()

        val http = HttpClient(OkHttp) { install(WebSockets) }
        return runCatching {
            http.webSocketSession {
                url("$wsBase/ws")
                if (!token.isNullOrBlank()) header(HttpHeaders.Authorization, "Bearer $token")
            }
        }.getOrNull()
    }

    private suspend fun pump(session: DefaultClientWebSocketSession) = CoroutineScope(Dispatchers.IO).apply {
        val send = launch {
            outgoing.collect { frame ->
                runCatching { session.send(frame.text) }
            }
        }
        for (frame in session.incoming) {
            if (frame is Frame.Text) _incoming.tryEmit(WsFrame(frame.readText()))
        }
        send.cancel()
    }.run { /* noop — suspensions drive the loop */ }
}
