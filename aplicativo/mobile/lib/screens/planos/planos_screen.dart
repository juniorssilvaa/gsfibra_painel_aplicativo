import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../config.dart';
import '../../utils/user_facing_error.dart';
import '../../theme/brand_colors.dart';
import '../../theme/app_branding.dart';

class PlanosScreen extends StatefulWidget {
  const PlanosScreen({super.key});

  @override
  State<PlanosScreen> createState() => _PlanosScreenState();
}

class _PlanosScreenState extends State<PlanosScreen> {
  final Color brandColor = BrandColors.primary;
  final Color cardBg = const Color(0xFF111111);
  
  List<dynamic> _plans = [];
  bool _isLoading = true;
  String? _error;
  final Set<int> _expandedIndices = {};

  @override
  void initState() {
    super.initState();
    _fetchPlans();
  }

  Future<void> _fetchPlans() async {
    try {
      final url = AppConfig.apiUrl('public/plans/');
      final response = await http.get(url, headers: AppConfig.apiHeaders);

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        setState(() {
          _plans = data;
          _isLoading = false;
        });
      } else {
        setState(() {
          _error = UserFacingError.planos;
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('Erro ao carregar planos: $e');
      setState(() {
        _error = UserFacingError.planos;
        _isLoading = false;
      });
    }
  }

  Future<void> _contactConsultant({String? planName}) async {
    String message = 'Olá, gostaria de saber mais sobre os planos de internet.';
    if (planName != null) {
      message = 'Olá, tenho interesse no plano $planName.';
    }
    final encodedMessage = Uri.encodeComponent(message);
    final digits = AppBranding.whatsappDigits;
    final waUrl = Uri.parse("https://wa.me/$digits?text=$encodedMessage");
    if (await canLaunchUrl(waUrl)) {
      await launchUrl(waUrl, mode: LaunchMode.externalApplication);
    } else {
      if (mounted) _showTopBanner('Não foi possível abrir o WhatsApp');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: brandColor,
        title: const Text('Planos', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
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
      return Center(child: CircularProgressIndicator(color: brandColor));
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, color: brandColor, size: 48),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Text(
                _error!,
                style: const TextStyle(color: Colors.white70, fontSize: 15, height: 1.4),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _isLoading = true;
                  _error = null;
                });
                _fetchPlans();
              },
              style: ElevatedButton.styleFrom(backgroundColor: brandColor),
              child: const Text('Tentar Novamente', style: TextStyle(color: Colors.white)),
            )
          ],
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_plans.isEmpty)
          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 40),
              child: Text('Nenhum plano disponível no momento.', style: TextStyle(color: Colors.grey)),
            ),
          )
        else
          ..._plans.asMap().entries.map((entry) {
            final index = entry.key;
            final plan = entry.value;
            return _buildPlanCard(
              context,
              index: index,
              name: plan['name'] ?? 'Plano',
              speed: plan['download_speed']?.toString() ?? '0',
              upload: plan['upload_speed']?.toString() ?? '0',
              price: plan['price_display'] ?? '0,00',
              features: (plan['description'] as String? ?? '').split('\n').where((s) => s.isNotEmpty).toList(),
              type: plan['type'] ?? 'FIBRA',
              isExpanded: _expandedIndices.contains(index),
              onToggleDetails: () {
                setState(() {
                  if (_expandedIndices.contains(index)) {
                    _expandedIndices.remove(index);
                  } else {
                    _expandedIndices.add(index);
                  }
                });
              },
            );
          }),
        
        const SizedBox(height: 20),
        
        // Card de Ajuda
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1E1E),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            children: [
              const Text(
                'Precisa de ajuda para escolher?',
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              const Text(
                'Entre em contato conosco e fale com um de nossos consultores',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey, fontSize: 14),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => _contactConsultant(),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: brandColor),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
                  ),
                  child: Text('Falar com consultor', style: TextStyle(color: brandColor, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
      ],
    );
  }

  Widget _buildPlanCard(
    BuildContext context, {
    required int index,
    required String name,
    required String speed,
    required String upload,
    required String price,
    required List<String> features,
    required String type,
    required bool isExpanded,
    required VoidCallback onToggleDetails,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E1E),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        children: [
          // Header
          Padding(
            padding: const EdgeInsets.all(24.0),
            child: Row(
              children: [
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    color: brandColor,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.wifi, color: Colors.white, size: 32),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name.toUpperCase(),
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        decoration: BoxDecoration(
                          color: brandColor,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          type.toUpperCase(),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          
          const Divider(color: Colors.white10, height: 1),
          
          // Velocidades
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 24),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildSpeedItem(Icons.arrow_downward, 'Down $speed Mb/s'),
                _buildSpeedItem(Icons.arrow_upward, 'Up $upload Mb/s'),
              ],
            ),
          ),
          
          const Divider(color: Colors.white10, height: 1),
          
          // Preço e Ação
          Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              children: [
                const Text('Por apenas', style: TextStyle(color: Colors.grey, fontSize: 12)),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 8),
                  decoration: BoxDecoration(
                    color: brandColor,
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: Text(
                    price,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                
                // Botão Detalhes
                TextButton(
                  onPressed: onToggleDetails,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        isExpanded ? 'Ocultar detalhes' : 'Detalhes',
                        style: TextStyle(
                          color: brandColor,
                          fontSize: 14,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                      const SizedBox(width: 4),
                      Icon(
                        isExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                        color: brandColor,
                        size: 16,
                      ),
                    ],
                  ),
                ),
                
                // Área de Detalhes Expandida
                if (isExpanded) ...[
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: features.map((f) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(Icons.check_circle, color: brandColor, size: 18),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                f, 
                                style: const TextStyle(color: Colors.white70, fontSize: 14),
                              ),
                            ),
                          ],
                        ),
                      )).toList(),
                    ),
                  ),
                ],

                const SizedBox(height: 16),
                
                // Botão Quero este
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () => _contactConsultant(planName: name),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: brandColor,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      elevation: 0,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: const [
                        Text('Quero este', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                        SizedBox(width: 8),
                        Icon(Icons.arrow_forward, size: 20),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _showTopBanner(String message) {
    showTopMessage(message, duration: const Duration(seconds: 2));
  }

  Widget _buildSpeedItem(IconData icon, String text) {
    return Row(
      children: [
        Icon(icon, color: brandColor, size: 16),
        const SizedBox(width: 8),
        Text(
          text,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
