// Root build — all plugins declared here with `apply false` so subprojects
// opt in via the version catalog alias without re-specifying versions.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android)       apply false
    alias(libs.plugins.kotlin.compose)       apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp)                  apply false
    alias(libs.plugins.hilt)                 apply false
}
