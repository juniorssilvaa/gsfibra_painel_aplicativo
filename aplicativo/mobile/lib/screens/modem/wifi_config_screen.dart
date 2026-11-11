import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import '../../provider.dart';
import '../../models/cpe_info.dart';
import '../../theme/brand_colors.dart';

class WifiConfigScreen extends StatefulWidget {
  final CpeInfo? initialInfo;

  const WifiConfigScreen({super.key, this.initialInfo});

  @override
  State<WifiConfigScreen> createState() => _WifiConfigScreenState();
}

class _WifiConfigScreenState extends State<WifiConfigScreen> {
  final _formKey = GlobalKey<FormState>();
  
  late TextEditingController _ssid2gController;
  late TextEditingController _pass2gController;
  late TextEditingController _ssid5gController;
  late TextEditingController _pass5gController;
  
  bool _obscure2g = true;
  bool _obscure5g = true;

  final Color brandColor = BrandColors.primary;
  final Color cardBg = const Color(0xFF1E1E1E);

  @override
  void initState() {
    super.initState();
    _ssid2gController = TextEditingController(text: widget.initialInfo?.ssid2g ?? '');
    _pass2gController = TextEditingController(text: widget.initialInfo?.password2g ?? '');
    _ssid5gController = TextEditingController(text: widget.initialInfo?.ssid5g ?? '');
    _pass5gController = TextEditingController(text: widget.initialInfo?.password5g ?? '');
  }

  @override
  void dispose() {
    _ssid2gController.dispose();
    _pass2gController.dispose();
    _ssid5gController.dispose();
    _pass5gController.dispose();
    super.dispose();
  }

  CpeInfo _mergeSubmittedWifi(CpeInfo? base, {String? ssid2g, String? ssid5g}) {
    final b = base ?? widget.initialInfo;
    if (b == null) {
      return CpeInfo(ssid2g: ssid2g, ssid5g: ssid5g);
    }
    return b.copyWith(
      ssid2g: ssid2g ?? b.ssid2g,
      ssid5g: ssid5g ?? b.ssid5g,
    );
  }

  Future<void> _saveChanges() async {
    if (!_formKey.currentState!.validate()) return;

    if (!mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E1E1E),
        content: Row(
          children: [
            CircularProgressIndicator(color: BrandColors.primary),
            SizedBox(width: 20),
            Expanded(
              child: Text(
                'Atualizando configurações de Wi-Fi, aguarde...',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );

    var closedLoading = false;
    void closeLoadingIfOpen() {
      if (!mounted || closedLoading) return;
      Navigator.of(context).pop();
      closedLoading = true;
    }

    try {
      final appProvider = Provider.of<AppProvider>(context, listen: false);
      final sgpService = appProvider.sgpService;

      if (sgpService == null) throw Exception("Serviço não inicializado");

      String contractId = appProvider.userContract['id']?.toString() ?? '';

      if (contractId.isEmpty) {
        final cpf = appProvider.cpf ?? '';
        final password = appProvider.centralPassword ?? '';
        final contracts = await sgpService.getContratos(cpf, password);
        if (contracts.isNotEmpty) {
          contractId = contracts[0]['id']?.toString() ?? contracts[0]['contrato']?.toString() ?? '';
        }
      }

      if (contractId.isEmpty) throw Exception("Contrato não identificado");

      final sentSsid2g = _ssid2gController.text.trim().isNotEmpty ? _ssid2gController.text.trim() : null;
      final sentSsid5g = _ssid5gController.text.trim().isNotEmpty ? _ssid5gController.text.trim() : null;
      final sentPass2g = _pass2gController.text.isNotEmpty ? _pass2gController.text : null;
      final sentPass5g = _pass5gController.text.isNotEmpty ? _pass5gController.text : null;

      final success = await sgpService.changeWifi(
        contractId,
        ssid: sentSsid2g,
        password: sentPass2g,
        ssid5g: sentSsid5g,
        password5g: sentPass5g,
      );

      closeLoadingIfOpen();

      if (!success) {
        throw Exception("Falha ao salvar configurações. Tente novamente.");
      }

      if (!mounted) return;

      var resultCpe = _mergeSubmittedWifi(
        widget.initialInfo,
        ssid2g: sentSsid2g ?? widget.initialInfo?.ssid2g,
        ssid5g: sentSsid5g ?? widget.initialInfo?.ssid5g,
      );
      if (sentPass2g != null || sentPass5g != null) {
        resultCpe = resultCpe.copyWith(
          clearPassword2g: sentPass2g != null,
          clearPassword5g: sentPass5g != null,
        );
      }

      setState(() {
        _ssid2gController.text = resultCpe.ssid2g ?? '';
        _ssid5gController.text = resultCpe.ssid5g ?? '';
        if (sentPass2g != null) _pass2gController.clear();
        if (sentPass5g != null) _pass5gController.clear();
      });

      if (!mounted) return;

      await showDialog(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: const Color(0xFF1E1E1E),
          title: const Text('Enviado', style: TextStyle(color: Colors.white)),
          content: const Text(
            'Os dados foram enviados ao modem. Pode demorar um pouco até o equipamento aceitar as alterações.\n\n'
            'Os nomes e senhas exibidos na tela já refletem o que você editou. A rede Wi-Fi pode reiniciar em instantes.',
            style: TextStyle(color: Colors.white70),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
                Navigator.of(context).pop(resultCpe);
              },
              child: Text('OK', style: TextStyle(color: BrandColors.primary)),
            ),
          ],
        ),
      );
    } catch (e) {
      closeLoadingIfOpen();

      if (mounted) {
        showTopSnackBar(context, 
          SnackBar(
            content: Text('Erro: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: brandColor,
        title: const Text('Configurar Wi-Fi', style: TextStyle(color: Colors.white)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildSectionTitle('Rede Wi-Fi (2.4 GHz)'),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _ssid2gController,
                label: 'Nome da rede',
                icon: Icons.wifi,
              ),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _pass2gController,
                label: 'Senha',
                icon: Icons.lock_outline,
                isPassword: true,
                obscureText: _obscure2g,
                onToggleVisibility: () => setState(() => _obscure2g = !_obscure2g),
              ),
              const SizedBox(height: 32),

              _buildSectionTitle('Rede Wi-Fi (5 GHz)'),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _ssid5gController,
                label: 'Nome da rede',
                icon: Icons.wifi,
              ),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _pass5gController,
                label: 'Senha',
                icon: Icons.lock_outline,
                isPassword: true,
                obscureText: _obscure5g,
                onToggleVisibility: () => setState(() => _obscure5g = !_obscure5g),
              ),
              const SizedBox(height: 40),

              SizedBox(
                height: 50,
                child: ElevatedButton(
                  onPressed: _saveChanges,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: brandColor,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(25),
                    ),
                  ),
                  child: const Text(
                    'Salvar Alterações',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Row(
      children: [
        Icon(Icons.wifi_tethering, color: brandColor, size: 20),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(color: Colors.grey, fontSize: 14)),
      ],
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    bool isPassword = false,
    bool obscureText = false,
    VoidCallback? onToggleVisibility,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          decoration: BoxDecoration(
            color: cardBg,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white10),
          ),
          child: TextFormField(
            controller: controller,
            obscureText: obscureText,
            style: const TextStyle(color: Colors.white),
            autovalidateMode: AutovalidateMode.onUserInteraction,
            validator: (value) {
              // Allow empty (no change)
              if (value == null || value.isEmpty) {
                return null; 
              }
              // If typed, check length
              if (isPassword && value.length < 8) {
                return 'A senha deve ter pelo menos 8 caracteres';
              }
              return null;
            },
            decoration: InputDecoration(
              labelText: label,
              labelStyle: const TextStyle(color: Colors.grey),
              prefixIcon: Icon(icon, color: brandColor),
              suffixIcon: isPassword
                  ? IconButton(
                      icon: Icon(
                        obscureText ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                        color: Colors.grey,
                      ),
                      onPressed: onToggleVisibility,
                    )
                  : null,
              border: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            ),
          ),
        ),
        if (isPassword)
          Padding(
            padding: const EdgeInsets.only(left: 12, top: 4),
            child: Text(
              'Deixe em branco para manter a senha atual',
              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12),
            ),
          ),
      ],
    );
  }
}
