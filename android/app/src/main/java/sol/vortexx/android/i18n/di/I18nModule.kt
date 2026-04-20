package sol.vortexx.android.i18n.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.i18n.api.LocaleSource
import sol.vortexx.android.i18n.impl.AssetLocaleSource
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class I18nModule {
    @Binds @Singleton
    abstract fun bindLocaleSource(impl: AssetLocaleSource): LocaleSource
}
