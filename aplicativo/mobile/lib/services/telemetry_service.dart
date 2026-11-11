import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:network_info_plus/network_info_plus.dart';
import 'package:wifi_iot/wifi_iot.dart';
import 'package:permission_handler/permission_handler.dart';

class TelemetryService {
  final _connectivity = Connectivity();
  final _networkInfo = NetworkInfo();

  Future<Map<String, dynamic>> collectTelemetry() async {
    String? ssid;
    String? ip;
    String? bssid;
    int? signalStrength;
    
    var status = await Permission.locationWhenInUse.status;
    if (!status.isGranted) {
      await Permission.locationWhenInUse.request();
    }
    
    try {
      ssid = await _networkInfo.getWifiName();
      ip = await _networkInfo.getWifiIP();
      bssid = await _networkInfo.getWifiBSSID();
      signalStrength = await WiFiForIoTPlugin.getCurrentSignalStrength();
    } catch (e) {
      print('Erro ao coletar telemetria WiFi: $e');
    }
    
    final connectivityResult = await _connectivity.checkConnectivity();
    return {
      'ssid': ssid,
      'ip': ip,
      'bssid': bssid,
      'signal_strength': signalStrength,
      'connectivity': connectivityResult.toString(),
      'timestamp': DateTime.now().toIso8601String(),
    };
  }
}
