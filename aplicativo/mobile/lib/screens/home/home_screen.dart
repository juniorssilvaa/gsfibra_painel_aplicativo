import 'package:flutter/services.dart';
import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:network_info_plus/network_info_plus.dart' as network_plus;
import 'package:permission_handler/permission_handler.dart';
import '../../services.dart';
import '../../services/sgp_service.dart';
import '../../main.dart';
import '../../provider.dart';
import '../../models/cpe_info.dart';
import '../../utils/user_facing_error.dart';
import 'barcode_painter.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../config.dart';
import '../../widgets/brand_logo.dart';
import '../../theme/app_branding.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  String _ssid = 'Carregando...';
  String _wanIp = 'Carregando...';
  String _modemUptime = '-';
  String _modemConnection = 'unknown';
  String _modemConnectionLabel = 'Verificando...';
  bool _modemUptimeExpanded = false;
  bool _userCardExpanded = false;
  bool _hideSuspensionGuide = false;
  StreamSubscription<ConnectivityResult>? _connectivitySubscription;
  Timer? _notificationsPollTimer;

  Color get brandColor => Theme.of(context).colorScheme.primary;
  // Colors removed here, defined in build

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _initWifiListener();
      final provider = context.read<AppProvider>();

      unawaited(provider.refreshData());
      provider.fetchAppConfig();
      unawaited(_fetchModemNetworkInfo());
      // Inicializar serviço de Push Notifications e garantir registro do token
      provider.initPushService();
      _notificationsPollTimer?.cancel();
      _notificationsPollTimer = Timer.periodic(const Duration(seconds: 15), (_) {
        if (!mounted) return;
        context.read<AppProvider>().fetchNotifications();
      });
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Quando o app volta do background para o foreground, forçamos um refresh
      debugPrint('App retomado: Forçando atualização de dados...');
      final provider = context.read<AppProvider>();
      provider.fetchAppConfig();
      provider.refreshData();
      provider.initPushService();
      _fetchModemNetworkInfo();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivitySubscription?.cancel();
    _notificationsPollTimer?.cancel();
    super.dispose();
  }

  Future<void> _initWifiListener() async {
    // Check inicial
    try {
      final result = await Connectivity().checkConnectivity();
      _updateWifiInfo(result);

      // Solicita permissão de localização se não tiver
      // IMPORTANTE: Necessário para ler SSID no Android 8+
      if (await Permission.locationWhenInUse.request().isGranted) {
        // Força atualização após permissão
        final info = network_plus.NetworkInfo();
        final ssid = await info.getWifiName();
        if (ssid != null && mounted) {
          setState(() => _ssid = ssid.replaceAll('"', ''));
        }
      }
    } catch (e) {
      debugPrint('Erro check inicial connectivity: $e');
    }

    // Listener
    _connectivitySubscription = Connectivity().onConnectivityChanged.listen(_updateWifiInfo);
  }

  Future<void> _updateWifiInfo(ConnectivityResult result) async {
    if (result == ConnectivityResult.wifi) {
      String? ssid;
      try {
        var status = await Permission.locationWhenInUse.status;
        if (!status.isGranted) {
          await Permission.locationWhenInUse.request();
        }

        final info = network_plus.NetworkInfo();
        ssid = await info.getWifiName();
        if (ssid != null) {
          ssid = ssid.replaceAll('"', '');
        }
      } catch (e) {
        debugPrint('Erro ao obter info WiFi: $e');
      }

      if (mounted) {
        setState(() {
          _ssid = ssid ?? 'Wi-Fi Conectado';
        });
      }
    } else if (mounted) {
      setState(() => _ssid = 'Wi-Fi desconectado');
    }
  }

  Future<String?> _resolveContractId(AppProvider appProvider, dynamic sgpService) async {
    String contractId = appProvider.userContract['id']?.toString() ?? '';
    if (contractId.isNotEmpty) return contractId;

    final cpf = appProvider.cpf ?? '';
    final password = appProvider.centralPassword ?? '';
    if (cpf.isEmpty || password.isEmpty) return null;

    final contracts = await sgpService.getContratos(cpf, password);
    if (contracts.isEmpty) return null;
    return contracts[0]['id']?.toString() ?? contracts[0]['contrato']?.toString();
  }

  Future<void> _fetchModemNetworkInfo() async {
    try {
      if (!mounted) return;
      final appProvider = context.read<AppProvider>();
      final sgpService = appProvider.sgpService;
      if (sgpService == null) return;

      final contractId = await _resolveContractId(appProvider, sgpService);
      if (contractId == null || contractId.isEmpty) return;

      if (mounted) {
        setState(() {
          _modemConnectionLabel = 'Verificando...';
          if (_wanIp == '-') _wanIp = 'Carregando...';
        });
      }

      final results = await Future.wait([
        sgpService.verifyAccess(contractId),
        sgpService.getModemInfo(contractId),
      ]);

      if (!mounted) return;

      final accessStatus = SGPService.parseAccessStatus(results[0]);
      final data = results[1] as Map<String, dynamic>?;
      if (data == null) {
        setState(() {
          _modemConnection = accessStatus['connection'] ?? 'unknown';
          _modemConnectionLabel = accessStatus['label'] ?? 'Indisponível';
          if (_wanIp == 'Carregando...') _wanIp = '-';
        });
        return;
      }

      final cpe = CpeInfo.fromJson(data);
      final wanIp = (cpe.ip ?? data['wan_ip'] ?? data['ip'] ?? '').toString().trim();
      final uptimeSource = data['uptime_raw'] ?? data['modem_uptime_seconds'] ?? cpe.uptime;
      final acsStatus = (data['status'] ?? '').toString().toLowerCase();
      var connection = accessStatus['connection'] ?? 'unknown';
      var label = accessStatus['label'] ?? 'Indisponível';
      if (connection == 'unknown' && acsStatus.contains('online')) {
        connection = 'online';
        label = 'Online';
      }

      setState(() {
        _modemConnection = connection;
        _modemConnectionLabel = label;
        _wanIp = wanIp.isEmpty || wanIp == '0.0.0.0' ? '-' : wanIp;
        _modemUptime = _formatModemUptime(uptimeSource);
      });
    } catch (e) {
      debugPrint('Erro ao buscar IP/uptime do modem: $e');
      if (mounted && _wanIp == 'Carregando...') {
        setState(() => _wanIp = '-');
      }
    }
  }

  int? _parseUptimeSeconds(dynamic uptime) {
    if (uptime == null) return null;
    if (uptime is int) return uptime;
    if (uptime is num) return uptime.toInt();

    final raw = uptime.toString().trim();
    if (raw.isEmpty || raw.toUpperCase() == 'N/A') return null;

    final asInt = int.tryParse(raw);
    if (asInt != null) return asInt;

    final secMatch = RegExp(r'^(\d+)\s*s$', caseSensitive: false).firstMatch(raw);
    if (secMatch != null) return int.parse(secMatch.group(1)!);

    final dhms = RegExp(
      r'(\d+)\s*d(?:\s*(\d+)\s*h)?(?:\s*(\d+)\s*m)?',
      caseSensitive: false,
    ).firstMatch(raw);
    if (dhms != null) {
      final days = int.parse(dhms.group(1)!);
      final hours = dhms.group(2) != null ? int.parse(dhms.group(2)!) : 0;
      final minutes = dhms.group(3) != null ? int.parse(dhms.group(3)!) : 0;
      return days * 86400 + hours * 3600 + minutes * 60;
    }

    final diasHoras = RegExp(
      r'(\d+)\s*dias?(?:,\s*(\d+)\s*horas?)?(?:,\s*(\d+)\s*min(?:utos?)?)?',
      caseSensitive: false,
    ).firstMatch(raw);
    if (diasHoras != null) {
      final days = int.parse(diasHoras.group(1)!);
      final hours = diasHoras.group(2) != null ? int.parse(diasHoras.group(2)!) : 0;
      final minutes = diasHoras.group(3) != null ? int.parse(diasHoras.group(3)!) : 0;
      return days * 86400 + hours * 3600 + minutes * 60;
    }

    final horasMin = RegExp(
      r'(\d+)\s*horas?(?:,\s*(\d+)\s*min(?:utos?)?)?',
      caseSensitive: false,
    ).firstMatch(raw);
    if (horasMin != null) {
      final hours = int.parse(horasMin.group(1)!);
      final minutes = horasMin.group(2) != null ? int.parse(horasMin.group(2)!) : 0;
      return hours * 3600 + minutes * 60;
    }

    final onlyMin = RegExp(r'^(\d+)\s*min(?:utos?)?$', caseSensitive: false).firstMatch(raw);
    if (onlyMin != null) return int.parse(onlyMin.group(1)!) * 60;

    return null;
  }

  String _formatModemUptime(dynamic uptime) {
    final seconds = _parseUptimeSeconds(uptime);
    if (seconds == null || seconds <= 0) return 'Indisponível no momento';

    final days = seconds ~/ 86400;
    final hours = (seconds % 86400) ~/ 3600;
    final minutes = (seconds % 3600) ~/ 60;

    final parts = <String>[];
    if (days > 0) parts.add('$days ${days == 1 ? 'dia' : 'dias'}');
    if (hours > 0) parts.add('$hours ${hours == 1 ? 'hora' : 'horas'}');
    if (minutes > 0 || parts.isEmpty) {
      parts.add('$minutes ${minutes == 1 ? 'minuto' : 'minutos'}');
    }

    if (parts.length == 1) return parts.first;
    if (parts.length == 2) return '${parts[0]} e ${parts[1]}';
    return '${parts.sublist(0, parts.length - 1).join(', ')} e ${parts.last}';
  }

  @override
  Widget build(BuildContext context) {
    final cardBg = AppBranding.cardBackground(context);
    final isDark = ThemeData.estimateBrightnessForColor(cardBg) == Brightness.dark;
    final scaffoldBg = AppBranding.screenBackground(context);
    final onBg = AppBranding.onColor(scaffoldBg);
    final textColor = isDark ? Colors.white : Colors.black;
    final subTextColor = isDark ? Colors.grey : Colors.grey[700]!;
    final provider = Provider.of<AppProvider>(context);
    final status = provider.userContract['status'] ?? 'ATIVO';
    final statusString = status.toString().toUpperCase();
    final isSuspended = statusString.contains('SUSPENSO') || statusString.contains('BLOQUEADO');

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: onBg == Colors.white ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: scaffoldBg,
        extendBody: true, // Importante para o conteúdo passar por trás da barra
        body: Stack(
          children: [
            Positioned.fill(
                child: SafeArea(
              bottom: false, // Permite que o conteúdo desça até o fundo
              child: Column(
                children: [
                  // Custom App Bar
                  _buildAppBar(onBg),

                  Expanded(
                    child: RefreshIndicator(
                      onRefresh: () async {
                        try {
                          await Provider.of<AppProvider>(context, listen: false).refreshData();
                          await _fetchModemNetworkInfo();
                          final result = await Connectivity().checkConnectivity();
                          await _updateWifiInfo(result);
                        } catch (e) {
                          if (mounted) {
                            showTopSnackBar(context, 
                              SnackBar(content: Text(UserFacingError.from(e, fallback: UserFacingError.connection))),
                            );
                          }
                        }
                      },
                      color: brandColor,
                      backgroundColor: cardBg,
                      child: SingleChildScrollView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Column(
                          children: [
                            const SizedBox(height: 16),
                            _buildUserCard(cardBg, textColor, subTextColor, isDark),
                            const SizedBox(height: 16),
                            _buildInvoiceCard(cardBg, textColor, subTextColor, isDark),
                            const SizedBox(height: 16),
                            _buildWifiCard(cardBg, textColor, subTextColor),
                            const SizedBox(height: 16),
                            _buildAIAssistantCard(cardBg, textColor, subTextColor),
                            const SizedBox(height: 24),
                            _buildQuickAccess(onBg),
                            const SizedBox(height: 100), // Bottom padding for nav bar
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            )),
            if (statusString.contains('SUSPENSO') && !_hideSuspensionGuide) _buildUnlockGuide(),
          ],
        ),
        bottomNavigationBar: _buildBottomNav(isDark),
      ),
    );
  }

  Widget _buildAppBar(Color onBg) {
    final provider = context.watch<AppProvider>();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Align(
              alignment: Alignment(AppBranding.homeLogoPosition / 50 - 1, 0),
              child: BrandLogo(height: 72, darkBackground: onBg == Colors.white),
            ),
          ),
          Stack(
            children: [
              IconButton(
                icon: Icon(Icons.notifications_none, color: onBg, size: 28),
                onPressed: () => Navigator.pushNamed(context, '/notifications'),
              ),
              if (provider.unreadNotificationsCount > 0)
                Positioned(
                  right: 8,
                  top: 8,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(color: brandColor, shape: BoxShape.circle),
                    constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                    child: Text(
                      '${provider.unreadNotificationsCount}',
                      style: const TextStyle(color: Colors.white, fontSize: 8, fontWeight: FontWeight.bold),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _performUnlock(String contractId) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (c) => AlertDialog(
        backgroundColor: Colors.white,
        content: Row(
          children: [
            CircularProgressIndicator(color: brandColor),
            const SizedBox(width: 20),
            const Expanded(
              child: Text(
                'Realizando desbloqueio...',
                style: TextStyle(color: Colors.black87),
              ),
            ),
          ],
        ),
      ),
    );

    try {
      final provider = Provider.of<AppProvider>(context, listen: false);
      final result = await provider.unlockContract(contractId);

      if (mounted) Navigator.pop(context); // Pop loading

      if (result['status'] == 1 || result['liberado'] == true) {
        // Atualiza status localmente para resposta imediata
        provider.updateContract({...provider.userContract, 'status': 'ATIVO'});

        final dias = result['liberado_dias']?.toString() ?? 'alguns';
        // Limpar mensagem para remover espaços extras e quebras de linha
        String msg = result['msg']?.toString() ?? 'Desbloqueio realizado com sucesso!';
        msg = msg.replaceAll(RegExp(r'\s+'), ' ').trim();

        if (mounted) {
          showTopSnackBar(context, SnackBar(
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Sucesso!',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                const SizedBox(height: 4),
                Text('Desbloqueio realizado por $dias dias.'),
              ],
            ),
            backgroundColor: Colors.green,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            margin: const EdgeInsets.all(16),
            duration: const Duration(seconds: 4),
          ));
        }
      } else {
        if (mounted) {
          showTopSnackBar(context, SnackBar(content: Text(result['msg']?.toString() ?? 'Erro ao desbloquear'), backgroundColor: brandColor));
        }
      }
    } catch (e) {
      if (mounted) {
        Navigator.pop(context);
        showTopSnackBar(context, SnackBar(content: Text(UserFacingError.from(e)), backgroundColor: brandColor));
      }
    }
  }

  Widget _buildUserCard(Color cardBg, Color textColor, Color subTextColor, bool isDark) {
    final provider = Provider.of<AppProvider>(context);
    final contract = provider.userContract;
    final userName = provider.userName ?? '';
    final contractId = contract['id']?.toString() ?? '';
    final status = contract['status'] ?? '';
    final planName = contract['plan_name'] ?? '';
    final address = contract['address'] ?? '';
    // Mostra a data de cadastro conforme solicitado
    final registrationDate = contract['registration_date'] ?? '';
    final contractDueDay = contract['contract_due_day'] ?? '';

    // Se estiver suspenso, muda cores
    final statusUpper = status.toString().toUpperCase();
    final isSuspended = statusUpper.contains('SUSPENSO') || statusUpper.contains('BLOQUEADO') || statusUpper.contains('CANCELADO');

    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 60,
                height: 60,
                decoration: BoxDecoration(
                  color: brandColor,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Icon(Icons.person, color: Colors.white, size: 36),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: isDark ? Colors.white.withOpacity(0.1) : Colors.grey[200],
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text.rich(
                            TextSpan(
                              children: [
                                TextSpan(
                                  text: 'Contrato: ',
                                  style: TextStyle(color: subTextColor, fontSize: 10, fontWeight: FontWeight.bold),
                                ),
                                TextSpan(
                                  text: contractId,
                                  style: TextStyle(color: textColor, fontSize: 10, fontWeight: FontWeight.bold),
                                ),
                              ],
                            ),
                          ),
                        ),
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: isSuspended ? Colors.red.withOpacity(0.2) : Colors.green.withOpacity(0.2),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                status.toString().toUpperCase(),
                                style: TextStyle(
                                  color: isSuspended ? Colors.red : Colors.green,
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                            if (isSuspended) ...[
                              const SizedBox(width: 8),
                            ],
                          ],
                        ),
                      ],
                    ),
                    Text(
                      userName.toUpperCase(),
                      style: TextStyle(color: textColor, fontSize: 18, fontWeight: FontWeight.bold),
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: isDark ? Colors.black : Colors.grey[100],
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  planName,
                  style: TextStyle(
                    color: isDark ? Colors.white : Colors.black,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                  maxLines: _userCardExpanded ? null : 1,
                  overflow: _userCardExpanded ? TextOverflow.visible : TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text(
                      'VENC. $contractDueDay',
                      style: TextStyle(
                        color: isDark ? Colors.white : Colors.black,
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                    Text(' | ', style: TextStyle(color: isDark ? Colors.white24 : Colors.black26)),
                    Flexible(
                      child: Text(
                        registrationDate,
                        style: TextStyle(
                          color: isDark ? Colors.white : Colors.black,
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                        overflow: TextOverflow.ellipsis,
                        maxLines: 1,
                      ),
                    ),
                  ],
                ),
                Divider(color: isDark ? Colors.white10 : Colors.black12, height: 24),
                InkWell(
                  onTap: () => setState(() => _userCardExpanded = !_userCardExpanded),
                  borderRadius: BorderRadius.circular(8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          address,
                          style: TextStyle(
                            color: textColor,
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: _userCardExpanded ? null : 1,
                          overflow: _userCardExpanded ? TextOverflow.visible : TextOverflow.ellipsis,
                        ),
                      ),
                      AnimatedRotation(
                        turns: _userCardExpanded ? 0.5 : 0,
                        duration: const Duration(milliseconds: 200),
                        child: Icon(Icons.keyboard_arrow_down, color: textColor),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildExemptCard(Color cardBg, Color textColor, Color subTextColor) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Color.alphaBlend(brandColor.withOpacity(0.1), cardBg), cardBg],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: brandColor.withOpacity(0.2)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: brandColor.withOpacity(0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(Icons.star_rounded, color: brandColor, size: 32),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'CLIENTE ISENTO',
                  style: TextStyle(
                    color: textColor,
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Você possui isenção de fatura neste contrato.',
                  style: TextStyle(
                    color: subTextColor,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCongratsCard(Color cardBg, Color textColor, Color subTextColor) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [Color.alphaBlend(Colors.green.withValues(alpha: 0.2), cardBg), cardBg],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.green.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.green.withValues(alpha: 0.2),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.emoji_events_rounded, color: Colors.green, size: 32),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Parabéns!',
                  style: TextStyle(
                    color: textColor,
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Você está em dia com suas faturas.',
                  style: TextStyle(
                    color: subTextColor,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInvoiceCard(Color cardBg, Color textColor, Color subTextColor, bool isDark) {
    final provider = Provider.of<AppProvider>(context);
    final contract = provider.userContract;

    // Verifica status especial: Isento
    if (contract['invoice_status_code'] == 'exempt') {
      return _buildExemptCard(cardBg, textColor, subTextColor);
    }

    // Verifica se está tudo pago (definido no LoginScreen)
    if (contract['invoice_status_code'] == 'paid') {
      return _buildCongratsCard(cardBg, textColor, subTextColor);
    }

    final invoiceAmount = contract['last_invoice_value'] ?? '0,00';
    final invoiceCorrected = contract['last_invoice_corrected_value'] ?? invoiceAmount;
    final interestAmount = contract['last_invoice_interest'];
    final invoiceDue = contract['last_invoice_due'] ?? contract['expiry_date'] ?? 'N/A';

    // Determina o status da fatura
    final isOverdue = contract['invoice_status_code'] == 'overdue';
    final statusText = isOverdue ? 'FATURA ATRASADA' : 'FATURA ABERTA';
    final statusColor = isOverdue ? const Color(0xFFFF3333) : Colors.orange[700];
    final statusIcon = isOverdue ? Icons.warning_amber_rounded : Icons.check_circle_outline;

    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(statusIcon, color: statusColor, size: 20),
                  const SizedBox(width: 8),
                  Text(
                    statusText,
                    style: TextStyle(color: statusColor, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
              if (isOverdue && interestAmount != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: statusColor!.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: statusColor!.withOpacity(0.3)),
                  ),
                  child: Text(
                    '+ R\$ $interestAmount de juros',
                    style: TextStyle(color: statusColor, fontSize: 10, fontWeight: FontWeight.bold),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'R\$ ${isOverdue ? invoiceCorrected : invoiceAmount}',
            style: TextStyle(color: textColor, fontSize: 36, fontWeight: FontWeight.bold),
          ),
          if (isOverdue && invoiceCorrected != invoiceAmount)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                'Valor original: R\$ $invoiceAmount',
                style: const TextStyle(color: Colors.grey, fontSize: 12, decoration: TextDecoration.lineThrough),
              ),
            ),
          Text(
            'Vencimento $invoiceDue',
            style: TextStyle(color: isOverdue ? const Color(0xFFFF3333) : Colors.grey, fontSize: 14, fontWeight: isOverdue ? FontWeight.bold : FontWeight.normal),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                flex: 3,
                child: ElevatedButton(
                  onPressed: () {
                    final pixCode = contract['pix_code'];
                    if (pixCode != null && pixCode.isNotEmpty) {
                      Clipboard.setData(ClipboardData(text: pixCode));
                      showTopSnackBar(context, 
                        const SnackBar(content: Text('Código PIX copiado com sucesso!')),
                      );
                    } else {
                      showTopSnackBar(context, 
                        const SnackBar(content: Text('Código PIX não disponível')),
                      );
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: brandColor,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      SvgPicture.asset(
                        'assets/pix-svgrepo-com.svg',
                        width: 30,
                        height: 30,
                        colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
                      ),
                      const SizedBox(width: 8),
                      const Text('Pagar com PIX', style: TextStyle(fontWeight: FontWeight.bold)),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _buildSmallButton(
                CustomPaint(
                  size: const Size(24, 20),
                  painter: BarcodePainter(),
                ),
                onTap: () {
                  final barcode = contract['barcode'];
                  if (barcode != null && barcode.isNotEmpty) {
                    Clipboard.setData(ClipboardData(text: barcode));
                    showTopSnackBar(context, 
                      const SnackBar(content: Text('Código de barras copiado com sucesso!')),
                    );
                  } else {
                    showTopSnackBar(context, 
                      const SnackBar(content: Text('Código de barras não disponível')),
                    );
                  }
                },
              ),
              const SizedBox(width: 8),
              _buildSmallButton(const Icon(Icons.credit_card, color: Colors.white)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSmallButton(Widget content, {VoidCallback? onTap}) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: 54,
          height: 54,
          decoration: BoxDecoration(
            color: brandColor,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Center(child: content),
        ),
      ),
    );
  }

  Widget _buildWifiCard(Color cardBg, Color textColor, Color subTextColor) {
    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.wifi, color: brandColor, size: 24),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Informação da sua rede wifi',
                  style: TextStyle(color: textColor, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(_ssid, style: TextStyle(color: textColor, fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          _buildModemStatusRow(textColor, subTextColor),
          const SizedBox(height: 12),
          _wifiInfoRow(Icons.public, 'IP do modem', _wanIp, textColor, subTextColor),
          const SizedBox(height: 12),
          _buildModemUptimeSection(textColor, subTextColor),
        ],
      ),
    );
  }

  Widget _buildModemStatusRow(Color textColor, Color subTextColor) {
    Color statusColor = Colors.orange;
    if (_modemConnection == 'online') {
      statusColor = Colors.green;
    } else if (_modemConnection == 'offline') {
      statusColor = Colors.red;
    } else if (_modemConnection == 'manutencao') {
      statusColor = Colors.amber;
    }

    return Row(
      children: [
        Icon(Icons.router, color: brandColor, size: 20),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Status do modem',
                style: TextStyle(color: subTextColor, fontSize: 12, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 2),
              Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(color: statusColor, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _modemConnectionLabel,
                      style: TextStyle(color: textColor, fontSize: 15, fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildModemUptimeSection(Color textColor, Color subTextColor) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => setState(() => _modemUptimeExpanded = !_modemUptimeExpanded),
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(
              children: [
                Icon(Icons.schedule, color: brandColor, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Modem ligado há',
                    style: TextStyle(
                      color: subTextColor,
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                AnimatedRotation(
                  turns: _modemUptimeExpanded ? 0.5 : 0,
                  duration: const Duration(milliseconds: 200),
                  child: Icon(
                    Icons.keyboard_arrow_down,
                    color: subTextColor,
                    size: 22,
                  ),
                ),
              ],
            ),
          ),
        ),
        AnimatedCrossFade(
          firstChild: const SizedBox.shrink(),
          secondChild: Padding(
            padding: const EdgeInsets.only(left: 30, top: 4),
            child: Text(
              _modemUptime,
              style: TextStyle(
                color: textColor,
                fontSize: 15,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          crossFadeState: _modemUptimeExpanded ? CrossFadeState.showSecond : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 200),
        ),
      ],
    );
  }

  Widget _wifiInfoRow(
    IconData icon,
    String label,
    String value,
    Color textColor,
    Color subTextColor,
  ) {
    return Row(
      children: [
        Icon(icon, color: brandColor, size: 20),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: TextStyle(color: subTextColor, fontSize: 12, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 2),
              Text(
                value,
                style: TextStyle(color: textColor, fontSize: 15, fontWeight: FontWeight.bold),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAIAssistantCard(Color cardBg, Color textColor, Color subTextColor) {
    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              FaIcon(FontAwesomeIcons.headset, color: brandColor, size: 26),
              const SizedBox(width: 12),
              Text(
                'Suporte',
                style: TextStyle(
                  color: textColor,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Fale com o Atendimento',
            style: TextStyle(color: subTextColor, fontSize: 14, height: 1.5),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                flex: 3,
                child: ElevatedButton.icon(
                  onPressed: () => Navigator.of(context).pushNamed('/ai_chat'),
                  icon: const FaIcon(FontAwesomeIcons.solidComment, size: 20),
                  label: const Text(
                    'Falar com o suporte',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: brandColor,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    elevation: 0,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              _buildActionIconButton(FontAwesomeIcons.whatsapp, () async {
                final digits = AppBranding.whatsappDigits;
                final message = Uri.encodeComponent('Preciso de suporte');
                final waUrl = Uri.parse('https://wa.me/$digits?text=$message');
                if (await canLaunchUrl(waUrl)) {
                  await launchUrl(waUrl, mode: LaunchMode.externalApplication);
                } else {
                  if (context.mounted) _showTopBanner('Não foi possível abrir o WhatsApp');
                }
              }), // WhatsApp Oficial
              const SizedBox(width: 12),
              _buildActionIconButton(FontAwesomeIcons.phone, () async {
                final phone = AppBranding.supportPhone;
                final uri = Uri(scheme: 'tel', path: phone);
                if (await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                } else {
                  // Fallback com dígitos apenas
                  final digits = phone.replaceAll(RegExp(r'[^\d]'), '');
                  final alt = Uri.parse('tel:$digits');
                  if (await canLaunchUrl(alt)) {
                    await launchUrl(alt, mode: LaunchMode.externalApplication);
                  } else {
                    if (context.mounted) _showTopBanner('Não foi possível realizar a chamada');
                  }
                }
              }), // Telefone
            ],
          ),
        ],
      ),
    );
  }

  void _showTopBanner(String message) {
    showTopMessage(message, duration: const Duration(seconds: 2));
  }

  Widget _buildActionIconButton(FaIconData icon, VoidCallback onTap) {
    return Material(
      color: brandColor,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          width: 54,
          height: 54,
          alignment: Alignment.center,
          child: FaIcon(icon, color: Colors.white, size: 22),
        ),
      ),
    );
  }

  Widget _buildQuickAccess(Color textColor) {
    final List<Map<String, dynamic>> masterItems = [
      {
        'ids': ['wifi', 'MEU WI-FI', 'meu_wifi'],
        'icon': Icons.wifi_rounded,
        'label': 'Meu Wi-Fi',
        'route': '/wifi'
      },
      {
        'ids': ['CONSUMO', 'consumo'],
        'icon': Icons.bar_chart_rounded,
        'label': 'Consumo',
        'route': '/consumo'
      },
      {
        'ids': ['cameras', 'CÂMERAS', 'cameras_cftv'],
        'icon': Icons.videocam_rounded,
        'label': 'Câmeras',
        'route': null // '/cameras' - Tela ainda não implementada
      },
      {
        'ids': ['speed_test', 'FAST TEST', 'speedtest', 'SPEED_TEST'],
        'icon': Icons.speed_rounded,
        'label': 'Teste de Velocidade',
        'route': '/speedtest'
      },
      {
        'ids': ['diagnostic', 'DIAGNÓSTICO WI-FI', 'wifi_diagnostic', 'DIAGNOSTICO WI-FI'],
        'icon': Icons.network_check_rounded,
        'label': 'Diagnóstico',
        'route': null // '/diagnostic' - Tela ainda não implementada
      },
      {
        'ids': ['PLANOS', 'planos'],
        'icon': Icons.layers_rounded,
        'label': 'Planos',
        'route': '/planos'
      },
      {
        'ids': ['contrato', 'CONTRATO', 'CONTRATO ASSINADO', 'contrato_assinado', 'CONTRATO_ASSINADO'],
        'icon': Icons.description_rounded,
        'label': 'Contrato Assinado',
        'route': '/contratos'
      },
      {
        'ids': ['nota_fiscal', 'NOTA FISCAL', 'notas', 'NOTAS'],
        'icon': Icons.receipt_long_rounded,
        'label': 'Nota Fiscal',
        'route': '/nota_fiscal'
      },
      {
        'ids': ['connected_devices', 'CONNECTED_DEVICES', 'dispositivos', 'DISPOSITIVOS CONECTADOS'],
        'icon': Icons.devices_other_rounded,
        'label': 'Dispositivos',
        'route': '/connected_devices'
      },
    ];

    return Consumer<AppProvider>(
      builder: (context, provider, child) {
        if (!provider.appConfigLoaded) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            provider.fetchAppConfig();
          });
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Acesso Rápido',
                style: TextStyle(color: textColor, fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 16),
              const Center(
                child: SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ],
          );
        }

        final activeKeys = <String>{
          ...provider.activeShortcuts,
          ...provider.activeTools,
        };

        // Filter items based on active keys (case-insensitive check against valid IDs)
        final items = masterItems.where((item) {
          final ids = item['ids'] as List<String>;
          // Check if any of the item's IDs are present in the activeKeys set
          return ids.any((id) => activeKeys.contains(id) || activeKeys.contains(id.toUpperCase()) || activeKeys.contains(id.toLowerCase()));
        }).toList();

        if (items.isEmpty) {
          return const SizedBox.shrink();
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Acesso Rápido',
              style: TextStyle(color: textColor, fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                mainAxisSpacing: 24,
                crossAxisSpacing: 16,
                childAspectRatio: 0.85,
              ),
              itemCount: items.length,
              itemBuilder: (context, index) {
                return Column(
                  children: [
                    Container(
                      width: 70,
                      height: 70,
                      decoration: BoxDecoration(
                        color: brandColor,
                        borderRadius: BorderRadius.circular(20),
                        boxShadow: [
                          BoxShadow(
                            color: brandColor.withOpacity(0.3),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                            spreadRadius: 0,
                          ),
                        ],
                      ),
                      child: Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () {
                            final item = items[index];
                            if (item['label'] == 'Desbloqueio') {
                              final contractId = provider.userContract['id']?.toString() ?? provider.userContract['contrato']?.toString() ?? '';

                              if (contractId.isNotEmpty) {
                                _performUnlock(contractId);
                              } else {
                                showTopSnackBar(context, const SnackBar(content: Text('Erro: Contrato não identificado.')));
                              }
                            } else if (item['route'] != null) {
                              Navigator.of(context).pushNamed(item['route']);
                            } else {
                              showTopSnackBar(context, SnackBar(content: Text('${item['label']} em breve!')));
                            }
                          },
                          borderRadius: BorderRadius.circular(20),
                          child: Icon(items[index]['icon'], color: Colors.white, size: 32),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      items[index]['label'],
                      style: TextStyle(
                        color: textColor, // Garante contraste máximo (Preto no Claro, Branco no Escuro)
                        fontSize: 12, // Levemente reduzido para caber melhor 2 linhas
                        fontWeight: FontWeight.bold, // Negrito para evitar parecer "cinza/apagado"
                      ),
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                );
              },
            ),
          ],
        );
      },
    );
  }

  Widget _buildBottomNav(bool isDark) {
    return Stack(
      alignment: Alignment.bottomCenter,
      clipBehavior: Clip.none,
      children: [
        Container(
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 48), // Sobe a barra (era 34)
          height: 62,
          decoration: BoxDecoration(
            color: (isDark ? const Color(0xFF1E1E1E) : AppBranding.cardBackground(context)).withOpacity(0.95),
            borderRadius: BorderRadius.circular(36), // Mantém a pílula mais fina
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.2), // Sombra mais suave no light
                blurRadius: 20,
                offset: const Offset(0, 10),
                spreadRadius: 0,
              ),
            ],
            border: Border.all(
              color: isDark ? Colors.white.withOpacity(0.1) : Colors.black.withOpacity(0.05),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _buildNavItem(Icons.home_rounded, "Início", true, () {}),
              _buildNavItem(Icons.receipt_long_rounded, "Faturas", false, () => Navigator.of(context).pushNamed('/fatura')),
              const SizedBox(width: 56), // Espaço ajustado para o botão central mais fino
              _buildNavItem(Icons.headset_mic_rounded, "Chamado", false, () => Navigator.of(context).pushNamed('/support')),
              _buildNavItem(Icons.menu_rounded, "Menu", false, () => Navigator.of(context).pushNamed('/menu')),
            ],
          ),
        ),
        Positioned(
          bottom: 40, // Abaixado mais ainda na pílula
          child: _buildCentralButton(),
        ),
      ],
    );
  }

  Widget _buildNavItem(IconData icon, String label, bool isSelected, VoidCallback onTap) {
    final color = isSelected ? brandColor : AppBranding.onColor(AppBranding.cardBackground(context));

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 26),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 10,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showMenuOptions() {
    // Implementação antiga, não utilizada mais pois temos a tela /menu
    // Mas mantida por compatibilidade caso seja chamada
    final isDark = Theme.of(context).brightness == Brightness.dark;
    showModalBottomSheet(
      context: context,
      backgroundColor: isDark ? const Color(0xFF1E1E1E) : Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return Container(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey[700],
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 24),
              Text(
                'Menu',
                style: TextStyle(
                  color: isDark ? Colors.white : Colors.black,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 24),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.logout_rounded, color: Colors.red),
                ),
                title: const Text(
                  'Sair do App',
                  style: TextStyle(
                    color: Colors.red,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                onTap: () async {
                  Navigator.pop(context); // Fecha o menu
                  await _handleLogout();
                },
              ),
              const SizedBox(height: 24),
            ],
          ),
        );
      },
    );
  }

  Future<void> _handleLogout() async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: isDark ? const Color(0xFF1E1E1E) : Colors.white,
        title: Text('Sair', style: TextStyle(color: isDark ? Colors.white : Colors.black)),
        content: Text('Deseja realmente sair do aplicativo?', style: TextStyle(color: isDark ? Colors.white70 : Colors.grey[800])),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar', style: TextStyle(color: Colors.grey)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Sair', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.clear();
      if (!mounted) return;
      Navigator.of(context).pushNamedAndRemoveUntil('/login', (route) => false);
    }
  }

  static const Color _suspendedRed = Color(0xFFC62828);

  /// Balão "DESBLOQUEIE AQUI" acima do cadeado. Fica no corpo da tela (e não dentro da
  /// barra inferior) porque fora dos limites da barra o Flutter ignora os toques no X.
  Widget _buildUnlockGuide() {
    return Positioned(
      left: 0,
      right: 0,
      bottom: 102,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 16, right: 16),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      color: _suspendedRed,
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.4),
                          blurRadius: 12,
                          offset: const Offset(0, 4),
                        ),
                      ],
                      border: Border.all(color: Colors.white.withOpacity(0.3), width: 1.5),
                    ),
                    child: const Text(
                      'DESBLOQUEIE AQUI',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ),
                Positioned(
                  top: 0,
                  right: 0,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => setState(() => _hideSuspensionGuide = true),
                    child: Container(
                      width: 36,
                      height: 36,
                      alignment: Alignment.center,
                      child: Container(
                        width: 26,
                        height: 26,
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                          boxShadow: [BoxShadow(color: Colors.black26, blurRadius: 4)],
                        ),
                        child: const Icon(Icons.close, size: 14, color: _suspendedRed),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const Icon(Icons.arrow_drop_down_rounded, color: _suspendedRed, size: 40),
          ],
        ),
      ),
    );
  }

  Widget _buildCentralButton() {
    final provider = Provider.of<AppProvider>(context);
    final status = provider.userContract['status'] ?? 'ATIVO';
    final isSuspended = status.toString().toUpperCase().contains('SUSPENSO');

    return SizedBox(
      width: 200,
      height: 220,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Positioned(
            bottom: 22, // Mais baixo para encaixar melhor na barra
            left: 0,
            right: 0,
            child: Center(
              child: GestureDetector(
                onTap: () {
                  if (isSuspended) {
                    final contractId = provider.userContract['id']?.toString() ?? '';
                    if (contractId.isNotEmpty) {
                      _performUnlock(contractId);
                    } else {
                      showTopSnackBar(context, const SnackBar(content: Text('Erro: ID do contrato não encontrado.')));
                    }
                  } else {
                    showTopSnackBar(context, SnackBar(
                      content: const Text(
                        'Recurso não disponível. Seu contrato está ativo.',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                      ),
                      backgroundColor: brandColor,
                      behavior: SnackBarBehavior.floating,
                      duration: const Duration(seconds: 2),
                    ));
                  }
                },
                child: Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: isSuspended ? [const Color(0xFFEF5350), _suspendedRed] : [const Color(0xFF66BB6A), const Color(0xFF2E7D32)],
                    ),
                    border: Border.all(
                      color: Colors.white.withOpacity(0.15),
                      width: 1,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.white.withOpacity(0.4),
                        blurRadius: 0,
                        offset: const Offset(0, 2),
                        spreadRadius: 0,
                      ),
                      BoxShadow(
                        color: Colors.black.withOpacity(0.2),
                        blurRadius: 10,
                        offset: const Offset(0, -4),
                        spreadRadius: -2,
                      ),
                    ],
                  ),
                  child: Center(
                    child: Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.black.withOpacity(0.1), boxShadow: [
                        BoxShadow(
                          color: Colors.white.withOpacity(0.1),
                          blurRadius: 0,
                          offset: const Offset(0, 1),
                        )
                      ]),
                      child: Icon(
                        isSuspended ? Icons.lock_outline : Icons.lock_open_rounded,
                        color: Colors.white,
                        size: 24,
                        shadows: const [
                          Shadow(
                            color: Colors.black26,
                            blurRadius: 4,
                            offset: Offset(0, 2),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
