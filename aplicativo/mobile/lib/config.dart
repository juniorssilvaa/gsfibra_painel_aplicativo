import 'dart:convert';
import 'package:http/http.dart' as http;

/// Configurações do aplicativo - Versão Sincronizada
class AppConfig {
  static const int providerId = 10;
  static const String providerName = 'gsfibra';
  static String? _runtimeApiBaseUrl;

  static void setRuntimeApiBaseUrl(String? baseUrl) {
    if (baseUrl == null || baseUrl.isEmpty) {
      _runtimeApiBaseUrl = null;
    } else {
      _runtimeApiBaseUrl = baseUrl.endsWith('/') ? baseUrl : '$baseUrl/';
    }
  }

  static const String _rawApiToken = String.fromEnvironment(
    'PROVIDER_API_TOKEN',
    defaultValue: '',
  );

  /// Token sk_live_* do painel (Integração). Nunca deve ser a URL da API.
  static String get apiToken {
    final t = _rawApiToken.replaceAll('+', '').trim();
    if (t.isEmpty ||
        t.startsWith('http://') ||
        t.startsWith('https://') ||
        t.contains('/v1') ||
        t.contains('niohub.com')) {
      throw StateError(
        'PROVIDER_API_TOKEN inválido (parece URL ou está vazio). '
        'Use o sk_live_... de "Seu Token de Integração" do painel do app.',
      );
    }
    return t;
  }

  static Map<String, String> get apiHeaders => {
        'Authorization': 'Bearer $apiToken',
        'X-Provider-Token': apiToken,
      };

  static String redactUri(Uri uri) {
    final q = Map<String, String>.from(uri.queryParameters);
    for (final key in const ['provider_token', 'token', 'assinatura_eletronica', 'password', 'senha']) {
      if (q.containsKey(key)) q[key] = '***';
    }
    return uri.replace(queryParameters: q.isEmpty ? null : q).toString();
  }
  static const String supportPhone = '+558597095195';
  /// API do painel GSFibra (mesmo host do painel, porta 8443).
  /// Local: --dart-define=API_BASE_URL=http://127.0.0.1:8010/v1/
  static const String _envApiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://painelapp.gsfibra.com:8443/v1/',
  );

  static String get apiBaseUrl {
    String base = (_runtimeApiBaseUrl ?? _envApiBaseUrl).trim();
    if (!base.endsWith('/')) base = '$base/';
    if (base.endsWith('/api/')) {
      base = '${base.substring(0, base.length - 4)}v1/';
    } else if (RegExp(r'^https?://[^/]+/$').hasMatch(base)) {
      base = '${base}v1/';
    }
    return base;
  }

  static bool get _usesV1 => apiBaseUrl.contains('/v1/');

  static const Map<String, String> _legacyToV1 = {
    'public/config/': 'home/',
    'public/warnings/': 'warnings/',
    'public/warnings/dismiss/': 'warnings/dismiss/',
    'public/plans/': 'plans/',
    'public/server-time/': 'time/',
    'app/register/': 'auth/register/',
    'devices/register/': 'devices/register/',
  };

  static String _normalizeRelativePath(String endpoint) {
    String path = endpoint.startsWith('/') ? endpoint.substring(1) : endpoint;
    if (path.startsWith('api/')) path = path.substring(4);
    if (path.startsWith('v1/')) path = path.substring(3);
    return path;
  }

  static String _toV1Path(String path) {
    final qIndex = path.indexOf('?');
    final pathOnly = qIndex >= 0 ? path.substring(0, qIndex) : path;
    final query = qIndex >= 0 ? path.substring(qIndex) : '';
    final normalized = pathOnly.endsWith('/') ? pathOnly : '$pathOnly/';
    return '${_legacyToV1[normalized] ?? pathOnly}$query';
  }

  static Uri apiUrl(String endpoint) {
    final base = apiBaseUrl;
    var path = _normalizeRelativePath(endpoint);
    String? query;
    final qIndex = path.indexOf('?');
    if (qIndex >= 0) {
      query = path.substring(qIndex + 1);
      path = path.substring(0, qIndex);
    }
    if (_usesV1) {
      final pathOnly = path;
      if (pathOnly == 'sgp' || pathOnly.startsWith('sgp/')) {
        final apiBase = base.replaceFirst(RegExp(r'/v1/?$'), '/api/');
        final uri = Uri.parse('$apiBase$path${query != null ? '?$query' : ''}');
        print('NETWORK: ${redactUri(uri)}');
        return uri;
      }
      path = _toV1Path(path + (query != null ? '?$query' : ''));
      query = null;
      final q2 = path.indexOf('?');
      if (q2 >= 0) {
        query = path.substring(q2 + 1);
        path = path.substring(0, q2);
      }
    }
    final uri = Uri.parse('$base$path${query != null ? '?$query' : ''}');
    print('NETWORK: ${redactUri(uri)}');
    return uri;
  }

  /// Monta URL SGP proxy com provider_token corretamente encoded.
  static Uri sgpProxyUrl(String endpoint, {Map<String, String>? query}) {
    final clean = endpoint.replaceAll(RegExp(r'^/+|/+$'), '');
    final params = <String, String>{
      if (query != null) ...query,
    };
    final base = apiUrl('sgp/$clean/');
    return base.replace(queryParameters: {
      ...base.queryParameters,
      ...params,
    });
  }

  static int _serverOffsetMs = 0;

  static Future<void> syncTime() async {
    try {
      final response = await http.get(apiUrl('public/server-time/')).timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _serverOffsetMs = DateTime.parse(data['server_time']).millisecondsSinceEpoch - DateTime.now().millisecondsSinceEpoch;
      }
    } catch (_) {}
  }

  static void setServerTime(DateTime serverTime) {
    _serverOffsetMs = serverTime.millisecondsSinceEpoch - DateTime.now().millisecondsSinceEpoch;
  }

  static DateTime getToday() {
    if (_serverOffsetMs != 0) return DateTime.now().add(Duration(milliseconds: _serverOffsetMs));
    return DateTime.now().toUtc().subtract(const Duration(hours: 3));
  }
}
