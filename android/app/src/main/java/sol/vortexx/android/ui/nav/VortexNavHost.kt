package sol.vortexx.android.ui.nav

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.auth.api.Session
import sol.vortexx.android.ui.screens.AuthScreen
import sol.vortexx.android.ui.screens.BootstrapScreen
import sol.vortexx.android.ui.screens.BotsScreen
import sol.vortexx.android.ui.screens.CallScreen
import sol.vortexx.android.ui.screens.ChatScreen
import sol.vortexx.android.ui.screens.RoomsListScreen
import sol.vortexx.android.ui.screens.SearchScreen
import sol.vortexx.android.ui.screens.SettingsScreen
import sol.vortexx.android.ui.screens.ChannelFeedsScreen
import sol.vortexx.android.ui.screens.GravitixDocsScreen
import sol.vortexx.android.ui.screens.IdeScreen
import sol.vortexx.android.ui.screens.SpacesScreen
import sol.vortexx.android.ui.screens.ThreadsScreen

object Routes {
    const val BOOTSTRAP = "bootstrap"
    const val AUTH      = "auth"
    const val ROOMS     = "rooms"
    const val SETTINGS  = "settings"
    const val SPACES    = "spaces"
    const val BOTS      = "bots"
    const val SEARCH    = "search"
    const val DOCS      = "gravitix-docs"
    const val IDE       = "ide"
    const val THREADS   = "threads/{roomId}"
    const val FEEDS     = "feeds/{roomId}"
    const val CHAT      = "chat/{roomId}"
    const val CALL      = "call/{roomId}/{video}"

    fun chat(roomId: Long)     = "chat/$roomId"
    fun threads(roomId: Long)  = "threads/$roomId"
    fun feeds(roomId: Long)    = "feeds/$roomId"
    fun call(roomId: Long, video: Boolean) = "call/$roomId/$video"
}

@Composable
fun VortexNavHost(
    authRepo: AuthRepository,
    nav: NavHostController = rememberNavController(),
) {
    val session by authRepo.session.collectAsState(initial = Session.LoggedOut)
    var baseUrlReady by remember { mutableStateOf(false) }

    val start = when {
        !baseUrlReady                -> Routes.BOOTSTRAP
        session is Session.LoggedOut -> Routes.AUTH
        else                         -> Routes.ROOMS
    }

    NavHost(navController = nav, startDestination = start) {
        composable(Routes.BOOTSTRAP) {
            BootstrapScreen(onConnected = {
                baseUrlReady = true
                nav.navigate(if (session is Session.LoggedOut) Routes.AUTH else Routes.ROOMS) {
                    popUpTo(Routes.BOOTSTRAP) { inclusive = true }
                }
            })
        }
        composable(Routes.AUTH) {
            AuthScreen(onLoggedIn = {
                nav.navigate(Routes.ROOMS) { popUpTo(Routes.AUTH) { inclusive = true } }
            })
        }
        composable(Routes.ROOMS) {
            RoomsListScreen(
                onRoomClick     = { id -> nav.navigate(Routes.chat(id)) },
                onSettingsClick = { nav.navigate(Routes.SETTINGS) },
                onOpenSpaces    = { nav.navigate(Routes.SPACES) },
                onOpenBots      = { nav.navigate(Routes.BOTS) },
                onOpenSearch    = { nav.navigate(Routes.SEARCH) },
                onOpenDocs      = { nav.navigate(Routes.DOCS) },
            )
        }
        composable(Routes.SETTINGS) { SettingsScreen(onBack = { nav.popBackStack() }) }
        composable(Routes.SPACES)   { SpacesScreen(  onBack = { nav.popBackStack() }) }
        composable(Routes.BOTS)     { BotsScreen(    onBack = { nav.popBackStack() }) }
        composable(Routes.SEARCH)   {
            SearchScreen(
                onResultClick = { roomId, _ -> nav.navigate(Routes.chat(roomId)) },
                onBack        = { nav.popBackStack() },
            )
        }
        composable(
            Routes.CHAT,
            arguments = listOf(navArgument("roomId") { type = NavType.LongType }),
        ) { entry ->
            val roomId = entry.arguments?.getLong("roomId") ?: return@composable
            ChatScreen(
                roomId = roomId,
                onOpenThread = { tid -> nav.navigate(Routes.chat(tid)) },
                onBack       = { nav.popBackStack() },
            )
        }
        composable(
            Routes.THREADS,
            arguments = listOf(navArgument("roomId") { type = NavType.LongType }),
        ) { entry ->
            val roomId = entry.arguments?.getLong("roomId") ?: return@composable
            ThreadsScreen(
                roomId        = roomId,
                onThreadClick = { /* negative-id convention: thread pseudo-room */ },
                onBack        = { nav.popBackStack() },
            )
        }
        composable(Routes.DOCS) { GravitixDocsScreen(onBack = { nav.popBackStack() }) }
        composable(Routes.IDE)  { IdeScreen(onBack = { nav.popBackStack() }) }
        composable(
            Routes.FEEDS,
            arguments = listOf(navArgument("roomId") { type = NavType.LongType }),
        ) { entry ->
            val roomId = entry.arguments?.getLong("roomId") ?: return@composable
            ChannelFeedsScreen(roomId = roomId, onBack = { nav.popBackStack() })
        }
        composable(
            Routes.CALL,
            arguments = listOf(
                navArgument("roomId") { type = NavType.LongType },
                navArgument("video")  { type = NavType.BoolType  },
            ),
        ) { entry ->
            val roomId = entry.arguments?.getLong("roomId") ?: return@composable
            val video  = entry.arguments?.getBoolean("video") ?: false
            CallScreen(roomId = roomId, initialVideo = video, onExit = { nav.popBackStack() })
        }
    }
}
