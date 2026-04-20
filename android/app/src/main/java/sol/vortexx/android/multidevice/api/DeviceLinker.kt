package sol.vortexx.android.multidevice.api

/**
 * Pair a new device to this user's account. Two flows:
 *   - This device is the OLD one → `generateCode()` returns a 6-digit
 *     link code shown to the user; they enter it on the new device.
 *   - This device is the NEW one → `redeemCode()` sends the code plus
 *     our freshly-generated X25519 pubkey; the server returns the
 *     encrypted-keys blob which we decrypt locally.
 */
interface DeviceLinker {
    suspend fun generateCode(): LinkCode?
    suspend fun redeemCode(code: String, newDevicePubHex: String): RedeemResult
}

data class LinkCode(val code: String, val expiresAt: Long)

sealed interface RedeemResult {
    data class Ok(val encryptedKeysBlob: String) : RedeemResult
    data class Error(val reason: String) : RedeemResult
}
