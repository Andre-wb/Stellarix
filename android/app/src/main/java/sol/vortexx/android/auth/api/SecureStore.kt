package sol.vortexx.android.auth.api

/**
 * Key/value store with OS-level encryption at rest.
 *
 * Responsibility: hold small secrets (JWTs, seed phrase, device keys).
 * NOT for arbitrary data — that goes to DataStore or Room. Keeping the
 * surface this narrow means consumers can't abuse it for bulk storage
 * and we can swap the backing Keystore-wrapped SharedPreferences for
 * e.g. AndroidX EncryptedFile in a later wave with no call-site churn.
 */
interface SecureStore {
    fun getString(key: String): String?
    fun putString(key: String, value: String?)
    fun clear()
}
