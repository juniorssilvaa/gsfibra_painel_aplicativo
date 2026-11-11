import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:gsfibra/config.dart';

class SGPService {
  final String? _providerTokenOverride;

  SGPService({String? providerToken}) : _providerTokenOverride = providerToken;

  String get providerToken {
    final override = (_providerTokenOverride ?? '').trim();
    if (override.isNotEmpty &&
        !override.startsWith('http://') &&
        !override.startsWith('https://') &&
        !override.contains('/v1')) {
      return override;
    }
    return AppConfig.apiToken;
  }

  Future<dynamic> _proxyGet(String endpoint, Map<String, String> params) async {
    final token = providerToken;
    final url = AppConfig.sgpProxyUrl(endpoint, query: params);

    try {
      debugPrint('SGPService: GET ${AppConfig.redactUri(url)}');
      final response = await http.get(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
          'X-Provider-Token': token,
          'ngrok-skip-browser-warning': 'true',
        },
      );
      return _handleResponse(response);
    } catch (e) {
      debugPrint('Erro na requisição GET: $e');
      return null;
    }
  }

  Future<dynamic> _proxyPost(String endpoint, Map<String, dynamic> data) async {
    final token = providerToken;
    final url = AppConfig.sgpProxyUrl(endpoint);

    final payload = Map<String, dynamic>.from(data);
    payload['provider_token'] = token;

    try {
      debugPrint('SGPService: POST ${AppConfig.redactUri(url)}');
      debugPrint('Payload keys: ${payload.keys.toList()}');

      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
          'X-Provider-Token': token,
          'ngrok-skip-browser-warning': 'true',
        },
        body: jsonEncode(payload),
      );

      return _handleResponse(response);
    } catch (e) {
      debugPrint('Erro na requisição: $e');
      return null;
    }
  }

  // --- INTERNAL API METHODS (Direct Backend Access) ---
  Future<dynamic> apiGet(String endpoint, Map<String, String> params) async {
    final token = providerToken;
    final fullParams = Map<String, String>.from(params);

    final base = AppConfig.apiUrl(endpoint);
    final url = base.replace(queryParameters: {
      ...base.queryParameters,
      ...fullParams,
    });

    try {
      debugPrint('SGPService: API GET ${AppConfig.redactUri(url)}');
      final response = await http.get(url, headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
        'X-Provider-Token': token,
      });
      return _handleResponse(response);
    } catch (e) {
      debugPrint('Erro na requisição API GET: $e');
      return null;
    }
  }

  Future<dynamic> apiPost(String endpoint, Map<String, dynamic> data) async {
    final token = providerToken;
    final payload = Map<String, dynamic>.from(data);
    payload['provider_token'] = token;

    String path = endpoint.startsWith('/') ? endpoint.substring(1) : endpoint;
    if (path.startsWith('api/')) path = path.substring(4);
    final base = AppConfig.apiUrl(path);
    final url = base;
    try {
      debugPrint('SGPService: API POST ${AppConfig.redactUri(url)}');
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
          'X-Provider-Token': token,
        },
        body: jsonEncode(payload),
      );
      return _handleResponse(response);
    } catch (e) {
      debugPrint('Erro na requisição API POST: $e');
      return null;
    }
  }

  /// Busca a hora oficial do servidor (Brasília)
  Future<DateTime?> getServerTime() async {
    try {
      final data = await apiGet('api/public/server-time/', {});
      if (data != null && data['server_time'] != null) {
        return DateTime.parse(data['server_time']);
      }
    } catch (e) {
      debugPrint('Erro ao buscar hora do servidor: $e');
    }
    return null;
  }

  dynamic _handleResponse(http.Response response) {
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      final isHtml = response.body.contains('<!DOCTYPE html>') || response.body.contains('<html');
      final bodyToLog = isHtml ? '[HTML content hidden]' : response.body;
      debugPrint('Backend error: ${response.statusCode} - $bodyToLog');
      throw Exception('Failed to load data: ${response.statusCode}');
    }
  }

  // Specific SGP Methods
  Future<Map<String, dynamic>?> getClientByCpf(String cpfCnpj) async {
    try {
      final data = await _proxyPost('cliente/consulta/', {'cpf_cnpj': cpfCnpj});
      return data;
    } catch (e) {
      debugPrint('Erro ao buscar cliente: $e');
      final msg = e.toString();
      if (msg.contains('403')) {
        throw Exception('USER_BLOCKED');
      }
      return null;
    }
  }

  Future<List<dynamic>> getInvoices(String cpfCnpj, {String? status}) async {
    try {
      final payload = {'cpf_cnpj': cpfCnpj};
      if (status != null) payload['status'] = status;
      
      final data = await _proxyPost('ura/titulos/', payload);
      
      if (data is List) return data;
      if (data is Map<String, dynamic>) {
        if (data.containsKey('titulos')) return data['titulos'];
        if (data.containsKey('faturas')) return data['faturas'];
      }
      return [];
    } catch (e) {
      debugPrint('Erro ao buscar faturas: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>?> getContractInfo(String contractId) async {
    return await _proxyPost('contrato/$contractId/', {});
  }

  Future<Map<String, dynamic>?> getCpeInfo(String contractId) async {
    return await _proxyPost('cpe/$contractId/', {});
  }

  Future<List<dynamic>> getContratos(String cpfCnpj, String password) async {
    try {
      debugPrint('SGPService: Buscando contratos/assinaturas para CPF $cpfCnpj');
      
      // Chama o endpoint do backend que faz proxy para ura/consultacliente
      final data = await _proxyPost('cliente/consulta/', {
        'cpf_cnpj': cpfCnpj, 
        'assinatura_eletronica': 1,
        'app': 'asnetchat', 
      });
      
      debugPrint('SGPService: Resposta contratos: $data');

      if (data is Map<String, dynamic>) {
        if (data.containsKey('contratos')) return data['contratos'];
      }
      return [];
    } catch (e) {
      debugPrint('Erro ao buscar contratos: $e');
      return [];
    }
  }

  // Support Tickets
  Future<List<dynamic>> getSupportTickets(String cpfCnpj, String password, String contractId) async {
    try {
      final data = await _proxyPost('central/chamado/list/', {
        'cpfcnpj': cpfCnpj,
        'contrato': contractId,
        'oc_status': '0',
      });
      
      if (data is List) return data;
      if (data is Map<String, dynamic>) {
        if (data.containsKey('chamados')) return data['chamados'];
        if (data.containsKey('list')) return data['list'];
        if (data.containsKey('registros')) return data['registros'];
      }
      return [];
    } catch (e) {
      debugPrint('Erro ao buscar chamados: $e');
      return [];
    }
  }

  Future<List<dynamic>> getFiscalNotes(String cpfCnpj, String password, String contractId) async {
    try {
      final data = await _proxyPost('central/notafiscal/list/', {
        'cpfcnpj': cpfCnpj,
        'senha': password,
        'contrato': contractId,
      });
      if (data is List) return data;
      return [];
    } catch (e) {
      debugPrint('Erro ao buscar notas fiscais: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>> openSupportTicket(String cpfCnpj, String password, String contractId, String typeId, String message) async {
    try {
      final data = await _proxyPost('ura/chamado/', {
        'contrato': contractId,
        'ocorrenciatipo': typeId, 
        'conteudo': message,
        'conteudolimpo': message, 
      });
      return data is Map<String, dynamic> ? data : {'status': 'success', 'data': data};
    } catch (e) {
      debugPrint('Erro ao abrir chamado: $e');
      return {'error': e.toString()};
    }
  }

  Future<bool> changeWifi(String contractId, {String? ssid, String? password, String? ssid5g, String? password5g}) async {
    debugPrint('DEBUG: changeWifi called for contract $contractId');
    try {
      final payload = {
        'contrato': contractId,
      };
      
      if (ssid != null && ssid.isNotEmpty) payload['novo_ssid'] = ssid;
      if (password != null && password.isNotEmpty) payload['nova_senha'] = password;
      if (ssid5g != null && ssid5g.isNotEmpty) payload['novo_ssid_5ghz'] = ssid5g;
      if (password5g != null && password5g.isNotEmpty) payload['nova_senha_5ghz'] = password5g;

      await apiPost('wifi/config/', payload);
      return true;
    } catch (e) {
      debugPrint('Erro ao alterar wifi: $e');
      return false;
    }
  }

  Future<Map<String, dynamic>?> verifyAccess(String contractId) async {
    try {
      final data = await _proxyPost('ura/verificaacesso/', {
        'contrato': contractId,
      });
      return data is Map<String, dynamic> ? data : null;
    } catch (e) {
      debugPrint('Erro ao verificar acesso do modem: $e');
      return null;
    }
  }

  static Map<String, String> parseAccessStatus(dynamic resp) {
    if (resp == null) {
      return {'connection': 'unknown', 'label': 'Indisponível'};
    }
    if (resp is List) {
      if (resp.isNotEmpty) {
        return {'connection': 'online', 'label': 'Online'};
      }
      return {'connection': 'offline', 'label': 'Offline'};
    }
    if (resp is! Map) {
      return {'connection': 'unknown', 'label': 'Indisponível'};
    }

    final status = resp['status'] ?? resp['status_conexao'];
    final statusStr = status?.toString().toUpperCase() ?? '';

    if (status == 9 || statusStr.contains('MANUTEN')) {
      return {'connection': 'manutencao', 'label': 'Em manutenção'};
    }
    if (status == 1 ||
        statusStr == '1' ||
        statusStr == 'ONLINE' ||
        statusStr == 'ATIVO' ||
        statusStr == 'TRUE') {
      return {'connection': 'online', 'label': 'Online'};
    }
    if (status == 0 ||
        statusStr == '0' ||
        statusStr.contains('OFFLINE') ||
        statusStr == 'FALSE') {
      return {'connection': 'offline', 'label': 'Offline'};
    }
    if (statusStr.contains('ONLINE')) {
      return {'connection': 'online', 'label': 'Online'};
    }
    return {'connection': 'offline', 'label': 'Offline'};
  }

  Future<Map<String, dynamic>?> getModemInfo(String contractId) async {
    try {
      debugPrint('SGPService: Fetching modem info for contract: $contractId');
      final data = await apiGet('wifi/config/', {'contrato': contractId});
      debugPrint('SGPService: Modem info response: $data');
      return data;
    } catch (e) {
      debugPrint('Erro ao buscar info do modem: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> getConnectedDevices(String contractId) async {
    try {
      debugPrint('SGPService: Fetching connected devices for contract: $contractId');
      final data = await apiGet('wifi/hosts/', {'contrato': contractId});
      debugPrint('SGPService: Connected devices response: $data');
      return data;
    } catch (e) {
      debugPrint('Erro ao buscar dispositivos conectados: $e');
      return null;
    }
  }
  Future<Map<String, dynamic>> openTicket(String contractId, String title, String description) async {
    try {
      final result = await _proxyPost('chamado/novo/', {
        'contract_id': contractId,
        'assunto': title,
        'mensagem': description,
      });
      return result ?? {};
    } catch (e) {
      debugPrint('Erro ao abrir chamado: $e');
      return {};
    }
  }

  Future<Map<String, dynamic>> unlockContract(String contractId, {String message = 'Solicitação de Desbloqueio via App'}) async {
    try {
      final result = await _proxyPost('ura/liberacaopromessa/', {
        'contrato': contractId,
        'conteudo': message,
      });
      return result is Map<String, dynamic> ? result : {};
    } catch (e) {
      debugPrint('Erro ao desbloquear contrato: $e');
      return {'status': 0, 'msg': 'Não foi possível concluir o desbloqueio agora. Tente novamente.'};
    }
  }

  Future<List<dynamic>> getConsumption(String cpfCnpj, String password, String contractId, int month, int year) async {
    try {
      final data = await _proxyPost('central/extratouso/', {
        'cpfcnpj': cpfCnpj,
        'senha': password,
        'contrato': contractId,
        'mes': month,
        'ano': year,
      });

      if (data is List) return data;
      if (data is Map<String, dynamic>) {
        if (data.containsKey('list')) return data['list'];
        if (data.containsKey('extrato')) return data['extrato'];
        if (data.containsKey('dados')) return data['dados'];
      }
      return [];
    } catch (e) {
      debugPrint('Erro ao buscar consumo: $e');
      return [];
    }
  }

  Future<Map<String, dynamic>> getConsultaCliente(String cpfCnpj) async {
    try {
      final data = await _proxyPost('ura/consultacliente/', {
        'app': 'asnetchat', 
        'cpfcnpj': cpfCnpj,
        'assinatura_eletronica': 1,
      });
      return data is Map<String, dynamic> ? data : {};
    } catch (e) {
      debugPrint('Erro ao consultar cliente (ura/consultacliente): $e');
      return {};
    }
  }
}