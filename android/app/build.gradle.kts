plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "sol.vortexx.android"
    compileSdk = 34

    defaultConfig {
        applicationId = "sol.vortexx.android"
        minSdk = 26            // Android 8.0 — covers >98% of devices, unblocks modern crypto
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables { useSupportLibrary = true }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
            versionNameSuffix   = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }

    packaging {
        resources.excludes += listOf(
            "META-INF/AL2.0",
            "META-INF/LGPL2.1",
            "META-INF/*.kotlin_module"
        )
    }
}

dependencies {
    // Compose BOM — single source of truth for every compose-ui artifact.
    val composeBom = platform(libs.androidx.compose.bom)
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)

    // Hilt (DI) — processor wired via KSP, not kapt, for Kotlin 2.x speed.
    implementation(libs.hilt.android)
    implementation(libs.androidx.hilt.navigation)
    ksp(libs.hilt.compiler)

    // Room (local DB) — used from Wave 7 onward.
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    // Ktor — used from Wave 4 onward (HTTP + JSON + WS).
    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.ktor.client.logging)
    implementation(libs.ktor.client.websockets)

    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    // Crypto — BouncyCastle provides X25519 / Ed25519 / Argon2id consistently
    // across minSdk 26…34 (java.security doesn't guarantee these until API 31).
    implementation(libs.bouncycastle)
    // AndroidKeyStore-backed EncryptedSharedPreferences — used for JWTs + seed
    implementation(libs.androidx.security.crypto)

    // WebRTC (Stream's maintained fork of the now-archived google-webrtc).
    implementation(libs.stream.webrtc)
    // Media3 ExoPlayer for the in-app video viewer.
    implementation(libs.androidx.media3.exoplayer)
    implementation(libs.androidx.media3.ui)

    // Firebase Cloud Messaging — push notifications. Requires google-services.json
    // from the project in Firebase console; without it the module compiles but
    // PushSubscriber.enable() will return false at runtime.
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.messaging)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso)
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)
}
