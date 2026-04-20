package sol.vortexx.android.files.api

/**
 * Wave 15 media viewer — what screens ask for when the user taps an
 * attachment. Implementation launches an internal viewer Activity for
 * images / video / PDF without going through an external intent (keeps
 * the decrypted plaintext out of other apps' hands).
 */
interface MediaViewer {
    fun show(fileId: String, mimeType: String)
}
