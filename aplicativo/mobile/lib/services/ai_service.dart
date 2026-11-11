import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:gsfibra/config.dart';

class AIService {
  final String providerToken;

  AIService({required this.providerToken});

  Future<Map<String, dynamic>> sendMessage({
    required String message,
    required String cpf,
    String? sessionId,
    String? name,
    Map<String, dynamic>? telemetry,
  }) async {
    final url = AppConfig.apiUrl('ai/chat/');
    final response = await http.post(
      url,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'provider_token': providerToken,
        'cpf': cpf,
        'message': message,
        'session_id': sessionId,
        'name': name,
        'telemetry': telemetry,
      }),
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      return {'error': 'Erro na comunicação com a IA', 'status': response.statusCode};
    }
  }
}
