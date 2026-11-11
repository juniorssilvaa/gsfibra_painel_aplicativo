import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:provider/provider.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'config.dart';
import 'theme/app_branding.dart';
import 'theme/brand_colors.dart';

import 'provider.dart';
import 'services/push_service.dart';
import 'services/update_service.dart';
import 'screens/home/home_screen.dart';
import 'screens/login/login_screen.dart';
import 'screens/fatura/fatura_screen.dart';
import 'screens/ai/ai_chat_screen.dart';
import 'screens/planos/planos_screen.dart';
import 'screens/perfil/perfil_screen.dart';
import 'screens/contratos/contratos_screen.dart';
import 'screens/consumption/consumption_screen.dart';
import 'screens/support/support_screen.dart';
import 'screens/modem/modem_info_screen.dart';
import 'screens/speed_test/speed_test_screen.dart';
import 'screens/connected_devices/connected_devices_screen.dart';
import 'screens/menu/menu_screen.dart';
import 'screens/menu/terms_screen.dart';
import 'screens/menu/privacy_screen.dart';
import 'screens/menu/select_contract_screen.dart';
import 'screens/notification/notification_screen.dart';
import 'screens/notification/notification_detail_screen.dart';
import 'screens/nota_fiscal/nota_fiscal_screen.dart';
import 'screens/splash_screen.dart';
import 'screens/blocked_screen.dart';

final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Só o essencial antes do primeiro frame: enquanto isso o Android mostra a tela preta nativa.
  await Future.wait([
    initializeDateFormatting('pt_BR', null),
    _loadApiOverride(),
    AppBranding.loadCached(),
  ]);

  AppBranding.splashLogoProvider().resolve(ImageConfiguration.empty);

  // Firebase, syncTime e checagem de atualização rodam depois que a Splash aparece.
  runApp(const MyApp());
  WidgetsBinding.instance.addPostFrameCallback((_) => UpdateService.checkForUpdate());
  unawaited(_bootstrapAfterFirstFrame());
  onPushNotificationTap = (data) {
    final type = '${data['type'] ?? ''}';
    final screen = '${data['screen'] ?? ''}';
    if (type == 'support_chat' || screen == 'ai_chat') {
      navigatorKey.currentState?.pushNamed('/ai_chat');
    }
  };
}

Future<void> _loadApiOverride() async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool('api_base_url_use_override') ?? false;
    final override = prefs.getString('api_base_url_override') ?? '';
    if (enabled && override.isNotEmpty) {
      AppConfig.setRuntimeApiBaseUrl(override);
    }
  } catch (e) {
    debugPrint("Erro ao carregar SharedPreferences: $e");
  }
}

Future<void> _bootstrapAfterFirstFrame() async {
  try {
    debugPrint("Iniciando Firebase...");
    await Firebase.initializeApp().timeout(const Duration(seconds: 8));
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
    debugPrint("Firebase inicializado com sucesso.");
  } catch (e) {
    debugPrint("⚠️ ALERTA: Erro ao inicializar Firebase: $e");
    debugPrint("O app continuará sem recursos de Push.");
  }

  try {
    await AppConfig.syncTime();
  } catch (_) {}
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AppProvider(),
      child: Consumer<AppProvider>(
        builder: (context, provider, child) {
          return MaterialApp(
            title: 'Gs Fibra',
            navigatorKey: navigatorKey,
            debugShowCheckedModeBanner: false,
            builder: (context, child) {
              if (provider.isBlocked) {
                return const BlockedScreen();
              }
              return SessionTimeoutWrapper(
                isLoggedIn: provider.isLoggedIn,
                logoutAction: () => provider.logout(),
                child: child!,
              );
            },
            themeMode: provider.themeMode,
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [
              Locale('pt', 'BR'),
            ],
            theme: ThemeData(
              brightness: Brightness.light,
              primaryColor: provider.brandPrimary,
              scaffoldBackgroundColor: BrandColors.lightBg,
              useMaterial3: true,
              colorScheme: ColorScheme.light(
                primary: provider.brandPrimary,
                secondary: BrandColors.accent,
                surface: Colors.white,
                error: const Color(0xFFB00020),
                onPrimary: Colors.white,
                onSecondary: Colors.white,
                onSurface: BrandColors.ink,
                onError: Colors.white,
              ),
              appBarTheme: AppBarTheme(
                backgroundColor: provider.brandPrimary,
                foregroundColor: Colors.white,
              ),
            ),
            darkTheme: ThemeData(
              brightness: Brightness.dark,
              primaryColor: provider.brandPrimary,
              scaffoldBackgroundColor: BrandColors.darkBg,
              useMaterial3: true,
              colorScheme: ColorScheme.dark(
                primary: provider.brandPrimary,
                secondary: BrandColors.accent,
                surface: BrandColors.darkSurface,
                error: const Color(0xFFCF6679),
                onPrimary: Colors.white,
                onSecondary: Colors.white,
                onSurface: Colors.white,
                onError: Colors.black,
              ),
              appBarTheme: AppBarTheme(
                backgroundColor: provider.brandPrimary,
                foregroundColor: Colors.white,
              ),
            ),
            home: const SplashScreen(),
            routes: {
              '/login': (context) => const LoginScreen(),
              '/home': (context) => HomeScreen(),
              '/fatura': (context) => const FaturaScreen(),
              '/ai_chat': (context) => const AIChatScreen(),
              '/planos': (context) => const PlanosScreen(),
              '/perfil': (context) => const PerfilScreen(),
              '/contratos': (context) => const ContratosScreen(),
              '/consumo': (context) => ConsumptionScreen(),
              '/support': (context) => const SupportScreen(),
              '/wifi': (context) => const ModemInfoScreen(),
              '/speedtest': (context) => const SpeedTestScreen(),
              '/connected_devices': (context) => const ConnectedDevicesScreen(),
              '/menu': (context) => const MenuScreen(),
              '/select_contract': (context) => const SelectContractScreen(),
              '/terms': (context) => const TermsScreen(),
              '/privacy': (context) => const PrivacyScreen(),
              '/notifications': (context) => const NotificationScreen(),
              '/notification_detail': (context) => const NotificationDetailScreen(),
              '/nota_fiscal': (context) => const NotaFiscalScreen(),
              '/blocked': (context) => const BlockedScreen(),
            },
          );
        },
      ),
    );
  }
}

class SessionTimeoutWrapper extends StatefulWidget {
  final Widget child;
  final bool isLoggedIn;
  final VoidCallback logoutAction;

  const SessionTimeoutWrapper({
    super.key,
    required this.child,
    required this.isLoggedIn,
    required this.logoutAction,
  });

  @override
  State<SessionTimeoutWrapper> createState() => _SessionTimeoutWrapperState();
}

class _SessionTimeoutWrapperState extends State<SessionTimeoutWrapper> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (widget.isLoggedIn) {
      _startTimer();
    }
  }

  @override
  void didUpdateWidget(SessionTimeoutWrapper oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isLoggedIn != oldWidget.isLoggedIn) {
      if (widget.isLoggedIn) {
        _startTimer();
      } else {
        _stopTimer();
      }
    }
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer(const Duration(minutes: 3), _handleTimeout);
  }

  void _stopTimer() {
    _timer?.cancel();
  }

  void _handleTimeout() {
    debugPrint("SESSION: Tempo de inatividade atingido (3 min). Deslogando...");
    widget.logoutAction();
    navigatorKey.currentState?.pushNamedAndRemoveUntil('/login', (route) => false);
  }

  void _onInteraction() {
    if (widget.isLoggedIn) {
      _startTimer();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerDown: (_) => _onInteraction(),
      onPointerMove: (_) => _onInteraction(),
      child: widget.child,
    );
  }
}
