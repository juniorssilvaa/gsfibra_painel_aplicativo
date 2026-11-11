import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../provider.dart';
import '../../theme/app_branding.dart';
import '../../theme/brand_colors.dart';
import 'home/home_screen.dart';
import 'login/login_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  Future<void> _requestInitialPermissions() async {
    try {
      await Permission.notification.request().timeout(const Duration(seconds: 4));
    } catch (e) {
      debugPrint('SPLASH: erro ao solicitar permissão de notificação: $e');
    }

    try {
      await Permission.locationWhenInUse.request().timeout(const Duration(seconds: 4));
    } catch (e) {
      debugPrint('SPLASH: erro ao solicitar localização: $e');
    }

    if (Platform.isIOS) {
      try {
        await FirebaseMessaging.instance
            .requestPermission(
              alert: true,
              badge: true,
              sound: true,
              provisional: false,
            )
            .timeout(const Duration(seconds: 4));
      } catch (e) {
        debugPrint('SPLASH: erro ao solicitar permissão de notificação iOS (FCM): $e');
      }
    }
  }

  @override
  void initState() {
    super.initState();
    // Precarrega a logo para a Splash Flutter aparecer sem “buraco” preto.
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      try {
        await precacheImage(AppBranding.splashLogoProvider(), context);
      } catch (_) {}
      if (!mounted) return;
      _navigateToNextScreen();
    });
  }

  Future<void> _initServices() async {
    try {
      await Firebase.initializeApp().timeout(const Duration(seconds: 5));
      debugPrint('Firebase inicializado com sucesso');
    } catch (e) {
      debugPrint('Erro na inicialização do Firebase (ignorado no emulador): $e');
    }
    
    await Future.delayed(const Duration(milliseconds: 100));
  }

  Future<void> _navigateToNextScreen() async {
    debugPrint('SPLASH: start');
    AppProvider? appState;
    try {
      appState = context.read<AppProvider>();
    } catch (e) {
      debugPrint('SPLASH: provider not found: $e');
    }

    try {
      final initFuture = _initServices();
      final providerInit = (appState?.initialize() ?? Future.value()).timeout(const Duration(seconds: 4));
      final minDelayFuture = Future.delayed(const Duration(milliseconds: 2500));
      await Future.wait([initFuture, providerInit, minDelayFuture]).timeout(const Duration(seconds: 6));
    } catch (e) {
      debugPrint('Erro/timeout na Splash: $e');
    }

    try {
      await _requestInitialPermissions().timeout(const Duration(seconds: 10));
    } catch (e) {
      debugPrint('SPLASH: permissions error: $e');
    }

    // Push não pode segurar a splash: no iOS sem aps-environment o FCM trava.
    if (appState != null) {
      unawaited(() async {
        try {
          await appState!.initPushService().timeout(const Duration(seconds: 15));
        } catch (e) {
          debugPrint('SPLASH: push init error: $e');
        }
      }());
    }

    if (!mounted) return;

    bool loggedIn = appState?.isLoggedIn ?? false;
    if (!loggedIn) {
      try {
        final prefs = await SharedPreferences.getInstance().timeout(const Duration(seconds: 2));
        loggedIn = prefs.getBool('isLoggedIn') ?? false;
      } catch (_) {}
    }

    if (!mounted) return;
    try {
      // Sempre navegar para /login ao iniciar o app do zero
      Navigator.of(context).pushReplacementNamed('/login');
    } catch (e) {
      debugPrint('SPLASH: named navigation failed: $e');
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => loggedIn ? HomeScreen() : const LoginScreen(),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final scaffoldBg = BrandColors.loginBgDefault;

    return Scaffold(
      backgroundColor: scaffoldBg,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Image(
              image: AppBranding.splashLogoProvider(),
              height: 280,
              fit: BoxFit.contain,
              errorBuilder: (context, error, stackTrace) => Image.asset(
                AppBranding.defaultSplashLogoAsset,
                height: 280,
                fit: BoxFit.contain,
                errorBuilder: (context, error, stackTrace) => Image.asset(
                  AppBranding.defaultLogoAsset,
                  width: 210,
                  fit: BoxFit.contain,
                ),
              ),
            ),
            const SizedBox(height: 40),
            SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(BrandColors.defaultPrimary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
