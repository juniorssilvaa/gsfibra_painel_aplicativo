import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../provider.dart';
import '../../utils/user_facing_error.dart';
import '../../theme/brand_colors.dart';

class ConnectedDevicesScreen extends StatefulWidget {
  const ConnectedDevicesScreen({super.key});

  @override
  State<ConnectedDevicesScreen> createState() => _ConnectedDevicesScreenState();
}

class _ConnectedDevicesScreenState extends State<ConnectedDevicesScreen> {
  bool _isLoading = true;
  String? _error;

  final Color brandColor = BrandColors.primary;

  @override
  void initState() {
    super.initState();
    _fetchConnectedDevices();
  }

  Future<void> _fetchConnectedDevices() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final appProvider = Provider.of<AppProvider>(context, listen: false);
      final sgpService = appProvider.sgpService;

      if (sgpService == null) throw Exception("Serviço não inicializado");

      final contractId = appProvider.userContract['id']?.toString() ?? '';
      
      if (contractId.isNotEmpty) {
        final data = await sgpService.getConnectedDevices(contractId);
        if (data != null && data['devices'] != null) {
          setState(() {
            _devices = List<Map<String, dynamic>>.from(data['devices']);
          });
        } else {
          throw Exception("Não foi possível obter a lista de dispositivos.");
        }
      } else {
        throw Exception("Contrato não identificado.");
      }
    } catch (e) {
      setState(() {
        _error = UserFacingError.from(e, fallback: 'Não foi possível carregar os dispositivos agora.');
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  List<Map<String, dynamic>> _devices = [];

  IconData _getDeviceIcon(String hostname) {
    final h = hostname.toLowerCase();
    if (h.contains('iphone') || h.contains('android') || h.contains('phone') || h.contains('celular') || h.contains('mobile')) return Icons.smartphone;
    if (h.contains('tv') || h.contains('televisao') || h.contains('samsung') || h.contains('lg')) return Icons.tv;
    if (h.contains('pc') || h.contains('computador') || h.contains('desktop') || h.contains('notebook') || h.contains('laptop')) return Icons.computer;
    if (h.contains('ps4') || h.contains('ps5') || h.contains('xbox') || h.contains('nintendo') || h.contains('console')) return Icons.videogame_asset;
    return Icons.devices;
  }

  String _formatLeaseTime(dynamic seconds) {
    if (seconds == null || seconds == 0) return 'Indeterminado';
    try {
      final s = int.parse(seconds.toString());
      if (s > 3600) {
        return '${(s / 3600).toStringAsFixed(1)} horas restando';
      } else if (s > 60) {
        return '${(s / 60).toStringAsFixed(0)} minutos restando';
      }
      return '$s segundos restando';
    } catch (_) {
      return 'N/A';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0A),
      appBar: AppBar(
        backgroundColor: brandColor,
        elevation: 0,
        title: const Text('Dispositivos Conectados', 
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18)),
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(color: BrandColors.primary),
            const SizedBox(height: 20),
            Text('Escaneando sua rede...', 
              style: TextStyle(color: Colors.grey[400], fontSize: 14)),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.wifi_off_rounded, color: Colors.grey[800], size: 64),
              const SizedBox(height: 16),
              const Text('Ops! O modem não respondeu', 
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text(_error!, 
                style: TextStyle(color: Colors.grey[500], fontSize: 14), 
                textAlign: TextAlign.center),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _fetchConnectedDevices,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: brandColor,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text('Tentar Novamente', 
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (_devices.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.router_outlined, color: Colors.grey[800], size: 64),
            const SizedBox(height: 16),
            const Text('Nenhum dispositivo encontrado', 
              style: TextStyle(color: Colors.white, fontSize: 16)),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _fetchConnectedDevices,
      color: brandColor,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        itemCount: _devices.length,
        itemBuilder: (context, index) {
          final device = _devices[index];
          final hostname = device['hostname'] ?? 'Dispositivo s/ nome';
          final ip = device['ip'] ?? '-';
          final mac = device['mac'] ?? '-';
          final active = device['active'] == true;
          final lease = device['lease_time'];
          
          return Container(
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  const Color(0xFF1A1A1A),
                  const Color(0xFF121212),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.white.withOpacity(0.05)),
            ),
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              leading: Container(
                width: 50,
                height: 50,
                decoration: BoxDecoration(
                  color: active ? brandColor.withOpacity(0.1) : Colors.white.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(_getDeviceIcon(hostname), 
                  color: active ? brandColor : Colors.grey[600], size: 28),
              ),
              title: Row(
                children: [
                  Expanded(
                    child: Text(
                      hostname,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (active)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.green.withOpacity(0.2),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text('ATIVO', 
                        style: TextStyle(color: Colors.green, fontSize: 8, fontWeight: FontWeight.bold)),
                    ),
                ],
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Icon(Icons.language, color: Colors.grey[600], size: 12),
                      const SizedBox(width: 4),
                      Text(ip, style: TextStyle(color: Colors.grey[400], fontSize: 13)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(Icons.fingerprint, color: Colors.grey[600], size: 12),
                      const SizedBox(width: 4),
                      Text(mac, style: TextStyle(color: Colors.grey[600], fontSize: 11)),
                    ],
                  ),
                  if (active && lease != null && lease != 0) ...[
                    const SizedBox(height: 8),
                    Text(_formatLeaseTime(lease), 
                      style: TextStyle(color: BrandColors.primary, fontSize: 11, fontWeight: FontWeight.w500)),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
