# Kotlinx serialization — keep @Serializable companions and their data classes.
-keep,includedescriptorclasses class sol.vortexx.android.**$$serializer { *; }
-keepclassmembers class sol.vortexx.android.** {
    *** Companion;
}
-keepclasseswithmembers class sol.vortexx.android.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Ktor
-keepnames class io.ktor.** { *; }
