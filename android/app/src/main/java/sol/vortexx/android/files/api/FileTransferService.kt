package sol.vortexx.android.files.api

import kotlinx.coroutines.flow.Flow
import java.io.InputStream

/**
 * E2E-encrypted file up/downloads. Streams bytes so memory stays O(chunk)
 * even for gigabyte files. `Flow<TransferProgress>` lets the UI show a
 * progress bar without polling.
 */
interface FileTransferService {
    suspend fun upload(roomId: Long, source: InputStream, filename: String, sizeBytes: Long): Flow<TransferProgress>
    suspend fun download(roomId: Long, fileId: String, sink: (ByteArray) -> Unit): Flow<TransferProgress>
}

sealed interface TransferProgress {
    data class InFlight(val done: Long, val total: Long) : TransferProgress
    data class Done(val fileId: String, val ciphertextHashHex: String) : TransferProgress
    data class Error(val reason: String) : TransferProgress
}
