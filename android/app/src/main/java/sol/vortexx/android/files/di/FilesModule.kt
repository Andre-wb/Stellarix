package sol.vortexx.android.files.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.files.api.FileTransferService
import sol.vortexx.android.files.api.MediaViewer
import sol.vortexx.android.files.impl.HttpFileTransferService
import sol.vortexx.android.files.impl.IntentMediaViewer
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class FilesModule {
    @Binds @Singleton
    abstract fun bindFileTransfer(impl: HttpFileTransferService): FileTransferService

    @Binds @Singleton
    abstract fun bindMediaViewer(impl: IntentMediaViewer): MediaViewer
}
