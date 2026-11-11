import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../provider.dart';
import '../../theme/brand_colors.dart';

class ContratosScreen extends StatefulWidget {
  const ContratosScreen({super.key});

  @override
  State<ContratosScreen> createState() => _ContratosScreenState();
}

class _ContratosScreenState extends State<ContratosScreen> {
  bool _isLoading = true;
  String? _errorMessage;
  List<Map<String, dynamic>> _signatures = [];

  @override
  void initState() {
    super.initState();
    _loadSignatures();
  }

  Future<void> _loadSignatures() async {
    final provider = context.read<AppProvider>();
    final cpf = provider.cpf;
    final sgp = provider.sgpService;
    String? pass = provider.centralPassword;

    if (cpf == null || sgp == null) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Sessão inválida.';
      });
      return;
    }

    pass ??= cpf;

    try {
      // Busca contratos com o parâmetro assinatura_eletronica=1
      List<dynamic> contratos = [];
      try {
        contratos = await sgp.getContratos(cpf, pass);
      } catch (_) {
        try {
          contratos = await sgp.getContratos(cpf, cpf);
        } catch (_) {}
      }

      if (contratos.isEmpty) {
        setState(() {
          _isLoading = false;
          _errorMessage = 'Nenhum contrato encontrado.';
        });
        return;
      }

      final List<Map<String, dynamic>> parsedSignatures = [];

      for (var c in contratos) {
        if (c is! Map) continue;

        // Verifica se há assinaturas eletrônicas
        if (c['assinaturaEletronica'] != null && c['assinaturaEletronica'] is List) {
          final assinaturas = c['assinaturaEletronica'] as List;
          
          for (var ass in assinaturas) {
            if (ass is! Map) continue;
            
            // Extrai informações da assinatura
            final tipoDocumento = ass['tipo_documento'] ?? 'Documento';
            final statusAtual = _resolveStatus(ass);
            
            // Tenta obter observação e data do status 'Assinado' ou do status atual
            String observacao = '';
            String dataAssinatura = '';
            
            if (ass['status'] != null && ass['status'] is List) {
              final statusList = ass['status'] as List;
              // Procura pelo status 'Assinado'
              final assinadoStatus = statusList.firstWhere(
                (s) => s['status'] == 'Assinado',
                orElse: () => null,
              );
              
              if (assinadoStatus != null) {
                observacao = assinadoStatus['observacao'] ?? '';
                dataAssinatura = assinadoStatus['data_cadastro'] ?? '';
              } else {
                 // Se não achar 'Assinado', pega do primeiro status (mais recente)
                 if (statusList.isNotEmpty) {
                    observacao = statusList.first['observacao'] ?? '';
                    dataAssinatura = statusList.first['data_cadastro'] ?? '';
                 }
              }
            }
            
            // Se ainda não tiver data, tenta pegar de data_status_atual
            if (dataAssinatura.isEmpty) {
              dataAssinatura = ass['data_status_atual'] ?? '';
            }

            // URLs
            String urlAssinatura = '';
            String urlAssinado = '';
            
            if (ass['cliente'] != null && ass['cliente'] is Map) {
               urlAssinatura = ass['cliente']['url_assinatura'] ?? '';
            }
            
            if (ass['documento'] != null && ass['documento'] is Map) {
               urlAssinado = ass['documento']['url_assinado'] ?? '';
            }

            // Se não tiver URL de assinatura no cliente, tenta pegar da empresa
             if (urlAssinatura.isEmpty && ass['empresa'] != null && ass['empresa'] is Map) {
               urlAssinatura = ass['empresa']['url_assinatura'] ?? '';
            }


            parsedSignatures.add({
              'tipo_documento': tipoDocumento,
              'status': statusAtual,
              'observacao': observacao,
              'data_assinatura': dataAssinatura,
              'url_assinatura': urlAssinatura,
              'url_assinado': urlAssinado,
            });
          }
        }
      }

      setState(() {
        _signatures = parsedSignatures;
        _isLoading = false;
        if (_signatures.isEmpty) {
          _errorMessage = 'Nenhuma assinatura eletrônica encontrada.';
        }
      });
      
    } catch (e) {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Erro ao carregar assinaturas: $e';
      });
    }
  }

  String _resolveStatus(Map ass) {
    final atual = (ass['status_atual'] ?? ass['statusAtual'] ?? '').toString().trim();
    if (atual.isNotEmpty) return atual;
    final list = ass['status'];
    if (list is List && list.isNotEmpty && list.first is Map) {
      final first = (list.first['status'] ?? '').toString().trim();
      if (first.isNotEmpty) return first;
    }
    return 'Desconhecido';
  }

  bool _isProcessing(String status) {
    final s = status.toLowerCase();
    return s.contains('processamento') || s.contains('pendente') || s.contains('aguardando');
  }

  bool _isCancelled(String status) {
    final s = status.toLowerCase();
    return s.contains('cancel') || s.contains('recus') || s.contains('expir');
  }

  bool _isSigned(String status) {
    final s = status.toLowerCase();
    return s.contains('assinado') || s.contains('finalizado');
  }

  Color _statusColor(String status) {
    if (_isSigned(status)) return Colors.green;
    if (_isCancelled(status)) return Colors.red;
    return Colors.orange;
  }

  String _assinaturaButtonLabel(String status) {
    if (_isProcessing(status)) return 'Assinar Documento';
    if (_isCancelled(status)) return 'Documento cancelado';
    return 'Documento Assinado';
  }

  IconData _assinaturaButtonIcon(String status) {
    if (_isProcessing(status)) return Icons.edit_document;
    if (_isCancelled(status)) return Icons.block;
    return Icons.description;
  }

  Future<void> _launchUrl(String urlString) async {
    if (urlString.isEmpty) return;
    final urlStringTrimmed = urlString.trim();
    final Uri url = Uri.parse(urlStringTrimmed);
    if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
       if (mounted) {
         showTopSnackBar(context, 
           SnackBar(content: Text('Não foi possível abrir o link: $urlStringTrimmed')),
         );
       }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final brandColor = BrandColors.primary;
    const backgroundColor = Color(0xFF121212);

    return Scaffold(
      backgroundColor: isDark ? backgroundColor : Colors.grey[50],
      appBar: AppBar(
        backgroundColor: brandColor,
        elevation: 0,
        title: const Text(
          'CONTRATOS ASSINADOS', 
          style: TextStyle(
            fontWeight: FontWeight.bold, 
            color: Colors.white
          )
        ),
        centerTitle: true,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator(color: brandColor))
          : _errorMessage != null
               ? Center(child: Text(_errorMessage!, style: TextStyle(color: isDark ? Colors.white : Colors.black)))
               : _buildList(isDark, brandColor),
    );
  }

  Widget _buildList(bool isDark, Color brandColor) {
    if (_signatures.isEmpty) {
      return Center(
        child: Text(
          'Nenhum documento encontrado', 
          style: TextStyle(color: isDark ? Colors.white70 : Colors.grey[600])
        ),
      );
    }
    
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _signatures.length,
      itemBuilder: (context, index) {
        final sig = _signatures[index];
        final tipo = sig['tipo_documento'] ?? 'Documento';
        final status = sig['status'] ?? '-';
        final obs = sig['observacao'] ?? '';
        final data = sig['data_assinatura'] ?? '';
        final urlAssinatura = sig['url_assinatura']?.toString().trim() ?? '';
        final urlAssinado = sig['url_assinado']?.toString().trim() ?? '';

        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF1E1E1E) : Colors.white,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.05),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Ícone em destaque (como no menu)
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: brandColor.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        Icons.description_rounded,
                        color: brandColor,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 16),
                    
                    // Conteúdo Principal
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Text(
                                  tipo,
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                    color: isDark ? Colors.white : Colors.black,
                                  ),
                                ),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: _statusColor(status).withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  status,
                                  style: TextStyle(
                                    color: _statusColor(status),
                                    fontWeight: FontWeight.bold,
                                    fontSize: 10,
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          
                          if (obs.isNotEmpty) ...[
                            Text(
                              obs.replaceFirst('Assinado Por: ', ''),
                              style: TextStyle(
                                color: isDark ? Colors.white70 : Colors.grey[700],
                                fontSize: 13,
                                fontWeight: FontWeight.w500
                              ),
                            ),
                            const SizedBox(height: 4),
                          ],
                          
                          if (data.isNotEmpty) ...[
                            Row(
                              children: [
                                Icon(Icons.calendar_today, 
                                  color: isDark ? Colors.white54 : Colors.grey[500], 
                                  size: 12
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  data,
                                  style: TextStyle(
                                    color: isDark ? Colors.white54 : Colors.grey[500],
                                    fontSize: 12
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
                
                // Botões de Ação
                if (urlAssinatura.isNotEmpty || urlAssinado.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  const Divider(height: 1),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      if (urlAssinatura.isNotEmpty)
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: () => _launchUrl(urlAssinatura),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: _isCancelled(status)
                                  ? (isDark ? Colors.grey[800] : Colors.grey[600])
                                  : brandColor,
                              foregroundColor: Colors.white,
                              elevation: 0,
                              padding: const EdgeInsets.symmetric(vertical: 10),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                            icon: Icon(_assinaturaButtonIcon(status), size: 16),
                            label: Text(_assinaturaButtonLabel(status)),
                          ),
                        ),
                      
                      if (urlAssinatura.isNotEmpty && urlAssinado.isNotEmpty)
                        const SizedBox(width: 12),

                      if (urlAssinado.isNotEmpty)
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: () => _launchUrl(urlAssinado),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: brandColor,
                              foregroundColor: Colors.white,
                              elevation: 0,
                              padding: const EdgeInsets.symmetric(vertical: 10),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                            icon: const Icon(Icons.visibility, size: 16),
                            label: const Text('Ver Contrato'),
                          ),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}
