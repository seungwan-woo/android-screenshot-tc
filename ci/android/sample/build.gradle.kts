buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        // AGP's built-in Kotlin uses this version for the matching Compose compiler.
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.4.21")
    }
}

plugins {
    id("com.android.application") version "9.5.2" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21" apply false
}
