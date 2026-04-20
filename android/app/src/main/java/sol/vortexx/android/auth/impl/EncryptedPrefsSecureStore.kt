package sol.vortexx.android.auth.impl

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import sol.vortexx.android.auth.api.SecureStore
import javax.inject.Inject
import javax.inject.Singleton

/**
 * [SecureStore] backed by AndroidX EncryptedSharedPreferences.
 *
 * Keys are wrapped by an AES256 master key held in AndroidKeyStore —
 * hardware-backed on Pixel / most flagships, software-backed on older
 * devices. Nothing leaves the secure storage even during auto-backup
 * (the file is listed in backup_rules.xml's exclude).
 */
@Singleton
class EncryptedPrefsSecureStore @Inject constructor(
    @ApplicationContext ctx: Context,
) : SecureStore {

    private val prefs: SharedPreferences = EncryptedSharedPreferences.create(
        ctx,
        "secure_prefs",
        MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    override fun getString(key: String): String? = prefs.getString(key, null)

    override fun putString(key: String, value: String?) {
        prefs.edit().apply {
            if (value == null) remove(key) else putString(key, value)
        }.apply()
    }

    override fun clear() { prefs.edit().clear().apply() }
}
