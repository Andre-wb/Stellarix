package sol.vortexx.android.stickers.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.stickers.api.StickerCatalog
import sol.vortexx.android.stickers.api.VoiceRecorder
import sol.vortexx.android.stickers.impl.AndroidVoiceRecorder
import sol.vortexx.android.stickers.impl.HttpStickerCatalog
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class StickersModule {
    @Binds @Singleton
    abstract fun bindStickerCatalog(impl: HttpStickerCatalog): StickerCatalog

    @Binds @Singleton
    abstract fun bindVoiceRecorder(impl: AndroidVoiceRecorder): VoiceRecorder
}
