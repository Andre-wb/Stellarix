package sol.vortexx.android.ui.components

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import sol.vortexx.android.stickers.api.VoiceRecorder
import sol.vortexx.android.stickers.api.VoiceSession
import sol.vortexx.android.ui.theme.VortexPurple

/**
 * Composer attachment affordances: mic (hold to record) + file picker.
 * Keeps recording state locally — parent stays dumb.
 *
 * @param onVoiceReady  fired with the OGG/Opus bytes once the user releases mic.
 * @param onFilePicked  fired with the content URI the system returned.
 */
@Composable
fun AttachmentBar(
    recorder: VoiceRecorder,
    onVoiceReady: (ByteArray) -> Unit,
    onFilePicked: (Uri) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var session by remember { mutableStateOf<VoiceSession?>(null) }
    val recording = session != null

    val pickFile = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent(),
    ) { uri -> if (uri != null) onFilePicked(uri) }

    Row(modifier) {
        IconButton(onClick = { pickFile.launch("*/*") }) {
            Icon(
                imageVector = Icons.Filled.AttachFile,
                contentDescription = "Attach file",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(24.dp),
            )
        }

        Icon(
            imageVector = if (recording) Icons.Filled.Stop else Icons.Filled.Mic,
            contentDescription = if (recording) "Recording — release to send" else "Hold to record voice",
            tint = if (recording) VortexPurple else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .size(44.dp)
                .pointerInput(Unit) {
                    detectTapGestures(
                        // Press = begin recording; long-press counts too.
                        onPress = { offset ->
                            // Start the session on press-down; ask for cancel
                            // if the gesture is cancelled (pointer leaves) and
                            // send the clip on natural release.
                            var cancelled = false
                            scope.launch { session = recorder.start() }
                            try {
                                tryAwaitRelease().also { released ->
                                    if (!released) cancelled = true
                                }
                            } finally {
                                scope.launch {
                                    val s = session; session = null
                                    if (s != null) {
                                        if (cancelled) s.cancel()
                                        else {
                                            val bytes = s.stop()
                                            if (bytes.isNotEmpty()) onVoiceReady(bytes)
                                        }
                                    }
                                }
                            }
                        },
                    )
                },
        )
    }
}
