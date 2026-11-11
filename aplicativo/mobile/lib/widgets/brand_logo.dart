import 'package:flutter/material.dart';

import '../theme/app_branding.dart';

/// Logo gsfibra que adapta o texto ao tema (branco no escuro, preto no claro).
class BrandLogo extends StatelessWidget {
  const BrandLogo({
    super.key,
    this.height,
    this.width,
    this.fit = BoxFit.contain,
    this.forceDarkAsset = false,
    this.darkBackground,
  });

  /// Fundo atrás do logo; quando nulo segue o tema claro/escuro.
  final bool? darkBackground;

  final double? height;
  final double? width;
  final BoxFit fit;

  /// Sempre usa a logo para fundo escuro (splash, login, blocked).
  final bool forceDarkAsset;

  @override
  Widget build(BuildContext context) {
    final isDark = darkBackground ?? Theme.of(context).brightness == Brightness.dark;
    const asset = AppBranding.defaultLogoAsset;
    final fallback = Text(
      'gsfibra',
      style: TextStyle(
        color: isDark || forceDarkAsset ? Colors.white : Colors.black,
        fontSize: (height != null && height! < 40) ? 14 : 16,
        fontWeight: FontWeight.w900,
        letterSpacing: 0.4,
      ),
    );
    final assetLogo = Image.asset(
      asset,
      height: height,
      width: width,
      fit: fit,
      errorBuilder: (context, error, stackTrace) => fallback,
    );
    if (AppBranding.logoFile == null) return assetLogo;
    return Image(
      image: AppBranding.logoProvider(),
      height: height,
      width: width,
      fit: fit,
      errorBuilder: (context, error, stackTrace) => assetLogo,
    );
  }
}
