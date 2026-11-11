import 'package:in_app_update/in_app_update.dart';
import 'package:flutter/foundation.dart';
import 'dart:io';

class UpdateService {
  static Future<void> checkForUpdate() async {
    // Updates are only supported on Android via Google Play
    if (!kIsWeb && Platform.isAndroid) {
      try {
        debugPrint('UpdateService: Checking for updates...');
        final info = await InAppUpdate.checkForUpdate();
        
        if (info.updateAvailability == UpdateAvailability.updateAvailable) {
          debugPrint('UpdateService: Update available! Starting flexible update...');
          await InAppUpdate.performImmediateUpdate();
        } else {
          debugPrint('UpdateService: No updates available.');
        }
      } catch (e) {
        debugPrint('UpdateService: Error checking for updates: $e');
      }
    } else {
      debugPrint('UpdateService: Skip check (platform not supported or web)');
    }
  }
}
