package sol.vortexx.android

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/**
 * Application entry point.
 *
 * `@HiltAndroidApp` triggers Hilt's code gen and sets up the component
 * tree for every @Inject across the app. Keeping this class empty means
 * Hilt owns the lifecycle — no globals, no singletons-by-hand. Every
 * wave from #4 onward will add providers via `@Module @InstallIn(...)`.
 */
@HiltAndroidApp
class VortexApp : Application()
