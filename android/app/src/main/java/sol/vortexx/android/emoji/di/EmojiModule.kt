package sol.vortexx.android.emoji.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.emoji.api.EmojiCatalog
import sol.vortexx.android.emoji.impl.AssetEmojiCatalog
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class EmojiModule {
    @Binds @Singleton
    abstract fun bindCatalog(impl: AssetEmojiCatalog): EmojiCatalog
}
