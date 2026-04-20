package sol.vortexx.android.rooms.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.rooms.api.RoomsRepository
import sol.vortexx.android.rooms.impl.HttpRoomsRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class RoomsModule {
    @Binds @Singleton
    abstract fun bindRoomsRepository(impl: HttpRoomsRepository): RoomsRepository
}
