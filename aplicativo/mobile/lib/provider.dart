import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'config.dart';
import 'theme/app_branding.dart';
import 'theme/brand_colors.dart';
import 'services/sgp_service.dart';
import 'services/ai_service.dart';
import 'services/telemetry_service.dart';
import 'services/push_service.dart';

class AppProvider with ChangeNotifier {
  // Theme
  ThemeMode _themeMode = ThemeMode.light;

  // Estado de Autenticação
  bool _isLoggedIn = false;
  String? _cpf;
  String? _token;
  String? _providerToken;
  String? _userName;
  String? _centralPassword;
  Map<String, dynamic> _userContract = {};
  Map<String, dynamic> _userInfo = {};

  // Services
  SGPService? _sgpService;
  AIService? _aiService;
  final TelemetryService _telemetryService = TelemetryService();
  final PushService _pushService = PushService();

  // Configuração do App (Atalhos e Ferramentas)
  List<String> _activeShortcuts = [];
  List<String> _activeTools = [];
  bool _appConfigLoaded = false;
  bool _isBlocked = false;
  String _speedTestProvider = 'fast';
  String _termsText = '';
  String _privacyText = '';
  Timer? _accessCheckTimer;

  // Notificações
  List<Map<String, dynamic>> _notifications = [];
  List<String> _readNotificationIds = [];

  int get unreadNotificationsCount => _notifications.where((n) => n['read'] != true).length;
  List<Map<String, dynamic>> get notifications => _notifications;

  // Getters
  ThemeMode get themeMode => _themeMode;
  bool get isLoggedIn => _isLoggedIn;
  String? get cpf => _cpf;
  String? get token => _token;
  String? get providerToken => _providerToken;
  String? get userName => _userName;
  String? get centralPassword => _centralPassword;
  Map<String, dynamic> get userContract => _userContract;
  Map<String, dynamic> get userInfo => _userInfo;
  SGPService? get sgpService => _sgpService;
  AIService? get aiService => _aiService;
  TelemetryService get telemetryService => _telemetryService;
  PushService get pushService => _pushService;
  List<String> get activeShortcuts => _activeShortcuts;
  List<String> get activeTools => _activeTools;
  bool get appConfigLoaded => _appConfigLoaded;
  bool get isBlocked => _isBlocked;
  String get speedTestProvider => _speedTestProvider;
  String get termsText => _termsText;
  String get privacyText => _privacyText;
  Color get brandPrimary => BrandColors.primary;

  AppProvider();

  // Inicializar Push Service
  bool _pushListening = false;

  Future<void> initPushService() async {
    _pushService.onTokenReady = (token) {
      if (!_isLoggedIn || _cpf == null) return;
      String? customerId = _userInfo['id']?.toString() ?? _userInfo['id_cliente']?.toString();
      if (customerId == null && _userContract.isNotEmpty) {
        customerId = _userContract['id']?.toString() ?? _userContract['contract_id']?.toString();
      }
      unawaited(_pushService.registerDevice(cpf: _cpf, contractId: customerId, name: _userName));
    };

    await _pushService.initialize();
    
    if (!_pushListening) {
      _pushService.messageStream.listen((message) {
        if (!_notifications.any((n) => n['id'] == message['id'])) {
           final text = (message['message'] ?? message['body'] ?? '').toString();
           _notifications.insert(0, {
             ...message,
             'message': text,
             'body': text,
             'read': false,
             'isRead': false,
           });
           notifyListeners();
        }
      });
      _pushListening = true;
    }
    
    if (_isLoggedIn && _cpf != null) {
      String? customerId = _userInfo['id']?.toString() ?? _userInfo['id_cliente']?.toString();
      if (customerId == null && _userContract.isNotEmpty) {
        customerId = _userContract['id']?.toString() ?? _userContract['contract_id']?.toString();
      }
      await _pushService.registerDevice(cpf: _cpf, contractId: customerId, name: _userName);
      final prefs = await SharedPreferences.getInstance();
      final tokenNow = _pushService.token ?? '';
      await prefs.setString('last_push_reg_sig', '${_cpf ?? ''}|$tokenNow|v3');
    }
  }

  Future<void> initialize() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _isLoggedIn = false; // Não persistir login entre sessões conforme solicitado
      _cpf = prefs.getString('cpf');
      _token = prefs.getString('token');
      _providerToken = AppConfig.apiToken; 
      _userName = prefs.getString('userName');
      _centralPassword = prefs.getString('centralPassword');
      _themeMode = prefs.getString('themeMode') == 'dark' ? ThemeMode.dark : ThemeMode.light;
      notifyListeners();
      
      _initServices(_providerToken!);

      final cachedShortcuts = prefs.getString('activeShortcuts');
      final cachedTools = prefs.getString('activeTools');
      _readNotificationIds = prefs.getStringList('read_notifications') ?? [];

      if (_isLoggedIn) {
        await fetchNotifications();
      }
      
      if (cachedShortcuts != null) {
        try {
          _activeShortcuts = List<String>.from(jsonDecode(cachedShortcuts));
          _appConfigLoaded = true;
        } catch (_) {}
      }
      if (cachedTools != null) {
        try {
          _activeTools = List<String>.from(jsonDecode(cachedTools));
          _appConfigLoaded = true;
        } catch (_) {}
      }
      _termsText = prefs.getString('termsText') ?? '';
      _privacyText = prefs.getString('privacyText') ?? '';
      
      await fetchAppConfig();
      
      if (prefs.containsKey('userContract')) {
        final contractJson = prefs.getString('userContract');
        if (contractJson != null) {
          try {
            _userContract = Map<String, dynamic>.from(jsonDecode(contractJson));
          } catch (e) {
            debugPrint('Erro ao carregar contrato: $e');
          }
        }
      }
      
      if (prefs.containsKey('userInfo')) {
        final infoJson = prefs.getString('userInfo');
        if (infoJson != null) {
          try {
            _userInfo = Map<String, dynamic>.from(jsonDecode(infoJson));
          } catch (e) {
            debugPrint('Erro ao carregar info do usuário: $e');
          }
        }
      }

      // As travas de segurança agressivas para ID "1" e nomes genéricos foram removidas
      // para suportar contratos reais com esses valores.

      notifyListeners();
    } catch (e) {
      debugPrint('Erro na inicialização do Provider: $e');
    }
  }

  void _initServices(String provToken) {
    _sgpService = SGPService(providerToken: provToken);
    _aiService = AIService(providerToken: provToken);
  }

  void _startAccessCheck() {
    _accessCheckTimer?.cancel();
    _accessCheckTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      if (_isLoggedIn) {
        fetchAppConfig();
      }
    });
  }

  void _stopAccessCheck() {
    _accessCheckTimer?.cancel();
    _accessCheckTimer = null;
  }

  Future<void> fetchAppConfig() async {
    try {
      final tokenToUse = _providerToken ?? AppConfig.apiToken;
      final cpfDigits = (_cpf ?? '').replaceAll(RegExp(r'[^\d]'), '');
      final cpfParam = cpfDigits.isNotEmpty ? {'cpf': cpfDigits} : <String, String>{};
      final base = AppConfig.apiUrl('public/config/');
      final url = base.replace(queryParameters: {
        ...base.queryParameters,
        ...cpfParam,
      });
      final response = await http.get(
        url,
        headers: {
          'Authorization': 'Bearer $tokenToUse',
          'X-Provider-Token': tokenToUse,
          'X-App-Default-Theme': AppBranding.buildDefaultsJson,
        },
      ).timeout(const Duration(seconds: 3));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['active_shortcuts'] != null) {
          _activeShortcuts = List<String>.from(data['active_shortcuts']);
        }
        if (data['active_tools'] != null) {
          if (data['active_tools'] is Map) {
            final toolsMap = data['active_tools'] as Map;
            _activeTools = toolsMap.entries.where((e) => e.value == true).map((e) => e.key.toString()).toList();
          } else if (data['active_tools'] is List) {
            _activeTools = List<String>.from(data['active_tools']);
          }
        }

        if (data['speed_test_provider'] != null) {
          _speedTestProvider = data['speed_test_provider'].toString();
        }

        final terms = (data['terms_text'] ?? data['termos'] ?? '').toString();
        final privacy = (data['privacy_text'] ?? data['privacidade'] ?? '').toString();
        if (terms != _termsText) {
          _termsText = terms;
        }
        if (privacy != _privacyText) {
          _privacyText = privacy;
        }
        await AppBranding.applyFromApi(data);
        
        final userBlocked = data['user_blocked'] == true;
        final providerBlocked = data['provider_blocked'] == true ||
            data['is_blocked'] == true ||
            data['is_active'] == false;
        final blocked = providerBlocked && !userBlocked;
        if (blocked != _isBlocked) {
          _isBlocked = blocked;
          if (_isBlocked) {
            debugPrint('PROVIDER: Sistema bloqueado pelo SuperAdmin.');
          }
          notifyListeners();
        }

        _appConfigLoaded = true;
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('activeShortcuts', jsonEncode(_activeShortcuts));
        await prefs.setString('activeTools', jsonEncode(_activeTools));
        await prefs.setString('termsText', _termsText);
        await prefs.setString('privacyText', _privacyText);
        notifyListeners();
      } else if (response.statusCode == 403) {
        Map<String, dynamic>? data;
        try {
          data = jsonDecode(response.body) as Map<String, dynamic>?;
        } catch (_) {}
        final userBlocked = data?['user_blocked'] == true;
        if (!userBlocked && !_isBlocked) {
          _isBlocked = true;
          debugPrint('PROVIDER: Acesso negado pelo servidor (403).');
          notifyListeners();
        }
      }
    } catch (_) {}
  }

  Future<void> login({
    required String cpf,
    required String token,
    required String providerToken,
    String? userName,
    String? centralPassword,
    Map<String, dynamic>? contract,
    Map<String, dynamic>? info,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    // await prefs.setBool('isLoggedIn', true); // Removido para forçar login toda vez que o app abre
    await prefs.setString('cpf', cpf);
    await prefs.setString('token', token);
    await prefs.setString('providerToken', providerToken);
    if (userName != null) await prefs.setString('userName', userName);
    if (centralPassword != null) await prefs.setString('centralPassword', centralPassword);
    
    if (contract != null) await prefs.setString('userContract', jsonEncode(contract));
    if (info != null) await prefs.setString('userInfo', jsonEncode(info));

    _isLoggedIn = true;
    _cpf = cpf.replaceAll(RegExp(r'[^\d]'), '');
    _token = token;
    _providerToken = providerToken;
    _userName = userName;
    _centralPassword = centralPassword;
    _userContract = contract ?? {};
    _userInfo = info ?? {};
    
    _initServices(providerToken);
    _startAccessCheck();
    await fetchAppConfig();
    await fetchNotifications();
    
    try {
      String? customerId = info?['id']?.toString() ?? info?['id_cliente']?.toString();
      if (customerId == null && contract != null) {
        customerId = contract['id']?.toString() ?? contract['contract_id']?.toString();
      }

      String model = 'Unknown';
      String manufacturer = 'Unknown';
      String osVersion = 'Unknown';
      final deviceInfo = DeviceInfoPlugin();
      
      if (Platform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        model = androidInfo.model;
        manufacturer = androidInfo.manufacturer;
        osVersion = 'Android ${androidInfo.version.release} (SDK ${androidInfo.version.sdkInt})';
      } else if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        model = iosInfo.utsname.machine;
        manufacturer = 'Apple';
        osVersion = 'iOS ${iosInfo.systemVersion}';
      }

      String? allLogins;
      try {
        final List<String> logins = [];
        if (info != null && info['contratos'] is List) {
          for (var c in info['contratos']) {
            final l = c['servico_login'] ?? c['login'] ?? c['pppoe_login'];
            if (l != null && l.toString().trim().isNotEmpty) {
              final s = l.toString().trim();
              if (!logins.contains(s)) logins.add(s);
            }
          }
        }
        if (logins.isEmpty) {
          final l = contract?['servico_login'] ?? contract?['login'] ?? contract?['pppoe_login'];
          if (l != null) logins.add(l.toString().trim());
        }
        if (logins.isNotEmpty) allLogins = logins.join(', ');
      } catch (_) {}

      if (customerId != null) {
        final url = AppConfig.apiUrl('app/register/');
        http.post(
          url,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'provider_token': providerToken,
            'cpf': cpf,
            'name': userName,
            'email': info?['email'],
            'customer_id': customerId,
            'device_platform': Platform.isAndroid ? 'android' : 'ios',
            'push_token': _pushService.token,
            'fcm_token': _pushService.token,
            'pppoe_login': allLogins,
            'model': model,
            'manufacturer': manufacturer,
            'os_version': osVersion,
          }),
        ).then((_) => debugPrint('Usuário registrado no backend')).catchError((_) {});
        
        final tokenNow = _pushService.token ?? '';
        await _pushService.registerDevice(cpf: cpf, contractId: customerId, name: userName);
        await prefs.setString('last_push_reg_sig', '${cpf}|$tokenNow|v3');
      }
      
      await refreshData();
    } catch (_) {}

    notifyListeners();
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('isLoggedIn');
    await prefs.remove('cpf');
    await prefs.remove('token');
    await prefs.remove('providerToken');
    await prefs.remove('userName');
    await prefs.remove('centralPassword');
    await prefs.remove('userContract');
    await prefs.remove('userInfo');
    await prefs.remove('activeShortcuts');
    await prefs.remove('activeTools');
    
    _stopAccessCheck();
    _isLoggedIn = false;
    _cpf = null;
    _token = null;
    _providerToken = null;
    _userName = null;
    _userContract = {};
    _userInfo = {};
    _sgpService = null;
    _aiService = null;
    _isBlocked = false;
    _providerToken = AppConfig.apiToken;
    _initServices(_providerToken!);
    notifyListeners();
    await fetchAppConfig();
  }

  void setProviderBlocked(bool value) {
    if (_isBlocked == value) return;
    _isBlocked = value;
    notifyListeners();
  }

  Future<void> fetchNotifications() async {
    if (!_isLoggedIn || _cpf == null) return;
    try {
      // Tenta obter o ID do contrato de várias formas para garantir que o filtro no backend funcione
      String? contractId = _userContract['id']?.toString() ?? 
                          _userContract['contrato']?.toString() ?? 
                          _userContract['contract_id']?.toString();
      
      debugPrint('BUSCANDO AVISOS PARA CPF: $_cpf E CONTRATO: $contractId');

      // O backend usa public/warnings/ para avisos in-app
      final warningsResponse = await _sgpService?.apiGet('public/warnings/', {
        'cpf': _cpf ?? '',
        'contract_id': contractId ?? ''
      });
      
      List<Map<String, dynamic>> allFetched = [];
      
      if (warningsResponse is List) {
        debugPrint('AVISOS RECEBIDOS: ${warningsResponse.length}');
        final mappedWarnings = warningsResponse.map((w) {
          final map = Map<String, dynamic>.from(w);
          final text = (map['message'] ?? map['body'] ?? '').toString();
          return {
            'id': 'warning_${map['id']}',
            'backend_warning_id': map['id'],
            'title': map['title'],
            'message': text,
            'body': text,
            'type': map['type'] ?? 'info',
            'sticky': map['sticky'] ?? false,
            'show_home': map['show_home'] ?? false,
            'created_at': map['created_at'],
            'is_warning': true,
          };
        }).toList();
        allFetched.addAll(mappedWarnings);
      } else {
        debugPrint('NENHUM AVISO RETORNADO PELO BACKEND');
      }
      
      _notifications = allFetched.map((n) {
        final id = n['id'].toString();
        return {...n, 'isRead': _readNotificationIds.contains(id), 'read': _readNotificationIds.contains(id)};
      }).toList();
      _notifications.sort((a, b) => (b['created_at']?.toString() ?? '').compareTo(a['created_at']?.toString() ?? ''));
      notifyListeners();
    } catch (e) {
      debugPrint('Erro ao buscar avisos: $e');
    }
  }

  Future<void> dismissNotification(String id) async {
    try {
      final index = _notifications.indexWhere((n) => n['id'].toString() == id);
      if (index == -1) return;
      final notif = _notifications[index];
      if (notif['is_warning'] == true && notif['backend_warning_id'] != null) {
        // Corrigido para o caminho correto no backend
        await _sgpService?.apiPost('public/warnings/dismiss/', {
          'warning_id': notif['backend_warning_id'], 
          'cpf': _cpf
        });
      }
      _notifications.removeAt(index);
      if (!_readNotificationIds.contains(id)) _readNotificationIds.add(id);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('read_notifications', _readNotificationIds);
      notifyListeners();
    } catch (_) {}
  }

  Future<void> dismissReadNotifications() async {
    final toDismiss = _notifications.where((n) => n['isRead'] == true || n['read'] == true).toList();
    for (var n in toDismiss) {
      await dismissNotification(n['id'].toString());
    }
  }

  Future<void> clearSupportChatNotifications() async {
    final support = _notifications.where((n) {
      final type = (n['type'] ?? '').toString();
      return type == 'support_chat' || type == 'support';
    }).toList();
    for (final n in support) {
      await dismissNotification(n['id'].toString());
    }
    try {
      await _pushService.cancelAllLocalNotifications();
    } catch (_) {}
  }

  Future<void> markNotificationAsRead(String id) async {
    if (!_readNotificationIds.contains(id)) {
      _readNotificationIds.add(id);
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('read_notifications', _readNotificationIds);
    }
    final index = _notifications.indexWhere((n) => n['id'].toString() == id);
    if (index != -1) {
      _notifications[index]['isRead'] = true;
      _notifications[index]['read'] = true;
      notifyListeners();
    }
  }

  Future<void> updateUserInfo(Map<String, dynamic> info) async {
    _userInfo = {..._userInfo, ...info};
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('userInfo', jsonEncode(_userInfo));
    notifyListeners();
  }

  Future<void> updateContract(Map<String, dynamic> contract) async {
    _userContract = contract;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('userContract', jsonEncode(contract));
    notifyListeners();
  }

  Future<void> toggleTheme(bool isDark) async {
    _themeMode = isDark ? ThemeMode.dark : ThemeMode.light;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('themeMode', isDark ? 'dark' : 'light');
    notifyListeners();
  }

  Future<Map<String, dynamic>> unlockContract(String contractId) async {
    if (_sgpService == null) return {'status': 0, 'msg': 'Serviço indisponível'};
    return await _sgpService!.unlockContract(contractId);
  }

  Future<void> refreshData() async {
    await fetchAppConfig();
    fetchNotifications();
    if (_cpf == null || _sgpService == null) return;
    try {
      Map<String, dynamic>? clientFullData = await _sgpService!.getClientByCpf(_cpf!);
      List contratos = [];
      if (_centralPassword != null && _centralPassword!.isNotEmpty) {
          try { contratos = await _sgpService!.getContratos(_cpf!, _centralPassword!); } catch (_) {}
      }
      if (contratos.isEmpty && clientFullData != null && clientFullData['contratos'] != null) {
           contratos = clientFullData['contratos'];
      }

      if (contratos.isNotEmpty) {
           final List<Map<String, dynamic>> allMappedContracts = [];
           for (var c in contratos) {
               bool hasNoAddress = (c['endereco_logradouro'] == null || c['endereco_logradouro'].toString().trim().isEmpty) && (c['logradouro'] == null || c['logradouro'].toString().trim().isEmpty);
               if (clientFullData != null && hasNoAddress) {
                   var match;
                   final String cId = (c['contrato'] ?? c['id'] ?? c['contratoId'])?.toString() ?? '';
                   if (clientFullData['contratos'] is List && cId.isNotEmpty) {
                       try {
                           match = (clientFullData['contratos'] as List).firstWhere((element) => (element['contrato']?.toString() == cId) || (element['id']?.toString() == cId), orElse: () => null);
                       } catch (_) {}
                   }
                   if (match != null) {
                        c = <String, dynamic>{...match, ...c};
                        c['logradouro'] = c['logradouro'] ?? match['logradouro'] ?? match['endereco_logradouro'];
                        c['numero'] = c['numero'] ?? match['numero'] ?? match['endereco_numero'];
                        c['bairro'] = c['bairro'] ?? match['bairro'] ?? match['endereco_bairro'];
                    } else {
                        c['logradouro'] = c['logradouro'] ?? clientFullData['logradouro'];
                        c['numero'] = c['numero'] ?? clientFullData['numero'];
                        c['bairro'] = c['bairro'] ?? clientFullData['bairro'];
                    }
               }
               String logradouro = (c['endereco_logradouro'] ?? c['logradouro'] ?? '').toString().trim();
               String numero = (c['endereco_numero'] ?? c['numero'] ?? 'S/N').toString().trim();
               String bairro = (c['endereco_bairro'] ?? c['bairro'] ?? '').toString().trim();
               String enderecoCompleto = logradouro.isNotEmpty ? '$logradouro, $numero - $bairro' : 'Endereço não cadastrado';

               allMappedContracts.add({
                 'id': c['contratoId']?.toString() ?? c['contrato']?.toString() ?? '1',
                 'status': c['contratoStatusDisplay'] ?? c['status'] ?? 'ATIVO',
                 'plan_name': c['planointernet'] ?? 'PLANO INTERNET',
                 'contract_due_day': c['cobVencimento']?.toString() ?? '30',
                 'registration_date': c['data_cadastro'] ?? '24/10/2024',
                 'address': enderecoCompleto,
                 'login': c['login'],
                 'is_exempt': (c['isento'] == true || 
                              c['cobPermuta'] == true || 
                              c['isento_mensalidade'] == true ||
                              c['isento_aluguel'] == true ||
                              c['cobIsento'] == true ||
                              c['isentoMensalidade'] == true),
               });
           }
           final currentId = (_userContract['id'] ?? _userContract['contrato'] ?? _userContract['contract_id'])?.toString().trim();
           _userContract = allMappedContracts.firstWhere((c) => c['id'].toString().trim() == currentId, orElse: () => allMappedContracts.first);
           
           final sTime = await _sgpService!.getServerTime();
           if (sTime != null) AppConfig.setServerTime(sTime);
           final invoices = await _sgpService!.getInvoices(_cpf!);
           
           // Limpa dados de fatura anterior para evitar lixo se não encontrar nada
           _userContract['last_invoice_value'] = null;
           _userContract['last_invoice_due'] = null;
           
           if (invoices.isNotEmpty) {
              // Filtrar faturas específicas para este contrato (Mesma lógica da FaturaScreen)
              final List<Map<String, dynamic>> contractInvoices = invoices.where((inv) {
                if (inv is! Map) return false;
                final invContractId = (inv['clienteContrato'] ?? inv['contrato_id'] ?? inv['contrato'] ?? inv['id_contrato'] ?? inv['numero_contrato'])?.toString().trim();
                if (invContractId != currentId) return false;
                
                final status = inv['status']?.toString().toUpperCase() ?? '';
                return status != 'PAGO' && status != 'BAIXADO' && status != 'CANCELADO';
              }).map((e) => Map<String, dynamic>.from(e)).toList();

              if (contractInvoices.isNotEmpty) {
                 // Ordenar por data de vencimento (mais antiga primeiro)
                 contractInvoices.sort((a, b) {
                   DateTime dateA;
                   DateTime dateB;
                   try {
                     dateA = DateTime.parse((a['dataVencimento'] ?? a['data_vencimento'] ?? '').toString());
                   } catch (_) { dateA = DateTime(2099); }
                   try {
                     dateB = DateTime.parse((b['dataVencimento'] ?? b['data_venc_original'] ?? b['data_vencimento'] ?? '').toString());
                   } catch (_) { dateB = DateTime(2099); }
                   return dateA.compareTo(dateB);
                 });

                 final priority = contractInvoices.first;
                 final dueStr = priority['dataVencimento'] ?? priority['data_vencimento'];
                 if (dueStr != null) {
                    final due = DateTime.parse(dueStr);
                    final today = AppConfig.getToday();
                    bool isOverdue = due.isBefore(DateTime(today.year, today.month, today.day));
                    
                    double valor = double.tryParse(priority['valor']?.toString() ?? '0') ?? 0;
                    double valorCorrigido = double.tryParse(priority['valorCorrigido']?.toString() ?? priority['valor_corrigido']?.toString() ?? priority['valor']?.toString() ?? '0') ?? valor;
                    
                    debugPrint('REFRESH: Fatura encontrada para contrato $currentId: Vencimento=$dueStr, Valor=$valor, Corrigido=$valorCorrigido, Atrasada=$isOverdue');
                    _userContract['last_invoice_value'] = valor.toStringAsFixed(2).replaceFirst('.', ',');
                    _userContract['last_invoice_corrected_value'] = valorCorrigido.toStringAsFixed(2).replaceFirst('.', ',');
                    _userContract['last_invoice_interest'] = (valorCorrigido - valor).toStringAsFixed(2).replaceFirst('.', ',');
                    _userContract['last_invoice_due'] = dueStr.split('-').reversed.join('/');
                    _userContract['invoice_status_code'] = isOverdue ? 'overdue' : 'open';
                    
                    // Extração do PIX e Código de Barras
                    if (priority['codigoPix'] != null) {
                      _userContract['pix_code'] = priority['codigoPix'];
                    }
                    if (priority['linhaDigitavel'] != null) {
                      _userContract['barcode'] = priority['linhaDigitavel'];
                    }
                  }
               } else {
                 if (_userContract['is_exempt'] == true) {
                   _userContract['invoice_status_code'] = 'exempt';
                 } else {
                   _userContract['invoice_status_code'] = 'paid';
                 }
              }
           } else {
               if (_userContract['is_exempt'] == true) {
                   _userContract['invoice_status_code'] = 'exempt';
               } else {
                   _userContract['invoice_status_code'] = 'paid';
               }
           }
           notifyListeners();
      }
    } catch (_) {}
  }
}
