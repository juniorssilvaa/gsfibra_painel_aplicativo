class CpeInfo {
  final String? manufacturer;
  /// Número de série do CPE (ex.: integração GenieACS); exibido no lugar de product_class quando existir.
  final String? serial;
  final String? model;
  final String? version;
  final String? ip;
  final dynamic uptime; // Can be int or string
  
  // 2.4GHz
  final String? ssid2g;
  final String? password2g;
  final bool? enabled2g;
  
  // 5GHz
  final String? ssid5g;
  final String? password5g;
  final bool? enabled5g;
  
  // Devices
  final List<dynamic>? connectedDevices;

  CpeInfo({
    this.manufacturer,
    this.serial,
    this.model,
    this.version,
    this.ip,
    this.uptime,
    this.ssid2g,
    this.password2g,
    this.enabled2g,
    this.ssid5g,
    this.password5g,
    this.enabled5g,
    this.connectedDevices,
  });

  factory CpeInfo.fromJson(Map<String, dynamic> json) {
    Map<String, dynamic> info;
    if (json.containsKey('info') && json['info'] is Map) {
      info = json['info'];
    } else {
      // Fallback to root if 'info' key is missing but data seems to be at root
      info = json;
    }

    String? ssid2g = info['wifi_ssid'] ?? info['ssid'];
    String? pass2g = info['wifi_password'] ?? info['password'];
    bool? en2g = info['wifi_enabled'];

    String? ssid5g = info['wifi_ssid_5ghz'] ?? info['ssid_5ghz'];
    String? pass5g = info['wifi_password_5ghz'] ?? info['password_5ghz'];
    bool? en5g = info['wifi_enabled_5ghz'];

    // Priority: interface_info > virtual_wifi > root
    // Check interface_info for enabled interfaces (Real networks)
    if (info.containsKey('interface_info') && info['interface_info'] is Map) {
      final interfaceInfo = info['interface_info'];
      if (interfaceInfo.containsKey('wlan_interfaces') && interfaceInfo['wlan_interfaces'] is List) {
        final List<dynamic> wlanInterfaces = interfaceInfo['wlan_interfaces'];
        for (var v in wlanInterfaces) {
          if (v is Map<String, dynamic> && v['enabled'] == true) {
            final String freq = v['frequency']?.toString() ?? '';
            // Only update if we found an enabled interface
            if (freq.contains('2.4')) {
              ssid2g = v['ssid'];
              pass2g = v['password']; // might be empty
            } else if (freq.contains('5')) {
              ssid5g = v['ssid'];
              pass5g = v['password']; // might be empty
            }
          }
        }
      }
    }

    // Fallback: Try to parse from virtual_wifi list if available (and nothing found yet or explicit fallback needed)
    // Note: User reported virtual_wifi contains disabled/guest networks, so we prioritize interface_info above.
    // However, if interface_info was missing or didn't yield results, we check here.
    if ((ssid2g == null || ssid5g == null) && info.containsKey('virtual_wifi') && info['virtual_wifi'] is List) {
      final List<dynamic> vWifi = info['virtual_wifi'];
      for (var v in vWifi) {
        if (v is Map<String, dynamic>) {
          final String freq = v['frequency']?.toString() ?? '';
          if (freq.contains('2.4')) {
            if (ssid2g == null || ssid2g.isEmpty) ssid2g = v['ssid'];
            if (pass2g == null || pass2g.isEmpty) pass2g = v['password'];
            // Prioritize non-empty values
          } else if (freq.contains('5')) {
             if (ssid5g == null || ssid5g.isEmpty) ssid5g = v['ssid'];
             if (pass5g == null || pass5g.isEmpty) pass5g = v['password'];
          }
        }
      }
    }
    
    final String? serialVal = info['serial']?.toString().trim();
    final bool hasSerial = serialVal != null && serialVal.isNotEmpty;

    return CpeInfo(
      manufacturer: info['manufacturer'],
      serial: hasSerial ? serialVal : null,
      model: (info['product_class'] ?? info['model'])?.toString(),
      version: info['version'],
      ip: info['ip'] ?? info['wan_ip'],
      uptime: info['uptime_raw'] ??
          info['modem_uptime_seconds'] ??
          info['wan_up_time'] ??
          info['sys_up_time'],
      
      ssid2g: ssid2g,
      password2g: pass2g,
      enabled2g: en2g,
      
      ssid5g: ssid5g,
      password5g: pass5g,
      enabled5g: en5g,
      
      connectedDevices: info['connected_devices'] is List 
          ? info['connected_devices'] 
          : (info['lan_devices'] is List ? info['lan_devices'] : []),
    );
  }

  CpeInfo copyWith({
    String? manufacturer,
    String? serial,
    String? model,
    String? version,
    String? ip,
    dynamic uptime,
    String? ssid2g,
    String? password2g,
    bool? enabled2g,
    String? ssid5g,
    String? password5g,
    bool? enabled5g,
    List<dynamic>? connectedDevices,
    bool clearPassword2g = false,
    bool clearPassword5g = false,
  }) {
    return CpeInfo(
      manufacturer: manufacturer ?? this.manufacturer,
      serial: serial ?? this.serial,
      model: model ?? this.model,
      version: version ?? this.version,
      ip: ip ?? this.ip,
      uptime: uptime ?? this.uptime,
      ssid2g: ssid2g ?? this.ssid2g,
      password2g: clearPassword2g ? null : (password2g ?? this.password2g),
      enabled2g: enabled2g ?? this.enabled2g,
      ssid5g: ssid5g ?? this.ssid5g,
      password5g: clearPassword5g ? null : (password5g ?? this.password5g),
      enabled5g: enabled5g ?? this.enabled5g,
      connectedDevices: connectedDevices ?? this.connectedDevices,
    );
  }
}
