import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:device_info_plus/device_info_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import '../config.dart';

void Function(Map<String, dynamic> data)? onPushNotificationTap;

void _handleNotificationData(Map<String, dynamic> data) {
  onPushNotificationTap?.call(data);
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint("Handling a background message: ${message.messageId}");
}

class PushService {
  late final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _flutterLocalNotificationsPlugin = FlutterLocalNotificationsPlugin();
  
  String? _token;
  bool _isInitialized = false;
  bool suppressSupportChatAlerts = false;
  void Function(String token)? onTokenReady;
  
  final _messageStreamController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get messageStream => _messageStreamController.stream;

  Future<String?> _ensureFcmToken({int attempts = 5}) async {
    if (_token != null && _token!.isNotEmpty) return _token;

    if (Platform.isIOS) {
      try {
        await _firebaseMessaging.setAutoInitEnabled(true).timeout(const Duration(seconds: 2));
      } catch (e) {
        debugPrint('setAutoInitEnabled falhou/timeout: $e');
      }
      var apnsOk = false;
      for (var i = 0; i < attempts; i++) {
        try {
          final apns = await _firebaseMessaging
              .getAPNSToken()
              .timeout(const Duration(seconds: 2));
          if (apns != null && apns.isNotEmpty) {
            debugPrint('APNs token obtido (tentativa ${i + 1})');
            apnsOk = true;
            break;
          }
        } catch (e) {
          debugPrint('APNs ainda indisponível (tentativa ${i + 1}): $e');
        }
        await Future.delayed(const Duration(milliseconds: 300));
      }
      if (!apnsOk) {
        // Sem entitlement/profile Push o iOS nunca entrega APNs — não trava o app.
        debugPrint('APNs ausente após $attempts tentativas; seguindo sem FCM');
        return null;
      }
    }

    for (var i = 0; i < attempts; i++) {
      try {
        final token = await _firebaseMessaging
            .getToken()
            .timeout(const Duration(seconds: 3));
        if (token != null && token.isNotEmpty) {
          _token = token;
          debugPrint('FCM Token: $_token');
          return _token;
        }
      } catch (e) {
        debugPrint('getToken tentativa ${i + 1}: $e');
      }
      await Future.delayed(const Duration(milliseconds: 300));
    }

    debugPrint('FCM Token nulo após $attempts tentativas (iOS precisa do APNs)');
    return null;
  }

  Future<void> initialize() async {
    if (_isInitialized) {
      if (_token == null || _token!.isEmpty) {
        try {
          _token = await _ensureFcmToken().timeout(const Duration(seconds: 12));
          if (_token != null && _token!.isNotEmpty) {
            onTokenReady?.call(_token!);
          }
        } catch (e) {
          debugPrint('Re-fetch FCM timeout/erro: $e');
        }
      }
      return;
    }

    try {
      NotificationSettings settings = await _firebaseMessaging
          .requestPermission(
            alert: true,
            badge: true,
            sound: true,
            announcement: true,
            carPlay: false,
            criticalAlert: false,
            provisional: false,
          )
          .timeout(const Duration(seconds: 5));

      final allowed = settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional;

      if (allowed) {
        debugPrint('Permissão de notificação concedida (${settings.authorizationStatus})');

        if (Platform.isIOS) {
          await _firebaseMessaging
              .setForegroundNotificationPresentationOptions(
                alert: true,
                badge: true,
                sound: true,
              )
              .timeout(const Duration(seconds: 2));
        }

        await _setupLocalNotifications().timeout(const Duration(seconds: 3));

        _token = await _ensureFcmToken().timeout(const Duration(seconds: 12));

        _firebaseMessaging.onTokenRefresh.listen((newToken) {
          _token = newToken;
          debugPrint('FCM Token atualizado: $_token');
          if (newToken.isNotEmpty) {
            onTokenReady?.call(newToken);
          }
        });

        FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

        FirebaseMessaging.onMessage.listen((RemoteMessage message) {
          debugPrint('Mensagem recebida em primeiro plano: ${message.notification?.title}');
          final type = (message.data['type'] ?? '').toString();
          if (type == 'support_chat' && suppressSupportChatAlerts) {
            debugPrint('Push support_chat ignorado (cliente no chat)');
            return;
          }

          _messageStreamController.add({
            'id': message.messageId ?? DateTime.now().millisecondsSinceEpoch.toString(),
            'title': message.notification?.title ?? 'Notificação',
            'message': message.notification?.body ?? '',
            'created_at': DateTime.now().toIso8601String(),
            'type': type.isNotEmpty ? type : 'info',
            'read': false,
          });

          _showLocalNotification(message);
        });

        FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
          _handleNotificationData(Map<String, dynamic>.from(message.data));
        });

        try {
          final initial = await FirebaseMessaging.instance
              .getInitialMessage()
              .timeout(const Duration(seconds: 2));
          if (initial != null) {
            _handleNotificationData(Map<String, dynamic>.from(initial.data));
          }
        } catch (e) {
          debugPrint('getInitialMessage timeout/erro: $e');
        }

        _isInitialized = true;
        if (_token != null && _token!.isNotEmpty) {
          onTokenReady?.call(_token!);
        }
      } else {
        debugPrint('Permissão de notificação negada ou não determinada: ${settings.authorizationStatus}');
        _isInitialized = true;
      }
    } catch (e) {
      debugPrint('Erro ao inicializar PushService: $e');
      _isInitialized = true;
    }
  }

  Future<void> _setupLocalNotifications() async {
    const AndroidInitializationSettings initializationSettingsAndroid =
        AndroidInitializationSettings('ic_notification');

    final DarwinInitializationSettings initializationSettingsIOS =
        DarwinInitializationSettings(
            requestAlertPermission: false,
            requestBadgePermission: false,
            requestSoundPermission: false);

    final InitializationSettings initializationSettings = InitializationSettings(
      android: initializationSettingsAndroid,
      iOS: initializationSettingsIOS,
    );

    await _flutterLocalNotificationsPlugin.initialize(
      initializationSettings,
      onDidReceiveNotificationResponse: (NotificationResponse notificationResponse) {
        debugPrint('Notificação clicada: ${notificationResponse.payload}');
        final payload = notificationResponse.payload;
        if (payload != null && payload.isNotEmpty) {
          try {
            final data = jsonDecode(payload);
            if (data is Map) {
              _handleNotificationData(Map<String, dynamic>.from(data));
            }
          } catch (_) {}
        }
      },
    );

    // Create channel for Android
    if (Platform.isAndroid) {
      const AndroidNotificationChannel channel = AndroidNotificationChannel(
        'high_importance_channel', // id
        'High Importance Notifications', // title
        description: 'This channel is used for important notifications.', // description
        importance: Importance.max,
      );

      await _flutterLocalNotificationsPlugin
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.createNotificationChannel(channel);
    }
  }

  Future<void> cancelAllLocalNotifications() async {
    try {
      await _flutterLocalNotificationsPlugin.cancelAll();
    } catch (e) {
      debugPrint('Erro ao cancelar notificações locais: $e');
    }
  }

  Future<void> _showLocalNotification(RemoteMessage message) async {
    try {
      final notification = message.notification;
      final data = message.data;
      final title = notification?.title
          ?? (data['title']?.toString().isNotEmpty == true ? data['title'].toString() : null)
          ?? 'Suporte';
      final body = notification?.body
          ?? (data['body']?.toString().isNotEmpty == true ? data['body'].toString() : null)
          ?? (data['message']?.toString().isNotEmpty == true ? data['message'].toString() : null)
          ?? 'Nova mensagem do atendimento';

      debugPrint('Exibindo notificação local: $title');
      await _flutterLocalNotificationsPlugin.show(
        message.messageId?.hashCode ?? DateTime.now().millisecondsSinceEpoch.remainder(100000),
        title,
        body,
        const NotificationDetails(
          android: AndroidNotificationDetails(
            'high_importance_channel',
            'High Importance Notifications',
            channelDescription: 'This channel is used for important notifications.',
            icon: 'ic_notification',
            importance: Importance.max,
            priority: Priority.high,
          ),
          iOS: DarwinNotificationDetails(
            presentAlert: true,
            presentBadge: true,
            presentSound: true,
          ),
        ),
        payload: jsonEncode(data),
      );
    } catch (e) {
      debugPrint('Erro ao exibir notificação local: $e');
    }
  }

  String? get token => _token;

  Future<Map<String, dynamic>> _collectDeviceInfo() async {
    final deviceInfo = DeviceInfoPlugin();
    if (Platform.isAndroid) {
      final android = await deviceInfo.androidInfo;
      return {
        'platform': 'android',
        'model': android.model,
        'model_name': android.model,
        'manufacturer': android.manufacturer,
        'brand': android.brand,
        'device': android.device,
        'product': android.product,
        'hardware': android.hardware,
        'android_version': android.version.release,
        'device_version': android.version.release,
        'model_version': android.device, // best-effort: codename/sku-like
        'sdk': android.version.sdkInt,
        'base_os': android.version.baseOS,
        'codename': android.version.codename,
        'incremental': android.version.incremental,
        'security_patch': android.version.securityPatch,
        'fingerprint': android.fingerprint,
        'is_emulator': !(android.isPhysicalDevice ?? true),
        // Campos redundantes para compatibilidade com backend
        'os_version': 'Android ${android.version.release} (SDK ${android.version.sdkInt})',
        'device_model': android.model,
        'os': 'android',
      };
    } else if (Platform.isIOS) {
      final ios = await deviceInfo.iosInfo;
      return {
        'platform': 'ios',
        'model': ios.utsname.machine,
        'model_name': ios.utsname.machine,
        'manufacturer': 'Apple',
        'brand': 'Apple',
        'system_name': 'iOS',
        'system_version': ios.systemVersion,
        'device_version': ios.systemVersion,
        'model_version': ios.utsname.machine,
        'is_emulator': !(ios.isPhysicalDevice ?? true),
        'os_version': 'iOS ${ios.systemVersion}',
        'device_model': ios.utsname.machine,
        'os': 'ios',
      };
    }
    return {
      'platform': Platform.operatingSystem,
      'os_version': Platform.operatingSystemVersion,
    };
  }

  Future<Map<String, dynamic>> _collectPermissions() async {
    final Map<String, dynamic> perms = {};
    Future<String> statusOf(Permission p) async {
      final s = await p.status;
      if (s.isGranted) return 'granted';
      if (s.isDenied) return 'denied';
      if (s.isPermanentlyDenied) return 'permanently_denied';
      if (s.isRestricted) return 'restricted';
      if (s.isLimited) return 'limited';
      return s.name;
    }
    try {
      perms['notification'] = await statusOf(Permission.notification);
    } catch (_) {}
    try {
      perms['location'] = await statusOf(Permission.location);
      perms['location_when_in_use'] = await statusOf(Permission.locationWhenInUse);
    } catch (_) {}
    try {
      perms['storage'] = await statusOf(Permission.storage);
    } catch (_) {}
    return perms;
  }

  Future<bool> registerDevice({String? cpf, String? contractId, String? name}) async {
    if (_token == null || _token!.isEmpty) {
      _token = await _ensureFcmToken();
      if (_token == null || _token!.isEmpty) {
        debugPrint('Não é possível registrar dispositivo: Token FCM nulo (iOS sem APNs?)');
        return false;
      }
    }

    try {
      final device = await _collectDeviceInfo();
      final permissions = await _collectPermissions();

      final url = AppConfig.apiUrl('devices/register/');
      
      final body = {
        'provider_token': AppConfig.apiToken,
        'push_token': _token,
        'fcm_token': _token,
        'platform': Platform.isAndroid ? 'android' : 'ios',
        'cpf': (cpf ?? '').replaceAll(RegExp(r'[^\d]'), ''),
        'contract_id': contractId,
        'name': (name ?? '').trim(),
        // Campos diretos (antigos)
        'model': device['model'],
        'manufacturer': device['manufacturer'],
        'os_version': device['os_version'],
        'device_version': device['device_version'],
        // Campos estendidos para compatibilidade
        'os': device['os'],
        'android_version': device['android_version'],
        'sdk': device['sdk'],
        'brand': device['brand'],
        'device_model': device['device_model'] ?? device['model'],
        'model_name': device['model_name'] ?? device['model'],
        'model_version': device['model_version'] ?? device['device'],
        'fingerprint': device['fingerprint'],
        'base_os': device['base_os'],
        'codename': device['codename'],
        'incremental': device['incremental'],
        // Sinônimos em PT/variações comuns para compatibilidade com o backend
        'sistema_operacional': device['os'] ?? 'android',
        'versao_sistema': device['os_version'],
        'versao': device['android_version'] ?? device['os_version'],
        'versao_android': device['android_version'],
        'sdk_version': device['sdk'],
        'android_sdk': device['sdk'],
        'modelo': device['model'],
        'modelo_dispositivo': device['device_model'] ?? device['model'],
        'versao_dispositivo': device['device_version'],
        'fabricante': device['manufacturer'],
        'marca': device['brand'] ?? device['manufacturer'],
        // Estruturas detalhadas
        'device_info': device,
        'permissions': permissions,
      };

      debugPrint('Registrando dispositivo no backend: $url');
      debugPrint('Payload: $body');

      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );

      if (response.statusCode == 200 || response.statusCode == 201) {
        debugPrint('Dispositivo registrado com sucesso!');
        return true;
      } else {
        debugPrint('Falha ao registrar dispositivo: ${response.statusCode} - ${response.body}');
        return false;
      }
    } catch (e) {
      debugPrint('Erro ao registrar dispositivo no backend: $e');
      return false;
    }
  }
}
