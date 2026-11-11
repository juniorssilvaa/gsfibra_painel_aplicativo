import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../../provider.dart';
import 'package:permission_handler/permission_handler.dart';
import '../../theme/app_branding.dart';
import '../../theme/brand_colors.dart';

class MenuScreen extends StatefulWidget {
  const MenuScreen({super.key});

  @override
  State<MenuScreen> createState() => _MenuScreenState();
}

class _MenuScreenState extends State<MenuScreen> {
  String _version = '1.0.1';

  @override
  void initState() {
    super.initState();
    _loadVersion();
  }

  Future<void> _loadVersion() async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      if (mounted) {
        setState(() {
          _version = packageInfo.version;
        });
      }
    } catch (_) {
      // Fallback version
    }
  }
  
  Future<void> _showPermissionsSheet() async {
    Future<String> s(Permission p) async {
      final st = await p.status;
      if (st.isGranted) return 'Permitido';
      if (st.isDenied) return 'Negado';
      if (st.isPermanentlyDenied) return 'Negado (def.)';
      if (st.isRestricted) return 'Restrito';
      if (st.isLimited) return 'Limitado';
      return st.name;
    }
    final map = <String, String>{};
    try { map['Notificações'] = await s(Permission.notification); } catch (_) {}
    try { map['Localização'] = await s(Permission.location); } catch (_) {}
    
    if (!mounted) return;
    final sheetBg = AppBranding.cardBackground(context);
    showModalBottomSheet(
      context: context,
      backgroundColor: sheetBg,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (_) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Permissões', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: AppBranding.onColor(sheetBg))),
            const SizedBox(height: 12),
            ...map.entries.map((e) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                e.value.startsWith('Permitido') ? Icons.check_circle : Icons.error_outline,
                color: e.value.startsWith('Permitido') ? Colors.green : Colors.orange,
              ),
              title: Text(e.key, style: TextStyle(color: AppBranding.onColor(sheetBg))),
              subtitle: Text(e.value, style: TextStyle(color: AppBranding.onColor(sheetBg).withValues(alpha: 0.6))),
            )),
            const SizedBox(height: 12),
            ElevatedButton.icon(
              onPressed: () => openAppSettings(),
              icon: const Icon(Icons.settings),
              label: const Text('Abrir configurações do app'),
              style: ElevatedButton.styleFrom(
                backgroundColor: BrandColors.primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            )
          ],
        ),
      ),
    );
  }
  

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final brandColor = BrandColors.primary;
    final provider = context.watch<AppProvider>();
    final bg = AppBranding.screenBackground(context);
    final onBg = AppBranding.onColor(bg);
    final cardBg = AppBranding.cardBackground(context);
    final onCard = AppBranding.onColor(cardBg);

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: AppBranding.headerBackground,
        foregroundColor: AppBranding.onHeader,
        surfaceTintColor: Colors.transparent,
        title: Text('MENU', style: TextStyle(fontWeight: FontWeight.bold, color: AppBranding.onHeader)),
        centerTitle: true,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            children: [
              const SizedBox(height: 24),

              // 1. Alterar Contratos
              _buildMenuItem(
                context,
                svgIcon: _Svgs.contract,
                title: 'Alterar Contratos',
                subtitle: 'Gerencie seus contratos ativos',
                onTap: () => Navigator.pushNamed(context, '/select_contract'),
                isDark: isDark,
              ),

              // 2. Termos de Uso
              _buildMenuItem(
                context,
                svgIcon: _Svgs.terms,
                title: 'Termos de Uso',
                subtitle: 'Leia nossos termos de serviço',
                onTap: () => Navigator.pushNamed(context, '/terms'),
                isDark: isDark,
              ),

              // 3. Política de Privacidade
              _buildMenuItem(
                context,
                svgIcon: _Svgs.privacy,
                title: 'Política de Privacidade',
                subtitle: 'Como tratamos seus dados',
                onTap: () => Navigator.pushNamed(context, '/privacy'),
                isDark: isDark,
              ),

              _buildMenuItem(
                context,
                svgIcon: _Svgs.shield,
                title: 'Permissões do App',
                subtitle: 'Verificar notificações e localização',
                onTap: _showPermissionsSheet,
                isDark: isDark,
              ),

              // 4. Modo Escuro (Penúltimo)
              Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: cardBg,
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.02),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: SwitchListTile(
                  value: isDark,
                  onChanged: (value) {
                    provider.toggleTheme(value);
                  },
                  title: Text(
                    isDark ? 'Modo Escuro' : 'Modo Claro',
                    style: TextStyle(
                      color: onCard,
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                    ),
                  ),
                  secondary: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: BrandColors.primary, // Fundo sólido na cor da marca
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: SvgPicture.string(
                      _Svgs.moon,
                      width: 24,
                      height: 24,
                      colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn), // Ícone branco
                    ),
                  ),
                  // Customização da Chave (Switch)
                  activeColor: Colors.white, // Bolinha branca quando ativo
                  activeTrackColor: brandColor, // Trilho na cor da marca quando ativo
                  inactiveThumbColor: Colors.grey[400],
                  inactiveTrackColor: isDark ? Colors.grey[800] : Colors.grey[300],
                  contentPadding: EdgeInsets.zero,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                ),
              ),

              const SizedBox(height: 32),

              // 5. Botão de Sair (Vermelho Sólido)
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: () {
                    provider.logout();
                    Navigator.pushNamedAndRemoveUntil(context, '/login', (route) => false);
                  },
                  icon: const Icon(Icons.logout_rounded, color: Colors.white),
                  label: const Text('Sair do App', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: brandColor,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    elevation: 4,
                    shadowColor: brandColor.withOpacity(0.4),
                  ),
                ),
              ),
          
              const SizedBox(height: 32),
              
              // Versão
              Center(
                child: Text(
                  'Versão $_version',
                  style: TextStyle(color: onBg.withValues(alpha: 0.75), fontSize: 12),
                ),
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMenuItem(
    BuildContext context, {
    required String svgIcon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
    required bool isDark,
  }) {
    final cardBg = AppBranding.cardBackground(context);
    final onCard = AppBranding.onColor(cardBg);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.02),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: BrandColors.primary, // Fundo sólido na cor da marca
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: SvgPicture.string(
                    svgIcon,
                    width: 24,
                    height: 24,
                    colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn), // Ícone branco
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: onCard,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        subtitle,
                        style: TextStyle(
                          fontSize: 12,
                          color: onCard.withValues(alpha: 0.6),
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.arrow_forward_ios_rounded,
                  size: 16,
                  color: onCard.withValues(alpha: 0.6),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Svgs {
  static const String contract = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M14 2H6C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M14 2V8H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16 13H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16 17H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';

  static const String terms = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M14 13L14.0001 13.0001" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M3 21H9L8.60002 18.6C8.20002 16.2 10 14 12.4 14H14.8C15.9 14 16.9 14.9 16.9 16V16C16.9 18.8 14.6 21 11.8 21H3V21Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M18.4 12.4L20.8 10C22.4 8.40002 22.4 5.80002 20.8 4.20002C19.2 2.60002 16.6 2.60002 15 4.20002L12.6 6.6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M10.5 8.7L16.2 14.4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';

  static const String privacy = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M12 22C12 22 20 18 20 12V5L12 2L4 5V12C4 18 12 22 12 22Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M12 8V16" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M12 16V16.01" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';

  static const String moon = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';

  static const String shield = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';
}
