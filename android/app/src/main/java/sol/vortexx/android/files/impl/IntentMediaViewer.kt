package sol.vortexx.android.files.impl

import android.content.Context
import android.content.Intent
import dagger.hilt.android.qualifiers.ApplicationContext
import sol.vortexx.android.files.api.MediaViewer
import sol.vortexx.android.ui.activities.MediaViewerActivity
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Launches [MediaViewerActivity] — an internal viewer. Deliberately avoids
 * `Intent.ACTION_VIEW` to keep decrypted plaintext out of third-party apps.
 */
@Singleton
class IntentMediaViewer @Inject constructor(
    @ApplicationContext private val ctx: Context,
) : MediaViewer {
    override fun show(fileId: String, mimeType: String) {
        val i = Intent(ctx, MediaViewerActivity::class.java).apply {
            putExtra(MediaViewerActivity.EXTRA_FILE_ID, fileId)
            putExtra(MediaViewerActivity.EXTRA_MIME_TYPE, mimeType)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(i)
    }
}
