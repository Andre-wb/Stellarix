package sol.vortexx.android.contacts.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import sol.vortexx.android.contacts.api.Contacts
import sol.vortexx.android.contacts.impl.HttpContacts
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class ContactsModule {
    @Binds @Singleton
    abstract fun bindContacts(impl: HttpContacts): Contacts
}
