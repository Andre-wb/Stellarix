package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
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
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import sol.vortexx.android.calls.api.CallController
import sol.vortexx.android.calls.api.CallState
import javax.inject.Inject

@HiltViewModel
class CallViewModel @Inject constructor(
    private val controller: CallController,
) : ViewModel() {
    val state = controller.state

    fun start(roomId: Long, video: Boolean) {
        viewModelScope.launch { controller.start(roomId, video) }
    }
    fun hangup() { viewModelScope.launch { controller.hangup() } }
    fun toggleMic(on: Boolean) { viewModelScope.launch { controller.toggleMic(on) } }
    fun toggleCam(on: Boolean) { viewModelScope.launch { controller.toggleCamera(on) } }
}

@Composable
fun CallScreen(
    roomId: Long,
    initialVideo: Boolean = false,
    onExit: () -> Unit,
    vm: CallViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var micOn by remember { mutableStateOf(true) }
    var camOn by remember { mutableStateOf(initialVideo) }

    androidx.compose.runtime.LaunchedEffect(roomId) { vm.start(roomId, initialVideo) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            // Avatar placeholder — local/remote VideoTextureView surfaces
            // are attached in the next iteration of CallScreen.
            Box(
                modifier = Modifier
                    .size(140.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.surface),
            )
            Text(
                text = when (val s = state) {
                    is CallState.Idle       -> "Idle"
                    is CallState.Ringing    -> "Ringing…"
                    is CallState.Connecting -> "Connecting…"
                    is CallState.Connected  -> "In call · ${s.participantCount} participants"
                    is CallState.Ended      -> "Ended · ${s.reason}"
                },
                style = MaterialTheme.typography.titleLarge,
                color = Color.White,
                modifier = Modifier.padding(top = 20.dp),
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
