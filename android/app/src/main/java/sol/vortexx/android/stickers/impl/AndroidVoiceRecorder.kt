package sol.vortexx.android.stickers.impl

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import sol.vortexx.android.stickers.api.VoiceRecorder
import sol.vortexx.android.stickers.api.VoiceSession
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Records a single-take voice note using Android's MediaRecorder into
 * an OGG/Opus file under `cacheDir`. `stop()` returns the raw bytes and
 * deletes the temp file — nothing touches disk after return.
 */
@Singleton
class AndroidVoiceRecorder @Inject constructor(
    @ApplicationContext private val ctx: Context,
) : VoiceRecorder {

    override suspend fun start(): VoiceSession {
        val outFile = File.createTempFile("voice_", ".ogg", ctx.cacheDir)
        @Suppress("DEPRECATION")
        val rec = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            MediaRecorder(ctx) else MediaRecorder()
        rec.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.OGG)
            setAudioEncoder(MediaRecorder.AudioEncoder.OPUS)
            setAudioSamplingRate(48_000)
            setAudioEncodingBitRate(24_000)
            setOutputFile(outFile.absolutePath)
            prepare(); start()
        }
        return Session(rec, outFile)
    }

    private class Session(private val rec: MediaRecorder, private val file: File) : VoiceSession {
        override suspend fun stop(): ByteArray {
            try { rec.stop() } catch (_: Throwable) { /* too-short clips throw; fall through */ }
            rec.release()
            val bytes = file.readBytes()
            file.delete()
            return bytes
        }
        override suspend fun cancel() {
            try { rec.stop() } catch (_: Throwable) {}
            rec.release()
            file.delete()
        }
    }
}
