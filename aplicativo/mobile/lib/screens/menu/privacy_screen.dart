import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../provider.dart';
import 'terms_screen.dart';

class PrivacyScreen extends StatelessWidget {
  const PrivacyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final text = context.watch<AppProvider>().privacyText;
    return LegalTextScreen(
      title: 'Política de Privacidade',
      text: text,
      emptyMessage: 'A política de privacidade ainda não foi cadastrada pelo provedor.',
    );
  }
}
