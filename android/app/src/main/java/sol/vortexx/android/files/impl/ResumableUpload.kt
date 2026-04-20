package sol.vortexx.android.files.impl

import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.Serializable
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.files.api.TransferProgress
import sol.vortexx.android.keys.api.KeyAcquisition
import sol.vortexx.android.keys.api.RoomKeyProvider
import sol.vortexx.android.net.impl.VortexHttpClient
import java.io.InputStream
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Chunked resumable upload for large files (> 50 MB). Each chunk is
 * independently AES-GCM encrypted so a partial upload doesn't leak the
 * rest of the file if the server aborts mid-stream.
 *
 * Server protocol (mirrors Vortex /api/files/resumable/*):
 *   POST  .../start   → { upload_id }
 *   PUT   .../{id}/chunk?index=N (ciphertext_hex body)
 *   POST  .../{id}/finish → { file_id }
 */
@Singleton
class ResumableUpload @Inject constructor(
    private val http: VortexHttpClient,
    private val aead: Aead,
    private val keys: RoomKeyProvider,
) {
    suspend fun upload(
        roomId: Long,
        source: InputStream,
        filename: String,
        sizeBytes: Long,
        chunkBytes: Int = DEFAULT_CHUNK,
    ): Flow<TransferProgress> = flow {
        val keyAcq = keys.keyFor(roomId)
        if (keyAcq !is KeyAcquisition.Ready) {
            emit(TransferProgress.Error("no_room_key")); return@flow
        }
        val key = Hex.decode(keyAcq.keyHex)

        val startResp = http.client.post("api/files/resumable/start") {
            contentType(ContentType.Application.Json)
            setBody(StartReq(room_id = roomId, filename = filename, size_bytes = sizeBytes))
        }
        if (!startResp.status.isSuccess()) {
            emit(TransferProgress.Error("start_http_${startResp.status.value}")); return@flow
        }
        val uploadId = startResp.body<StartResp>().upload_id

        val md = MessageDigest.getInstance("SHA-256")
        var index = 0
        var done = 0L
        val buf = ByteArray(chunkBytes)

        while (true) {
            val read = source.read(buf)
            if (read <= 0) break
            val chunkPlain = if (read == buf.size) buf else buf.copyOf(read)
            val ct = aead.encrypt(key, chunkPlain)
            md.update(ct)
            val resp = http.client.put("api/files/resumable/$uploadId/chunk?index=$index") {
                contentType(ContentType.Application.OctetStream)
                setBody(Hex.encode(ct))
            }
            if (!resp.status.isSuccess()) {
                emit(TransferProgress.Error("chunk_${index}_http_${resp.status.value}"))
                return@flow
            }
            index += 1
            done  += read
            emit(TransferProgress.InFlight(done = done, total = sizeBytes))
        }

        val finish = http.client.post("api/files/resumable/$uploadId/finish")
        if (!finish.status.isSuccess()) {
            emit(TransferProgress.Error("finish_http_${finish.status.value}")); return@flow
        }
        val body = finish.body<FinishResp>()
        emit(TransferProgress.Done(
            fileId = body.file_id,
            ciphertextHashHex = Hex.encode(md.digest()),
        ))
    }

    companion object { const val DEFAULT_CHUNK = 4 * 1024 * 1024 /* 4 MiB */ }

    @Serializable private data class StartReq(
        val room_id: Long, val filename: String, val size_bytes: Long,
    )
    @Serializable private data class StartResp(val upload_id: String)
    @Serializable private data class FinishResp(val file_id: String)
}
