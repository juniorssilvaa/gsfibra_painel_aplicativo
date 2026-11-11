import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../provider.dart';

class TermsScreen extends StatelessWidget {
  const TermsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final text = context.watch<AppProvider>().termsText;
    return LegalTextScreen(
      title: 'Termos de Uso',
      text: text,
      emptyMessage: 'Os termos ainda não foram cadastrados pelo provedor.',
    );
  }
}

class LegalTextScreen extends StatelessWidget {
  final String title;
  final String text;
  final String emptyMessage;

  const LegalTextScreen({
    super.key,
    required this.title,
    required this.text,
    required this.emptyMessage,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final body = text.trim();

    return Scaffold(
      appBar: AppBar(
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: body.isEmpty
            ? Text(
                emptyMessage,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.5,
                  color: isDark ? Colors.grey[300] : Colors.grey[800],
                ),
              )
            : SelectableText(
                body,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.55,
                  color: isDark ? Colors.grey[300] : Colors.grey[800],
                ),
              ),
      ),
    );
  }
}
