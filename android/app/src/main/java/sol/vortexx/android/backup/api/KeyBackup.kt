package sol.vortexx.android.backup.api

/**
 * Encrypted key vault stored server-side.
 * The passphrase never leaves the device: we derive an AES key via
 * Argon2id, encrypt the keypair blob, and upload the ciphertext plus
 * the kdf parameters. Server holds ciphertext it can't read.
 */
interface KeyBackup {
    suspend fun backup(passphrase: CharArray): Boolean
    suspend fun restore(passphrase: CharArray): Boolean
}
