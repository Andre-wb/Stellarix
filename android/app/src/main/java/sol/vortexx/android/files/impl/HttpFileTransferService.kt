package sol.vortexx.android.files.impl

import io.ktor.client.call.body
import io.ktor.client.request.forms.formData
import io.ktor.client.request.forms.submitFormWithBinaryData
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import io.ktor.utils.io.ByteReadChannel
import io.ktor.utils.io.jvm.javaio.toInputStream
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.Serializable
import sol.vortexx.android.crypto.api.Aead
import sol.vortexx.android.crypto.util.Hex
import sol.vortexx.android.files.api.FileTransferService
import sol.vortexx.android.files.api.TransferProgress
import sol.vortexx.android.keys.api.KeyAcquisition
import sol.vortexx.android.keys.api.RoomKeyProvider
import sol.vortexx.android.net.impl.VortexHttpClient
import java.io.InputStream
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Encrypts + uploads a file to `/api/files/upload` then downloads +
 * decrypts on demand. The underlying server supports resumable uploads
 * (`/api/files/resumable/*`) — this first cut does single-shot upload;
 * resumable chunking lands once the basic path is verified end-to-end.
 */
@Singleton
class HttpFileTransferService @Inject constructor(
    private val http: VortexHttpClient,
    private val aead: Aead,
    private val keys: RoomKeyProvider,
) : FileTransferService {

    override suspend fun upload(
        roomId: Long,
        source: InputStream,
        filename: String,
        sizeBytes: Long,
    ): Flow<TransferProgress> = flow {
        val keyAcq = keys.keyFor(roomId)
        if (keyAcq !is KeyAcquisition.Ready) {
            emit(TransferProgress.Error("no_room_key:${(keyAcq as? KeyAcquisition.Error)?.reason ?: "pending"}"))
            return@flow
        }

        // For phase 1 we buffer the whole file, encrypt in one shot. Large
        // files land in Wave 14.5 with streaming chunked AEAD.
        val plaintext = source.use { it.readBytes() }
        val packed = aead.encrypt(Hex.decode(keyAcq.keyHex), plaintext)
        val ctHex = Hex.encode(packed)
        emit(TransferProgress.InFlight(done = plaintext.size.toLong(), total = sizeBytes))

        val resp = runCatching {
            http.client.submitFormWithBinaryData(
                url = "api/files/upload",
                formData = formData {
                    append("room_id", roomId.toString())
                    append("filename", filename)
                    append("ciphertext_hex", ctHex)
                },
            )
        }.getOrElse {
            emit(TransferProgress.Error(it.message ?: "io_error")); return@flow
        }

        if (!resp.status.isSuccess()) {
            emit(TransferProgress.Error("http_${resp.status.value}")); return@flow
        }
        val body = resp.body<UploadResp>()
        val ctHash = MessageDigest.getInstance("SHA-256").digest(packed)
        emit(TransferProgress.Done(fileId = body.file_id, ciphertextHashHex = Hex.encode(ctHash)))
    }

    override suspend fun download(
        roomId: Long,
        fileId: String,
        sink: (ByteArray) -> Unit,
    ): Flow<TransferProgress> = callbackFlow {
        val keyAcq = keys.keyFor(roomId)
        if (keyAcq !is KeyAcquisition.Ready) {
            trySend(TransferProgress.Error("no_room_key")); close(); awaitClose(); return@callbackFlow
        }
        val resp = runCatching { http.client.get("api/files/$fileId") }.getOrNull()
        if (resp == null || !resp.status.isSuccess()) {
            trySend(TransferProgress.Error("fetch_failed")); close(); awaitClose(); return@callbackFlow
        }

        val ctHex = resp.bodyAsChannel().toInputStream().bufferedReader().readText()
        val packed = Hex.decode(ctHex.trim())
        val plaintext = runCatching { aead.decrypt(Hex.decode(keyAcq.keyHex), packed) }
            .getOrElse { trySend(TransferProgress.Error("decrypt_failed")); close(); awaitClose(); return@callbackFlow }

        sink(plaintext)
        val hash = MessageDigest.getInstance("SHA-256").digest(packed)
        trySend(TransferProgress.Done(fileId = fileId, ciphertextHashHex = Hex.encode(hash)))
        close()
        awaitClose()
    }

    @Serializable private data class UploadResp(val file_id: String, val size: Long)
}
