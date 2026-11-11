import 'package:flutter/services.dart';

/// Sensor de proximidade nativo: apaga a tela perto do rosto e avisa
/// o Dart para tocar o áudio pelo alto-falante de ouvido.
class ProximityService {
  static const MethodChannel _channel = MethodChannel('gsfibra/proximity');
  static void Function(bool near)? _listener;

  static Future<bool> enable(void Function(bool near) onChange) async {
    _listener = onChange;
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onProximity') {
        _listener?.call(call.arguments == true);
      }
    });
    try {
      return await _channel.invokeMethod<bool>('enable') ?? false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  static Future<void> disable() async {
    _listener = null;
    try {
      await _channel.invokeMethod('disable');
    } on PlatformException {
      // sensor indisponível
    } on MissingPluginException {
      // plataforma sem sensor
    }
  }
}
