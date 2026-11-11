import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'package:gsfibra/config.dart';

class ApiService {
  static String get baseUrl => AppConfig.apiBaseUrl;
  
  // Headers padrão
  static Map<String, String> _getHeaders() {
    return {
      'Content-Type': 'application/json',
    };
  }
  
  // GET com token
  static Future<dynamic> getWithToken(String endpoint) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');
    
    final headers = _getHeaders();
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    
    final response = await http.get(
      Uri.parse('${baseUrl}$endpoint'),
      headers: headers,
    );
    
    return _handleResponse(response);
  }
  
  // POST com token
  static Future<dynamic> postWithToken(String endpoint, Map<String, dynamic> data) async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');
    
    final headers = _getHeaders();
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    
    final response = await http.post(
      Uri.parse('${baseUrl}$endpoint'),
      headers: headers,
      body: jsonEncode(data),
    );
    
    return _handleResponse(response);
  }
  
  // Sem autenticação
  static Future<dynamic> get(String endpoint) async {
    final response = await http.get(
      Uri.parse('${baseUrl}$endpoint'),
      headers: _getHeaders(),
    );
    
    return _handleResponse(response);
  }
  
  static Future<dynamic> post(String endpoint, Map<String, dynamic> data) async {
    final response = await http.post(
      Uri.parse('${baseUrl}$endpoint'),
      headers: _getHeaders(),
      body: jsonEncode(data),
    );
    
    return _handleResponse(response);
  }
  
  // Tratamento de resposta
  static dynamic _handleResponse(http.Response response) {
    if (response.statusCode == 200 || response.statusCode == 201) {
      try {
        return jsonDecode(response.body);
      } catch (e) {
        return {'error': 'Erro ao processar resposta'};
      }
    } else {
      return {
        'error': 'Erro ${response.statusCode}: ${response.reasonPhrase}',
        'status': response.statusCode,
      };
    }
  }
}

class NetworkInfo {
  final String? ssid;
  final int? strength;
  final String? ipAddress;
  final String? frequency;
  final String? networkType;
  final bool? isConnected;
  
  NetworkInfo({
    this.ssid,
    this.strength,
    this.ipAddress,
    this.frequency,
    this.networkType,
    this.isConnected,
  });
  
  Map<String, dynamic> toJson() {
    return {
      'ssid': ssid,
      'strength': strength,
      'ipAddress': ipAddress,
      'frequency': frequency,
      'networkType': networkType,
      'isConnected': isConnected,
    };
  }
}
