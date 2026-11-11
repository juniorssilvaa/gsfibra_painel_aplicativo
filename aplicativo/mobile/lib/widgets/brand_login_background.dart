import 'dart:math';

import 'package:flutter/material.dart';

/// Fundo da tela de login (ondas, malha e brilhos) derivado de [base] e [glow].
class BrandLoginBackground extends StatelessWidget {
  const BrandLoginBackground({super.key, required this.base, required this.glow});

  final Color base;
  final Color glow;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _LoginBackgroundPainter(base: base, glow: glow),
      child: const SizedBox.expand(),
    );
  }
}

class _LoginBackgroundPainter extends CustomPainter {
  const _LoginBackgroundPainter({required this.base, required this.glow});

  final Color base;
  final Color glow;

  Color _shade(Color c, double amount) {
    final hsl = HSLColor.fromColor(c);
    return hsl.withLightness((hsl.lightness + amount).clamp(0.0, 1.0)).toColor();
  }

  @override
  void paint(Canvas canvas, Size size) {
    final width = size.width;
    final height = size.height;
    final line = Color.lerp(glow, Colors.white, 0.35)!;
    final dot = Color.lerp(glow, Colors.white, 0.45)!;

    final backgroundRect = Rect.fromLTWH(0, 0, width, height);

    final backgroundPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          base,
          _shade(base, 0.07),
          _shade(base, -0.03),
          _shade(base, 0.11),
        ],
        stops: const [0.0, 0.32, 0.68, 1.0],
      ).createShader(backgroundRect);

    canvas.drawRect(backgroundRect, backgroundPaint);

    final topGlowPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.75, -0.75),
        radius: 1.0,
        colors: [
          _shade(glow, 0.08).withValues(alpha: 0.38),
          glow.withValues(alpha: 0.15),
          Colors.transparent,
        ],
        stops: const [0.0, 0.40, 1.0],
      ).createShader(backgroundRect);

    canvas.drawRect(backgroundRect, topGlowPaint);

    final centerGlowPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(0.15, -0.20),
        radius: 0.95,
        colors: [
          glow.withValues(alpha: 0.22),
          Colors.transparent,
        ],
      ).createShader(backgroundRect);

    canvas.drawRect(backgroundRect, centerGlowPaint);

    final bottomGlowPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(0.85, 0.95),
        radius: 0.70,
        colors: [
          _shade(glow, 0.06).withValues(alpha: 0.36),
          glow.withValues(alpha: 0.10),
          Colors.transparent,
        ],
      ).createShader(backgroundRect);

    canvas.drawRect(backgroundRect, bottomGlowPaint);

    final wavePath = Path()
      ..moveTo(0, height * 0.23)
      ..cubicTo(
        width * 0.20,
        height * 0.34,
        width * 0.54,
        height * 0.36,
        width,
        height * 0.07,
      );

    final wavePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..color = line.withValues(alpha: 0.65);

    canvas.drawPath(wavePath, wavePaint);

    final glowWavePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10)
      ..color = _shade(glow, 0.06).withValues(alpha: 0.20);

    canvas.drawPath(wavePath, glowWavePaint);

    for (int i = 0; i < 24; i++) {
      final offset = i * 4.5;
      final path = Path()
        ..moveTo(0, height * 0.23 + offset)
        ..cubicTo(
          width * 0.24,
          height * 0.36 + offset * 0.35,
          width * 0.59,
          height * 0.37 + offset * 0.28,
          width,
          height * 0.07 + offset * 0.20,
        );

      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.45
        ..color = line.withValues(alpha: 0.18);

      canvas.drawPath(path, paint);
    }

    final random = Random(10);

    for (int i = 0; i < 450; i++) {
      final x = random.nextDouble() * width;
      final y = height * 0.19 + random.nextDouble() * height * 0.25;
      final normalizedX = x / width;
      final curveY = height * (0.22 + 0.18 * sin(normalizedX * pi));

      if (y > curveY) {
        final dotPaint = Paint()
          ..color = dot.withValues(
            alpha: 0.05 + random.nextDouble() * 0.17,
          );

        canvas.drawCircle(
          Offset(x, y),
          0.3 + random.nextDouble() * 1.2,
          dotPaint,
        );
      }
    }

    final bottomWave = Path()
      ..moveTo(width * 0.52, height)
      ..cubicTo(
        width * 0.68,
        height * 0.92,
        width * 0.83,
        height * 0.89,
        width,
        height * 0.85,
      );

    final bottomWavePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = line.withValues(alpha: 0.45);

    canvas.drawPath(bottomWave, bottomWavePaint);

    for (int i = 0; i < 20; i++) {
      final offset = i * 5.0;
      final path = Path()
        ..moveTo(width * 0.53, height + offset)
        ..cubicTo(
          width * 0.70,
          height * 0.94 + offset * 0.18,
          width * 0.87,
          height * 0.90 + offset * 0.18,
          width,
          height * 0.86 + offset * 0.15,
        );

      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.45
        ..color = line.withValues(alpha: 0.15);

      canvas.drawPath(path, paint);
    }

    for (int i = 0; i < 180; i++) {
      final x = width * 0.55 + random.nextDouble() * width * 0.45;
      final y = height * 0.83 + random.nextDouble() * height * 0.17;

      final paint = Paint()
        ..color = dot.withValues(
          alpha: 0.05 + random.nextDouble() * 0.18,
        );

      canvas.drawCircle(
        Offset(x, y),
        0.3 + random.nextDouble() * 1,
        paint,
      );
    }

    final vignettePaint = Paint()
      ..shader = RadialGradient(
        center: Alignment.center,
        radius: 1.0,
        colors: [
          Colors.transparent,
          Colors.black.withValues(alpha: 0.08),
          Colors.black.withValues(alpha: 0.20),
        ],
        stops: const [0.4, 0.78, 1],
      ).createShader(backgroundRect);

    canvas.drawRect(backgroundRect, vignettePaint);
  }

  @override
  bool shouldRepaint(covariant _LoginBackgroundPainter oldDelegate) =>
      oldDelegate.base != base || oldDelegate.glow != glow;
}
