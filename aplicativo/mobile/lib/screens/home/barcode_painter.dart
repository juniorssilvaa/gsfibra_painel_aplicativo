import 'package:flutter/material.dart';

class BarcodePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.fill;

    final double w = size.width;
    final double h = size.height;

    // Definição das barras (posição relativa X, largura relativa)
    final bars = [
      [0.00, 0.08], // Barra fina
      [0.15, 0.04], // Barra muito fina
      [0.25, 0.12], // Barra média
      [0.45, 0.04], // Barra muito fina
      [0.55, 0.08], // Barra fina
      [0.70, 0.04], // Barra muito fina
      [0.80, 0.12], // Barra média
      [0.96, 0.04], // Barra final
    ];

    for (var bar in bars) {
      canvas.drawRect(
        Rect.fromLTWH(bar[0] * w, 0, bar[1] * w, h),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
