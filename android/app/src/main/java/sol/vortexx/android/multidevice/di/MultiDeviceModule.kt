package sol.vortexx.android.multidevice.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.multidevice.api.DeviceLinker
import sol.vortexx.android.multidevice.impl.HttpDeviceLinker
import sol.vortexx.android.keys.api.SealedKeyClient
import sol.vortexx.android.keys.impl.HttpSealedKeyClient
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class MultiDeviceModule {
    @Binds @Singleton
    abstract fun bindLinker(impl: HttpDeviceLinker): DeviceLinker

    @Binds @Singleton
    abstract fun bindSealedKeys(impl: HttpSealedKeyClient): SealedKeyClient
}
