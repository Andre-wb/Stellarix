package sol.vortexx.android.feeds.api

import kotlinx.coroutines.flow.Flow
import sol.vortexx.android.db.entities.ChannelFeedEntity

/**
 * RSS / Atom / JSON feed subscriptions for a channel. The server does
 * the actual fetching (once per N minutes) and posts items as normal
 * messages. The client only manages subscribe/unsubscribe.
 */
interface ChannelFeedRepository {
    fun observe(roomId: Long): Flow<List<ChannelFeedEntity>>
    suspend fun refresh(roomId: Long): Boolean
    suspend fun subscribe(roomId: Long, url: String, feedType: String = "rss"): Boolean
    suspend fun unsubscribe(feedId: Long): Boolean
}
