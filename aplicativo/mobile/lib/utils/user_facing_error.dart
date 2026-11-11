/// Mensagens para o cliente: nunca exibe token, URL, stack ou código HTTP.
class UserFacingError {
  static const connection =
      'Não foi possível conectar agora. Verifique sua internet e tente novamente.';
  static const generic =
      'Não foi possível concluir esta ação. Tente novamente em instantes.';
  static const atendimento =
      'O atendimento via app está desativado para você.';
  static const planos =
      'Não foi possível carregar os planos agora. Tente novamente em instantes.';

  static String from(Object? error, {String fallback = generic}) {
    final cleaned = (error?.toString() ?? '')
        .replaceFirst(RegExp(r'^Exception:\s*'), '')
        .trim();
    if (cleaned.isEmpty || looksTechnical(cleaned)) return fallback;
    return cleaned;
  }

  static bool looksTechnical(String text) {
    final lower = text.toLowerCase();
    return lower.contains('provider_token') ||
        lower.contains('sk_live_') ||
        lower.contains('socketexception') ||
        lower.contains('clientexception') ||
        lower.contains('httpexception') ||
        lower.contains('handshake') ||
        lower.contains('127.0.0.1') ||
        lower.contains('localhost') ||
        lower.contains('errno') ||
        lower.contains('uri=') ||
        lower.contains('failed to load') ||
        RegExp(r'https?://').hasMatch(text) ||
        RegExp(r'\b[45]\d\d\b').hasMatch(text);
  }
}
