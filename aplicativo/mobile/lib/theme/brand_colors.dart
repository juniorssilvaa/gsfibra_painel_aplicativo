import 'package:flutter/material.dart';

/// Paleta do gsfibra: fundo verde da marca com detalhes em laranja.
/// [primary] e [accent] podem ser trocadas pelo painel (AppBranding).
class BrandColors {
  /// Laranja da logo (detalhes / botões).
  static const Color defaultPrimary = Color(0xFFFF7D29);
  /// Laranja mais fechado para realces.
  static const Color defaultAccent = Color(0xFFE86A1A);
  /// Verde da marca (fundo splash/login/app).
  static const Color loginBgDefault = Color(0xFF307A17);
  static Color primary = defaultPrimary;
  static Color accent = defaultAccent;
  static const Color ink = Color(0xFF1F2124);
  static const Color muted = Color(0xFF69727D);
  static const Color lightBg = Color(0xFFF8F8F8);
  static const Color darkBg = Color(0xFF0A0A0A);
  static const Color darkSurface = Color(0xFF141414);
  static const Color whatsapp = Color(0xFF25D366);

  static Color parseHex(String? hex, {Color? fallback}) {
    fallback ??= primary;
    if (hex == null) return fallback;
    var value = hex.trim();
    if (value.isEmpty) return fallback;
    // Azul legado do template antigo → ignora e usa a marca atual.
    if (value.toUpperCase() == '#0D70B3') return fallback;
    // Verde-neon antigo do template → ignora.
    if (value.toUpperCase() == '#34E300') return fallback;
    if (value.startsWith('#')) value = value.substring(1);
    if (value.length == 6) value = 'FF$value';
    if (value.length != 8) return fallback;
    final parsed = int.tryParse(value, radix: 16);
    return parsed == null ? fallback : Color(parsed);
  }

  static String toHex(Color color) {
    final argb = color.toARGB32().toRadixString(16).padLeft(8, '0');
    return '#${argb.substring(2)}';
  }
}
