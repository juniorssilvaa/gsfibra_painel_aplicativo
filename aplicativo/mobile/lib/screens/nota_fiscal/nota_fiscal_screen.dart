import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../provider.dart';
import '../../theme/brand_colors.dart';

class NotaFiscalScreen extends StatefulWidget {
  const NotaFiscalScreen({super.key});

  @override
  State<NotaFiscalScreen> createState() => _NotaFiscalScreenState();
}

class _NotaFiscalScreenState extends State<NotaFiscalScreen> {
  bool _isLoading = true;
  List<dynamic> _notes = [];
  
  final Color brandColor = BrandColors.primary;
  final Color cardBg = const Color(0xFF111111);

  @override
  void initState() {
    super.initState();
    _loadNotes();
  }

  Future<void> _loadNotes() async {
    setState(() => _isLoading = true);
    try {
      final provider = context.read<AppProvider>();
      if (provider.cpf != null && provider.centralPassword != null) {
        final contractId = (provider.userContract['id'] ?? provider.userContract['contract_id'])?.toString();
        if (contractId != null) {
          final notes = await provider.sgpService?.getFiscalNotes(
            provider.cpf!,
            provider.centralPassword!,
            contractId,
          );
          
          if (notes != null) {
            setState(() {
              _notes = notes;
            });
          }
        }
      }
    } catch (e) {
      debugPrint('Erro ao carregar notas fiscais: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: brandColor,
        title: const Text('Notas Fiscais', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
        centerTitle: true,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator(color: brandColor))
          : _notes.isEmpty
               ? _buildEmptyState()
               : RefreshIndicator(
                  onRefresh: _loadNotes,
                  color: brandColor,
                  child: ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _notes.length,
                    itemBuilder: (context, index) {
                      return _buildNoteItem(_notes[index]);
                    },
                  ),
                ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.receipt_long, size: 80, color: Colors.white24),
          const SizedBox(height: 16),
          const Text(
            'Nenhuma nota fiscal encontrada',
            style: TextStyle(color: Colors.grey, fontSize: 16),
          ),
        ],
      ),
    );
  }

  Future<void> _openNoteLink(String? url) async {
    if (url == null || url.isEmpty) {
      if (mounted) {
        showTopSnackBar(context, const SnackBar(content: Text('Link da nota não disponível')));
      }
      return;
    }
    final uri = Uri.parse(url);
    try {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        if (!await launchUrl(uri, mode: LaunchMode.platformDefault)) {
           if (mounted) {
             showTopSnackBar(context, const SnackBar(content: Text('Não foi possível abrir a nota fiscal')));
           }
        }
      }
    } catch (e) {
      debugPrint('Erro ao abrir link: $e');
      if (mounted) {
        showTopSnackBar(context, const SnackBar(content: Text('Erro ao tentar abrir a nota fiscal')));
      }
    }
  }

  Widget _buildNoteItem(Map<String, dynamic> note) {
    // Formatação de Data
    String dataEmissao = '--/--/----';
    try {
      final rawDate = note['data_emissao'];
      if (rawDate != null) {
        final parsedDate = DateTime.parse(rawDate);
        dataEmissao = DateFormat('dd/MM/yyyy').format(parsedDate);
      }
    } catch (_) {}

    final String numero = note['numero']?.toString() ?? 'N/A';
    final double valorRaw = double.tryParse(note['valortotal']?.toString() ?? '0') ?? 0.0;
    final String valor = valorRaw.toStringAsFixed(2).replaceAll('.', ',');

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withOpacity(0.05)),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Cabeçalho: Ícone + Número + Empresa (Centrados)
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 50,
                height: 50,
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(Icons.receipt_long_rounded, color: brandColor, size: 28),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Text(
                      'Nota Fiscal Nº $numero',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      note['empresa_razao_social'] ?? 'Provedor de Internet',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: brandColor.withOpacity(0.8),
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 66), // Espaço compensatório para o ícone (50 + gap 16)
            ],
          ),
          
          const SizedBox(height: 24),
          
          // Meio: Datas e Valores
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'DATA DE EMISSÃO',
                      style: TextStyle(
                        color: brandColor.withOpacity(0.7),
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      dataEmissao,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      'VALOR TOTAL',
                      style: TextStyle(
                        color: brandColor.withOpacity(0.7),
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'R\$ $valor',
                      style: TextStyle(
                        color: brandColor,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          
          const SizedBox(height: 24),
          
          // Rodapé: Botão de Download (Estilo Login)
          ElevatedButton.icon(
            onPressed: () => _openNoteLink(note['link']),
            icon: const Icon(Icons.download_rounded, size: 20),
            label: const Text(
              'BAIXAR DOCUMENTO FISCAL',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 13,
                letterSpacing: 0.5,
              ),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: brandColor,
              foregroundColor: Colors.white,
              minimumSize: const Size(double.infinity, 50),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              elevation: 0,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTag(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFF222222),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.white60,
          fontSize: 9,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}