import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../config.dart';
import '../provider.dart';
import '../main.dart';
import '../theme/brand_colors.dart';
import '../theme/app_branding.dart';
import '../widgets/brand_logo.dart';

class BlockedScreen extends StatelessWidget {
  const BlockedScreen({super.key});

  static Color get _red => BrandColors.primary;
  static const Color _bg = BrandColors.darkBg;

  Future<void> _openWhatsApp() async {
    final digits = AppBranding.whatsappDigits;
    final message = Uri.encodeComponent(
      'Olá, estou sem acesso ao app ${AppConfig.providerName}. Preciso de ajuda.',
    );
    final waDeepLink = Uri.parse('whatsapp://send?phone=$digits&text=$message');
    final waWeb = Uri.parse('https://wa.me/$digits?text=$message');

    if (await canLaunchUrl(waDeepLink)) {
      await launchUrl(waDeepLink, mode: LaunchMode.externalApplication);
    } else if (await canLaunchUrl(waWeb)) {
      await launchUrl(waWeb, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _backToLogin(BuildContext context) async {
    final provider = context.read<AppProvider>();
    await provider.logout();
    if (!context.mounted) return;
    if (!provider.isBlocked) {
      navigatorKey.currentState?.pushNamedAndRemoveUntil('/login', (route) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: _bg,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      child: Scaffold(
        backgroundColor: _bg,
        body: SizedBox.expand(
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 28),
              child: Column(
                children: [
                  const BrandLogo(height: 52, darkBackground: true),
                  const Spacer(),
                  Container(
                    width: 96,
                    height: 96,
                    decoration: BoxDecoration(
                      color: _red.withValues(alpha: 0.12),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(Icons.engineering_rounded, size: 48, color: _red),
                  ),
                  const SizedBox(height: 20),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0x33FF9800),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: const Text(
                      'MANUTENÇÃO',
                      style: TextStyle(
                        color: Color(0xFFFFB74D),
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.1,
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'App em Manutenção',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                      height: 1.2,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    'Estamos realizando melhorias para melhor atendê-lo.\nEm breve o acesso será restabelecido.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.65),
                      fontSize: 15,
                      height: 1.45,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    'Se precisar de algo urgente, clique no botão abaixo falar com o provedor',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.9),
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                      height: 1.4,
                    ),
                  ),
                  const Spacer(),
                  SizedBox(
                    width: double.infinity,
                    height: 54,
                    child: ElevatedButton.icon(
                      onPressed: _openWhatsApp,
                      icon: const Icon(Icons.chat_rounded, size: 20),
                      label: const Text(
                        'Falar com o Provedor',
                        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _red,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    height: 54,
                    child: ElevatedButton.icon(
                      onPressed: () => _backToLogin(context),
                      icon: const Icon(Icons.logout_rounded, size: 20),
                      label: const Text(
                        'Voltar para o Login',
                        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _red,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
