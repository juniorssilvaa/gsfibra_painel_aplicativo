# Add project specific ProGuard rules here.
# By default, the flags in this file are appended to flags specified
# in /usr/local/Cellar/android-sdk/24.3.3/tools/proguard/proguard-android.txt
# You can edit the include path and order by changing the proguardFiles
# directive in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# Flutter
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.** { *; }
-keep class io.flutter.util.** { *; }
-keep class io.flutter.view.** { *; }
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }

# Firebase
-keep class com.google.firebase.** { *; }
-keep enum com.google.firebase.** { *; }
-keepnames class com.google.firebase.** { *; }
-keepclassmembers class com.google.firebase.** { *; }

# Google Services
-keep class com.google.android.gms.** { *; }
-keep class com.google.android.apps.common.google.services.** { *; }

# App Specific (Models etc if needed)
-keep class com.gsfibra.app.models.** { *; }
-keep class com.jocanet.app.niochat.models.** { *; }

# react-native-reanimated (Mantido por segurança caso existam libs legadas)
-keep class com.swmansion.reanimated.** { *; }
-keep class com.facebook.react.turbomodule.** { *; }

# Add any project specific keep options here:
