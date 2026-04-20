package sol.vortexx.android.ui.activities

import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.flow.collectLatest
import sol.vortexx.android.files.api.FileTransferService
import sol.vortexx.android.files.api.TransferProgress
import sol.vortexx.android.ui.theme.VortexTheme
import java.io.ByteArrayOutputStream
import javax.inject.Inject

/**
 * In-app viewer: decrypts a file to RAM / temp dir and renders it in
 * Compose. Images use [BitmapFactory]; video/pdf will land once the
 * file pipeline can stream-decrypt chunks.
 *
 * Opened via [sol.vortexx.android.files.impl.IntentMediaViewer] so the
 * plaintext never leaves this process via a share intent.
 */
@AndroidEntryPoint
class MediaViewerActivity : ComponentActivity() {

    @Inject lateinit var files: FileTransferService

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val fileId = intent.getStringExtra(EXTRA_FILE_ID) ?: run { finish(); return }
        val mime   = intent.getStringExtra(EXTRA_MIME_TYPE) ?: "application/octet-stream"
        val roomId = intent.getLongExtra(EXTRA_ROOM_ID, 0L)

        setContent { VortexTheme { ViewerBody(roomId = roomId, fileId = fileId, mime = mime) } }
    }

    @Composable
    private fun ViewerBody(roomId: Long, fileId: String, mime: String) {
        var bytes by remember { mutableStateOf<ByteArray?>(null) }
        var error by remember { mutableStateOf<String?>(null) }

        LaunchedEffect(fileId) {
            val buf = ByteArrayOutputStream()
            files.download(roomId, fileId) { chunk -> buf.write(chunk) }.collectLatest {
                if (it is TransferProgress.Done) bytes = buf.toByteArray()
                if (it is TransferProgress.Error) error = it.reason
            }
        }

        Box(Modifier.fillMaxSize().background(Color.Black), contentAlignment = Alignment.Center) {
            when {
                error != null -> Text(error!!, color = Color.White)
                bytes == null -> CircularProgressIndicator(color = Color.White)
                mime.startsWith("image/") -> {
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes!!.size)
                    if (bmp != null) Image(bmp.asImageBitmap(), contentDescription = null)
                    else Text("Unable to decode image", color = Color.White)
                }
                mime.startsWith("video/") || mime.startsWith("audio/") ->
                    VideoPreview(bytes!!)
                else -> Text("Preview not yet supported for $mime", color = Color.White)
            }
        }
    }

    /**
     * ExoPlayer-backed preview. Writes the decrypted bytes to cache and
     * plays from there so we don't need a custom DataSource. The cache
     * file is deleted when the activity is destroyed.
     */
    @Composable
    private fun VideoPreview(bytes: ByteArray) {
        val ctx = androidx.compose.ui.platform.LocalContext.current
        val file = androidx.compose.runtime.remember {
            java.io.File.createTempFile("vortex_media_", ".bin", ctx.cacheDir).apply {
                writeBytes(bytes)
            }
        }
        val exo = androidx.compose.runtime.remember(file) {
            androidx.media3.exoplayer.ExoPlayer.Builder(ctx).build().apply {
                setMediaItem(androidx.media3.common.MediaItem.fromUri(android.net.Uri.fromFile(file)))
                prepare(); playWhenReady = true
            }
        }
        androidx.compose.runtime.DisposableEffect(exo) {
            onDispose { exo.release(); file.delete() }
        }
        androidx.compose.ui.viewinterop.AndroidView(
            factory = {
                androidx.media3.ui.PlayerView(it).apply { player = exo }
            },
            modifier = Modifier.fillMaxSize(),
        )
    }

    companion object {
        const val EXTRA_FILE_ID   = "file_id"
        const val EXTRA_ROOM_ID   = "room_id"
        const val EXTRA_MIME_TYPE = "mime"
    }
}
