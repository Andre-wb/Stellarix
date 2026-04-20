package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.VideocamOff
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack
import sol.vortexx.android.calls.api.CallController
import sol.vortexx.android.calls.api.CallState
import sol.vortexx.android.calls.impl.WebRtcCallController
import javax.inject.Inject

@HiltViewModel
class CallViewModel @Inject constructor(
    controller: CallController,
    // Concrete type dependency intentional: the renderer needs access to
    // the shared EglBase context which is a WebRTC-specific detail kept
    // off the interface to avoid leaking libwebrtc into ../api.
    private val webrtc: WebRtcCallController,
) : ViewModel() {
    val state       = controller.state
    val localVideo  = webrtc.localVideo
    val remoteVideo = webrtc.remoteVideo
    val eglContext  get() = webrtc.eglBaseContext

    fun start(roomId: Long, video: Boolean) {
        viewModelScope.launch { webrtc.start(roomId, video) }
    }
    fun hangup() { viewModelScope.launch { webrtc.hangup() } }
    fun toggleMic(on: Boolean) { viewModelScope.launch { webrtc.toggleMic(on) } }
    fun toggleCam(on: Boolean) { viewModelScope.launch { webrtc.toggleCamera(on) } }
}

@Composable
fun CallScreen(
    roomId: Long,
    initialVideo: Boolean = false,
    onExit: () -> Unit,
    vm: CallViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val local by vm.localVideo.collectAsState()
    val remote by vm.remoteVideo.collectAsState()
    var micOn by remember { mutableStateOf(true) }
    var camOn by remember { mutableStateOf(initialVideo) }

    LaunchedEffect(roomId) { vm.start(roomId, initialVideo) }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        // Remote fills the whole viewport.
        if (remote != null) VideoSurface(
            track = remote!!,
            eglContext = vm.eglContext,
            modifier = Modifier.fillMaxSize(),
        ) else Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = when (val s = state) {
                    is CallState.Idle       -> "Idle"
                    is CallState.Ringing    -> "Ringing…"
                    is CallState.Connecting -> "Connecting…"
                    is CallState.Connected  -> "Connected · ${s.participantCount}"
                    is CallState.Ended      -> "Ended · ${s.reason}"
                },
                style = MaterialTheme.typography.titleLarge,
                color = Color.White,
            )
        }

        // Local PIP in top-right corner.
        if (local != null) Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(16.dp)
                .size(120.dp, 160.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(Color.DarkGray),
        ) {
            VideoSurface(
                track = local!!,
                eglContext = vm.eglContext,
                modifier = Modifier.fillMaxSize(),
            )
        }

        Row(
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 48.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            FloatingActionButton(
                onClick = { micOn = !micOn; vm.toggleMic(micOn) },
                containerColor = MaterialTheme.colorScheme.surface,
            ) {
                Icon(
                    if (micOn) Icons.Filled.Mic else Icons.Filled.MicOff,
                    contentDescription = "Mic",
                    tint = Color.White,
                )
            }
            FloatingActionButton(
                onClick = { camOn = !camOn; vm.toggleCam(camOn) },
                containerColor = MaterialTheme.colorScheme.surface,
            ) {
                Icon(
                    if (camOn) Icons.Filled.Videocam else Icons.Filled.VideocamOff,
                    contentDescription = "Camera",
                    tint = Color.White,
                )
            }
            FloatingActionButton(
                onClick = { vm.hangup(); onExit() },
                containerColor = MaterialTheme.colorScheme.error,
            ) { Icon(Icons.Filled.CallEnd, contentDescription = "Hang up", tint = Color.White) }
        }
    }
}

/**
 * Compose wrapper over [SurfaceViewRenderer]. Creates the view lazily,
 * inits it with the shared EGL context, binds the current [track], and
 * unbinds + releases on dispose. Rotation/scale are kept at default —
 * FIT_CENTER keeps the video within the given box without stretching.
 */
@Composable
private fun VideoSurface(
    track: VideoTrack,
    eglContext: org.webrtc.EglBase.Context,
    modifier: Modifier = Modifier,
) {
    val renderer = remember {
        object {
            var view: SurfaceViewRenderer? = null
        }
    }
    AndroidView(
        factory = { ctx ->
            SurfaceViewRenderer(ctx).also {
                it.init(eglContext, null)
                it.setEnableHardwareScaler(true)
                renderer.view = it
                track.addSink(it)
            }
        },
        modifier = modifier,
        update = { /* track pinned at factory time; re-bind on change below */ },
    )
    DisposableEffect(track) {
        // If the track swaps out (e.g. remote peer reconnects with a new
        // PeerConnection), rebind the sink.
        val r = renderer.view
        if (r != null) { track.addSink(r) }
        onDispose {
            renderer.view?.let {
                runCatching { track.removeSink(it) }
                it.release()
            }
            renderer.view = null
        }
    }
}
