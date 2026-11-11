import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../provider.dart';
import '../../models/cpe_info.dart';
import '../../utils/user_facing_error.dart';
import 'wifi_config_screen.dart';
import '../../theme/brand_colors.dart';

class ModemInfoScreen extends StatefulWidget {
  const ModemInfoScreen({super.key});

  @override
  State<ModemInfoScreen> createState() => _ModemInfoScreenState();
}

class _ModemInfoScreenState extends State<ModemInfoScreen> {
  bool _isLoading = true;
  CpeInfo? _cpeInfo;
  String? _error;

  final Color brandColor = BrandColors.primary;
  final Color cardBg = const Color(0xFF111111);

  // State for password visibility
  final Map<String, bool> _showPassword = {};

  @override
  void initState() {
    super.initState();
    _fetchModemInfo();
  }

  Future<void> _fetchModemInfo() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final appProvider = Provider.of<AppProvider>(context, listen: false);
      final sgpService = appProvider.sgpService;

      if (sgpService == null) throw Exception("Serviço não inicializado");

      String contractId = appProvider.userContract['id']?.toString() ?? '';
      
      // Fallback if contractId is empty
      if (contractId.isEmpty) {
        final cpf = appProvider.cpf ?? '';
        final password = appProvider.centralPassword ?? '';
        final contracts = await sgpService.getContratos(cpf, password);
        if (contracts.isNotEmpty) {
           contractId = contracts[0]['id']?.toString() ?? contracts[0]['contrato']?.toString() ?? '';
        }
      }

      if (contractId.isNotEmpty) {
        print('ModemInfoScreen: Using contractId: $contractId');
        final data = await sgpService.getModemInfo(contractId);
        if (data != null) {
          setState(() {
            _cpeInfo = CpeInfo.fromJson(data);
          });
        } else {
          throw Exception("Não foi possível obter informações do modem.");
        }
      } else {
        throw Exception("Contrato não identificado.");
      }
    } catch (e) {
      setState(() {
        _error = UserFacingError.from(e, fallback: UserFacingError.connection);
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: brandColor,
        title: const Text('Meu Modem', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return Center(child: CircularProgressIndicator(color: BrandColors.primary));
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: brandColor.withOpacity(0.1),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.wifi_off, size: 64, color: brandColor),
              ),
              const SizedBox(height: 24),
              const Text(
                'Ops! Algo deu errado',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                _cleanErrorMessage(_error!),
                style: TextStyle(
                  color: Colors.grey[400],
                  fontSize: 16,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 32),
              SizedBox(
                width: double.infinity,
                height: 54,
                child: ElevatedButton.icon(
                  onPressed: _fetchModemInfo,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: brandColor,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                    elevation: 8,
                    shadowColor: brandColor.withOpacity(0.4),
                  ),
                  icon: const Icon(Icons.refresh, color: Colors.white),
                  label: const Text(
                    'Tentar Novamente',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (_cpeInfo == null) {
      return const Center(child: Text('Nenhuma informação disponível.', style: TextStyle(color: Colors.white)));
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Header
          Center(
            child: Column(
              children: [
                Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    color: Colors.black,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: brandColor.withOpacity(0.5),
                        blurRadius: 20,
                        spreadRadius: 2,
                      ),
                    ],
                    border: Border.all(color: brandColor.withOpacity(0.3), width: 1),
                  ),
                  child: Icon(Icons.router, color: brandColor, size: 50),
                ),
                const SizedBox(height: 16),
                const Text('Modem', style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text(_cpeInfo?.manufacturer ?? 'Fabricante Desconhecido', style: const TextStyle(color: Colors.white70, fontSize: 16)),
                Text(
                  _cpeInfo?.serial ?? _cpeInfo?.model ?? '—',
                  style: const TextStyle(color: Colors.grey, fontSize: 16),
                ),
              ],
            ),
          ),
          const SizedBox(height: 32),

          // Wi-Fi Section
          _buildSectionCard(
            title: 'Wi-Fi',
            icon: Icons.wifi,
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => WifiConfigScreen(initialInfo: _cpeInfo),
                ),
              ).then((result) {
                if (result is CpeInfo) {
                  setState(() => _cpeInfo = result);
                } else {
                  _fetchModemInfo();
                }
              });
            },
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (_cpeInfo?.ssid2g != null) ...[
                  _buildWifiRow('2.4 GHz', _cpeInfo!.ssid2g!, _cpeInfo?.password2g, '2g'),
                  const SizedBox(height: 12),
                ],
                if (_cpeInfo?.ssid5g != null)
                  _buildWifiRow('5 GHz', _cpeInfo!.ssid5g!, _cpeInfo?.password5g, '5g'),
              ],
            ),
            trailing: Icon(Icons.edit, color: brandColor, size: 20),
          ),
          const SizedBox(height: 16),

          // Internet Section
          _buildSectionCard(
            title: 'Internet',
            icon: Icons.language,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildInfoRow('IP: ${_cpeInfo?.ip ?? '-'}'),
                const SizedBox(height: 8),
                _buildInfoRow('Tempo Ligado: ${_formatUptime(_cpeInfo?.uptime)}'),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  // Devices section removed as requested
  /*
  void _showConnectedDevices(BuildContext context) {
  ...
  }
  */

  Widget _buildWifiRow(String label, String ssid, String? password, String key) {
    final bool isVisible = _showPassword[key] ?? false;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: brandColor, fontSize: 12, fontWeight: FontWeight.bold)),
        const SizedBox(height: 2),
        Row(
          children: [
             const Icon(Icons.wifi, color: Colors.white70, size: 16),
             const SizedBox(width: 8),
             Text(ssid, style: const TextStyle(color: Colors.white, fontSize: 14)),
          ],
        ),
        if (password != null && password.isNotEmpty) ...[
          const SizedBox(height: 2),
           Row(
            children: [
               const Icon(Icons.lock, color: Colors.white70, size: 16),
               const SizedBox(width: 8),
               Text(
                 isVisible ? password : '•' * 8, // Fixed length for better UI alignment
                 style: const TextStyle(color: Colors.white70, fontSize: 12),
               ),
               const SizedBox(width: 8),
               InkWell(
                 onTap: () {
                   setState(() {
                     _showPassword[key] = !isVisible;
                   });
                 },
                 child: Icon(
                   isVisible ? Icons.visibility : Icons.visibility_off,
                   color: Colors.white54,
                   size: 18,
                 ),
               ),
            ],
          ),
        ]
      ],
    );
  }

  Widget _buildSectionCard({
    required String title,
    required IconData icon,
    required Widget child,
    Widget? trailing,
    VoidCallback? onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: cardBg,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: brandColor, size: 24),
                const SizedBox(width: 12),
                Text(title, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                if (trailing != null) ...[
                  const Spacer(),
                  trailing,
                ],
              ],
            ),
            const Divider(color: Colors.white10, height: 32),
            child,
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String text) {
    return Text(
      text,
      style: const TextStyle(color: Colors.grey, fontSize: 14),
    );
  }

  String _formatUptime(dynamic uptime) {
    if (uptime == null) return '-';
    // If uptime is seconds (int)
    if (uptime is int) {
      final duration = Duration(seconds: uptime);
      final days = duration.inDays;
      final hours = duration.inHours % 24;
      if (days > 0) return '$days dias, $hours horas';
      return '$hours horas';
    }
    // If string
    return uptime.toString();
  }

  String _cleanErrorMessage(String error) {
    String clean = error;
    // Remove technical prefixes
    if (clean.startsWith('Exception: ')) {
      clean = clean.substring(11);
    }
    
    // User friendly messages
    if (clean.contains('FALHA DE CONEXÃO') || clean.contains('Connection refused') || clean.contains('SocketException')) {
      return 'Não foi possível conectar ao servidor. Verifique sua internet e tente novamente.';
    }
    if (clean.contains('404') || clean.contains('não encontrado')) {
      return 'Não conseguimos localizar as informações do seu modem neste momento.';
    }
    
    return clean;
  }
}
