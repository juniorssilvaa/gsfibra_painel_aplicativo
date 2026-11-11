import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../config.dart';
import '../../provider.dart';

class PerfilScreen extends StatefulWidget {
  const PerfilScreen({super.key});

  @override
  State<PerfilScreen> createState() => _PerfilScreenState();
}

class _PerfilScreenState extends State<PerfilScreen> {
  String _appVersion = 'Carregando...';
  bool _useLocalBackend = false;
  final TextEditingController _apiController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadAppVersion();
    _loadApiOverride();
  }

  Future<void> _loadAppVersion() async {
    try {
      final info = await PackageInfo.fromPlatform();
      if (mounted) {
        setState(() {
          _appVersion = info.version;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _appVersion = '1.0.0';
        });
      }
    }
  }

  Future<void> _launchUrl(String url) async {
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri);
    }
  }

  Future<void> _loadApiOverride() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final enabled = prefs.getBool('api_base_url_use_override') ?? false;
      final override = prefs.getString('api_base_url_override') ?? '';
      setState(() {
        _useLocalBackend = enabled && override.isNotEmpty;
        _apiController.text = override;
      });
    } catch (_) {}
  }

  Future<void> _saveApiOverride() async {
    final prefs = await SharedPreferences.getInstance();
    final override = _apiController.text.trim();
    await prefs.setBool('api_base_url_use_override', _useLocalBackend);
    await prefs.setString('api_base_url_override', override);
    if (_useLocalBackend && override.isNotEmpty) {
      AppConfig.setRuntimeApiBaseUrl(override);
    } else {
      AppConfig.setRuntimeApiBaseUrl(null);
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<AppProvider>();
    final userInfo = provider.userInfo;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final brandColor = Theme.of(context).colorScheme.primary;
    final cardBg = isDark ? const Color(0xFF111111) : Colors.white;
    final textColor = isDark ? Colors.white : Colors.black;
    final subTextColor = isDark ? Colors.grey : Colors.grey[700];

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: cardBg,
        title: Text('Meu Perfil', style: TextStyle(fontWeight: FontWeight.bold, color: textColor)),
        centerTitle: true,
        iconTheme: IconThemeData(color: textColor),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Center(
              child: Stack(
                children: [
                  Container(
                    width: 100,
                    height: 100,
                    decoration: BoxDecoration(
                      color: cardBg,
                      shape: BoxShape.circle,
                      border: Border.all(color: brandColor, width: 2),
                    ),
                    child: Icon(Icons.person, color: textColor, size: 60),
                  ),
                  Positioned(
                    bottom: 0,
                    right: 0,
                    child: Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(color: brandColor, shape: BoxShape.circle),
                      child: const Icon(Icons.edit, color: Colors.white, size: 16),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Text(
              provider.userName ?? 'Usuário gsfibra',
              style: TextStyle(color: textColor, fontSize: 22, fontWeight: FontWeight.bold),
            ),
            Text(
              provider.cpf ?? '',
              style: TextStyle(color: subTextColor, fontSize: 14),
            ),
            const SizedBox(height: 40),
            _buildInfoSection('Dados Pessoais', cardBg, textColor, subTextColor, [
              _buildInfoItem(Icons.email_outlined, 'E-mail', userInfo['email'] ?? 'A completar', textColor, subTextColor),
              _buildInfoItem(Icons.phone_outlined, 'Telefone', userInfo['telefone'] ?? 'A completar', textColor, subTextColor),
              _buildInfoItem(Icons.location_on_outlined, 'Endereço', provider.userContract['address'] ?? 'Consulte sua fatura', textColor, subTextColor),
            ]),
            const SizedBox(height: 24),
            _buildInfoSection('Configurações', cardBg, textColor, subTextColor, [
              _buildActionItem(Icons.description_outlined, 'Meus Contratos', () {
                Navigator.pushNamed(context, '/contratos');
              }, textColor, subTextColor),
              _buildActionItem(Icons.notifications_none, 'Notificações', () {}, textColor, subTextColor),
              _buildActionItem(Icons.lock_outline, 'Segurança', () {}, textColor, subTextColor),
              
              // Dark Mode Toggle
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  children: [
                    Icon(Icons.brightness_6, color: subTextColor, size: 20),
                    const SizedBox(width: 16),
                    Text('Modo Escuro', style: TextStyle(color: textColor, fontWeight: FontWeight.w500)),
                    const Spacer(),
                    Switch(
                      value: isDark,
                      activeColor: brandColor,
                      onChanged: (val) {
                        provider.toggleTheme(val);
                      },
                    ),
                  ],
                ),
              ),
              // Ambiente (Backend)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.cloud_outlined, color: subTextColor, size: 20),
                        const SizedBox(width: 16),
                        Text('Usar backend local', style: TextStyle(color: textColor, fontWeight: FontWeight.w500)),
                        const Spacer(),
                        Switch(
                          value: _useLocalBackend,
                          activeColor: brandColor,
                          onChanged: (val) async {
                            setState(() => _useLocalBackend = val);
                            await _saveApiOverride();
                          },
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _apiController,
                      style: TextStyle(color: textColor),
                      decoration: InputDecoration(
                        labelText: 'URL do backend',
                        labelStyle: TextStyle(color: subTextColor),
                        hintText: 'http://10.0.1.6:8000/api',
                        hintStyle: TextStyle(color: subTextColor),
                        enabledBorder: OutlineInputBorder(
                          borderSide: BorderSide(color: Colors.white12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderSide: BorderSide(color: brandColor),
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      onSubmitted: (_) async => _saveApiOverride(),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        onPressed: _saveApiOverride,
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(color: brandColor),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        child: Text('Aplicar', style: TextStyle(color: brandColor, fontWeight: FontWeight.bold)),
                      ),
                    ),
                  ],
                ),
              ),
            ]),
            const SizedBox(height: 24),
            _buildInfoSection('Sobre', cardBg, textColor, subTextColor, [
              _buildActionItem(Icons.info_outline, 'Versão do App', () {}, textColor, subTextColor, trailingText: _appVersion),
              _buildActionItem(Icons.article_outlined, 'Termos de Uso', () {
                Navigator.pushNamed(context, '/terms');
              }, textColor, subTextColor),
              _buildActionItem(Icons.privacy_tip_outlined, 'Política de Privacidade', () {
                Navigator.pushNamed(context, '/privacy');
              }, textColor, subTextColor),
            ]),
            const SizedBox(height: 40),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {
                  provider.logout();
                  Navigator.of(context).pushNamedAndRemoveUntil('/login', (route) => false);
                },
                icon: const Icon(Icons.logout),
                label: const Text('SAIR DA CONTA'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: brandColor,
                  side: BorderSide(color: brandColor),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoSection(String title, Color bg, Color textColor, Color? subColor, List<Widget> items) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Text(title, style: TextStyle(color: textColor, fontWeight: FontWeight.bold, fontSize: 16)),
        ),
        Container(
          decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20), border: Border.all(color: Colors.grey.withOpacity(0.1))),
          child: Column(children: items),
        ),
      ],
    );
  }

  Widget _buildInfoItem(IconData icon, String label, String value, Color textColor, Color? subColor) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Row(
        children: [
          Icon(icon, color: subColor, size: 20),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: TextStyle(color: subColor, fontSize: 12)),
                Text(value, style: TextStyle(color: textColor, fontWeight: FontWeight.w500)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionItem(IconData icon, String label, VoidCallback onTap, Color textColor, Color? subColor, {String? trailingText}) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          children: [
            Icon(icon, color: subColor, size: 20),
            const SizedBox(width: 16),
            Text(label, style: TextStyle(color: textColor, fontWeight: FontWeight.w500)),
            const Spacer(),
            if (trailingText != null)
              Text(trailingText, style: TextStyle(color: subColor, fontSize: 14))
            else
              Icon(Icons.chevron_right, color: subColor),
          ],
        ),
      ),
    );
  }
}
