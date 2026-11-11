import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';
import 'brand_colors.dart';

/// Personalização feita no painel (cores, logos e WhatsApp de suporte).
/// Valores vazios no painel mantêm o padrão embutido no build.
class AppBranding {
  AppBranding._();

  static const _prefsKey = 'app_branding_v1';

  static String supportPhone = AppConfig.supportPhone;
  static Color? loginBg;
  static Color? loginButton;
  static Color? loginText;
  static Color? appBg;
  static Color? card;

  /// Posição do logo no topo da Início: 0 = esquerda, 50 = centro, 100 = direita.
  static int homeLogoPosition = 0;
  static File? logoFile;

  static Map<String, dynamic> _cached = {};

  /// Só dígitos, com DDI 55 quando o painel salva o número sem ele (ex.: "(94) 99284-0080").
  static String get whatsappDigits {
    final digits = supportPhone.replaceAll(RegExp(r'[^\d]'), '');
    if ((digits.length == 10 || digits.length == 11) && !digits.startsWith('55')) {
      return '55$digits';
    }
    return digits;
  }

  /// Sem cor de fundo no painel: usa a do build, ou um tom escuro da cor principal
  /// personalizada (mesmo cálculo da prévia do painel).
  static Color get loginBackground {
    if (loginBg != null) return loginBg!;
    if (BrandColors.primary == BrandColors.defaultPrimary) return BrandColors.loginBgDefault;
    final hsl = HSLColor.fromColor(BrandColors.primary);
    return hsl.withLightness((hsl.lightness - 0.22).clamp(0.0, 1.0)).toColor();
  }
  static Color get loginButtonColor => loginButton ?? BrandColors.primary;

  /// Cores de fábrica deste build, enviadas ao backend para a prévia do painel.
  static String get buildDefaultsJson => jsonEncode({
        'primary_color': BrandColors.toHex(BrandColors.defaultPrimary),
        'secondary_color': BrandColors.toHex(BrandColors.defaultAccent),
        'login_bg_color': BrandColors.toHex(BrandColors.loginBgDefault),
        'login_button_color': BrandColors.toHex(BrandColors.defaultPrimary),
        'login_text_color': '#FFFFFF',
        'app_bg_color': BrandColors.toHex(BrandColors.loginBgDefault),
        'card_color': '#FFFFFF',
      });
  static Color get loginTextColor => loginText ?? Colors.white;

  /// Fundo das telas do app; vazio no painel = mesma cor do fundo do login.
  static Color get appBackground => appBg ?? loginBackground;
  static Color get cardColor => card ?? Colors.white;

  static const Color darkCard = Color(0xFF111111);

  /// Barra superior das telas internas: mesma laranja dos botões (não o verde de fundo).
  static Color get headerBackground => loginButtonColor;
  static Color get onHeader => onColor(headerBackground);

  /// Modo claro usa as cores do painel; modo escuro mantém o fundo escuro.
  static Color screenBackground(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? BrandColors.darkBg : appBackground;
  static Color cardBackground(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? darkCard : cardColor;

  /// Texto legível sobre [background] (preto em cores claras, branco em escuras).
  static Color onColor(Color background) =>
      ThemeData.estimateBrightnessForColor(background) == Brightness.dark ? Colors.white : const Color(0xFF1F2124);

  /// Logos embutidos no build; usados sem personalização ou quando a do painel falha.
  /// Home e login: logo tipográfica. Splash: mascote.
  static const String defaultLogoAsset = 'assets/logo_gsfibra.png';
  static const String defaultLoginLogoAsset = 'assets/gsfibra_login.png';
  static const String defaultSplashLogoAsset = 'assets/mascote_splash.png';

  static ImageProvider logoProvider() =>
      logoFile != null ? FileImage(logoFile!) as ImageProvider : const AssetImage(defaultLogoAsset);

  /// Mascote da Splash (build). Não troca pela logo do painel.
  static ImageProvider splashLogoProvider() =>
      ResizeImage(
        const AssetImage(defaultSplashLogoAsset),
        width: 720,
        policy: ResizeImagePolicy.fit,
        allowUpscaling: false,
      );

  /// O login usa o mesmo logo do painel; sem ele, a versão de login embutida no build.
  static ImageProvider loginLogoProvider() =>
      logoFile != null ? FileImage(logoFile!) as ImageProvider : const AssetImage(defaultLoginLogoAsset);

  /// Aplica a última personalização salva; chamado antes do primeiro frame.
  static Future<void> loadCached() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_prefsKey);
      if (raw == null) return;
      _cached = Map<String, dynamic>.from(jsonDecode(raw) as Map);
      _applyValues(_cached);
      logoFile = _existing(_cached['logo_path']);
    } catch (e) {
      debugPrint('BRANDING: cache inválido: $e');
    }
  }

  static Future<bool> _pending = Future.value(false);

  /// Aplica a resposta do /v1/home. Retorna true se algo visível mudou.
  /// Chamadas simultâneas rodam em fila: em paralelo, uma apagaria o logo recém-baixado pela outra.
  static Future<bool> applyFromApi(Map<String, dynamic> data) {
    final run = _pending.catchError((_) => false).then((_) => _applyFromApi(data));
    _pending = run;
    return run;
  }

  static Future<bool> _applyFromApi(Map<String, dynamic> data) async {
    final theme = data['theme'] is Map ? Map<String, dynamic>.from(data['theme'] as Map) : <String, dynamic>{};
    final next = <String, dynamic>{
      'primary_color': theme['primary_color'] ?? '',
      'secondary_color': theme['secondary_color'] ?? '',
      'login_bg_color': theme['login_bg_color'] ?? '',
      'login_button_color': theme['login_button_color'] ?? '',
      'login_text_color': theme['login_text_color'] ?? '',
      'app_bg_color': theme['app_bg_color'] ?? '',
      'card_color': theme['card_color'] ?? '',
      'home_logo_position': theme['home_logo_position'] ?? 0,
      'support_phone': (data['support_phone'] ?? data['provider_phone'] ?? '').toString().trim(),
      'logo_url': theme['logo_url'] ?? '',
      'logo_path': _cached['logo_path'],
    };

    var changed = false;
    for (final key in const [
      'primary_color', 'secondary_color', 'login_bg_color', 'login_button_color',
      'login_text_color', 'app_bg_color', 'card_color', 'home_logo_position', 'support_phone',
    ]) {
      if (next[key] != _cached[key]) changed = true;
    }
    _applyValues(next);
    if (logoFile != null && !logoFile!.existsSync()) logoFile = null;
    if (_cached['login_logo_path'] != null) {
      // Logo de login separado foi descontinuado: apaga o arquivo baixado por versões anteriores.
      await _deleteVersions(await getApplicationSupportDirectory(), 'brand_login_logo');
    }

    // Sem arquivo local (apagado pelo sistema), baixa de novo mesmo com a URL igual.
    final logo = await _syncImage(next['logo_url'] as String, logoFile == null ? '' : _cached['logo_url'], 'brand_logo');
    if (logo.changed) {
      changed = true;
      logoFile = logo.file;
      next['logo_path'] = logo.file?.path;
    }
    if (!logo.ok) next['logo_url'] = _cached['logo_url'];

    _cached = next;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKey, jsonEncode(next));
    } catch (_) {}
    return changed;
  }

  static void _applyValues(Map<String, dynamic> v) {
    BrandColors.primary = BrandColors.parseHex(v['primary_color']?.toString(), fallback: BrandColors.defaultPrimary);
    BrandColors.accent = BrandColors.parseHex(v['secondary_color']?.toString(), fallback: BrandColors.defaultAccent);
    loginBg = _optionalColor(v['login_bg_color']);
    loginButton = _optionalColor(v['login_button_color']);
    loginText = _optionalColor(v['login_text_color']);
    appBg = _optionalColor(v['app_bg_color']);
    card = _optionalColor(v['card_color']);
    final position = v['home_logo_position'];
    homeLogoPosition = position is num ? position.round().clamp(0, 100) : 0;
    final phone = (v['support_phone'] ?? '').toString().trim();
    supportPhone = phone.isNotEmpty ? phone : AppConfig.supportPhone;
  }

  static Color? _optionalColor(dynamic hex) {
    final value = (hex ?? '').toString().trim();
    if (!RegExp(r'^#[0-9A-Fa-f]{6}$').hasMatch(value)) return null;
    return BrandColors.parseHex(value);
  }

  static File? _existing(dynamic path) {
    if (path is! String || path.isEmpty) return null;
    final f = File(path);
    return f.existsSync() ? f : null;
  }

  /// Baixa o logo quando a URL muda; URL vazia remove o arquivo salvo.
  static Future<({bool ok, bool changed, File? file})> _syncImage(String url, dynamic previousUrl, String name) async {
    if (url == (previousUrl ?? '')) return (ok: true, changed: false, file: null);
    final dir = await getApplicationSupportDirectory();
    if (url.isEmpty) {
      await _deleteVersions(dir, name);
      return (ok: true, changed: true, file: null);
    }
    try {
      final res = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 10));
      if (res.statusCode != 200 || res.bodyBytes.isEmpty) {
        return (ok: false, changed: false, file: null);
      }
      // Nome novo a cada versão: FileImage faz cache pelo caminho do arquivo.
      final file = File('${dir.path}/${name}_${DateTime.now().millisecondsSinceEpoch}.img');
      await file.writeAsBytes(res.bodyBytes, flush: true);
      await _deleteVersions(dir, name, keep: file.path);
      return (ok: true, changed: true, file: file);
    } catch (e) {
      debugPrint('BRANDING: falha ao baixar $name: $e');
      return (ok: false, changed: false, file: null);
    }
  }

  static Future<void> _deleteVersions(Directory dir, String name, {String? keep}) async {
    for (final old in dir.listSync().whereType<File>()) {
      if (old.uri.pathSegments.last.startsWith('${name}_') && old.path != keep) {
        try {
          await old.delete();
        } catch (_) {}
      }
    }
  }
}
