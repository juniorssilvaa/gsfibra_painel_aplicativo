import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../../provider.dart';
import '../../utils/user_facing_error.dart';
import '../../services/sgp_service.dart';
import '../../theme/app_branding.dart';
import '../../theme/brand_colors.dart';

class SupportScreen extends StatefulWidget {
  const SupportScreen({super.key});

  @override
  State<SupportScreen> createState() => _SupportScreenState();
}

class _SupportScreenState extends State<SupportScreen> {
  bool _isLoading = false;
  List<dynamic> _tickets = [];

  final Color brandColor = BrandColors.primary;
  Color get darkBackground => AppBranding.screenBackground(context);
  Color get cardBackground => AppBranding.cardBackground(context);
  Color get _onBg => AppBranding.onColor(darkBackground);
  Color get _onCard => AppBranding.onColor(cardBackground);
  Color get textGrey => _onCard.withValues(alpha: 0.6);

  final _formKey = GlobalKey<FormState>();
  final _messageController = TextEditingController();
  String _selectedType = '1'; // Default: Sem Acesso
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _fetchTickets();
  }

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _fetchTickets() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final appProvider = Provider.of<AppProvider>(context, listen: false);
      final sgpService = appProvider.sgpService;

      if (sgpService == null) throw Exception("Serviço SGP não inicializado");

      String contractId = appProvider.userContract['id']?.toString() ?? '';
      final cpf = appProvider.cpf ?? '';
      final password = appProvider.centralPassword ?? '';

      if (contractId.isEmpty) {
        final contracts = await sgpService.getContratos(cpf, password);
        if (contracts.isNotEmpty) {
           contractId = contracts[0]['id']?.toString() ?? contracts[0]['contrato']?.toString() ?? '';
        }
      }

      if (contractId.isNotEmpty) {
        final data = await sgpService.getSupportTickets(cpf, password, contractId);
        
        // Filtrar chamados pelo contrato selecionado
        final filteredTickets = (data as List).where((ticket) {
          if (ticket is! Map) return false;
          final ticketContratoId = (ticket['oc_contrato_id'] ?? ticket['contrato_id'] ?? ticket['contrato'] ?? ticket['id_contrato'])?.toString();
          return ticketContratoId != null && ticketContratoId.trim() == contractId.trim();
        }).toList();

        setState(() {
          _tickets = filteredTickets;
        });
      }
    } catch (e) {
      if (mounted) {
        showTopSnackBar(context, 
          SnackBar(content: Text(UserFacingError.from(e, fallback: 'Não foi possível carregar os chamados agora.'))),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _submitTicket() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isSubmitting = true);
    Navigator.of(context).pop(); // Close dialog

    try {
      final appProvider = Provider.of<AppProvider>(context, listen: false);
      final sgpService = appProvider.sgpService;

      if (sgpService == null) throw Exception("Serviço SGP não inicializado");

      String contractId = appProvider.userContract['id']?.toString() ?? '';
      final cpf = appProvider.cpf ?? '';
      final password = appProvider.centralPassword ?? '';

      if (contractId.isEmpty) {
        final contracts = await sgpService.getContratos(cpf, password);
        if (contracts.isNotEmpty) {
           contractId = contracts[0]['id']?.toString() ?? contracts[0]['contrato']?.toString() ?? '';
        }
      }

      final result = await sgpService.openSupportTicket(
        cpf, 
        password, 
        contractId, 
        _selectedType,
        '${_messageController.text} - Chamado aberto Via app'
      );

      if (result.containsKey('error')) {
        throw Exception(result['error']);
      }

      showTopSnackBar(context, 
        const SnackBar(content: Text('Chamado aberto com sucesso!'), backgroundColor: Colors.green),
      );
      
      _messageController.clear();
      _fetchTickets(); // Refresh list

    } catch (e) {
      showTopSnackBar(context, 
        SnackBar(content: Text(UserFacingError.from(e, fallback: 'Não foi possível abrir o chamado agora.')), backgroundColor: Colors.red),
      );
    } finally {
      setState(() => _isSubmitting = false);
    }
  }

  void _openNewTicketDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: cardBackground,
        title: Text('Novo Chamado', style: TextStyle(color: _onCard)),
        content: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                value: _selectedType,
                dropdownColor: cardBackground,
                style: TextStyle(color: _onCard),
                decoration: InputDecoration(
                  labelText: 'Tipo de Ocorrência',
                  labelStyle: TextStyle(color: Colors.grey),
                  enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: Colors.grey)),
                  focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: BrandColors.primary)),
                ),
                items: const [
                  DropdownMenuItem(value: '1', child: Text('Sem Acesso')),
                  DropdownMenuItem(value: '2', child: Text('Internet Lenta')),
                ],
                onChanged: (value) {
                  if (value != null) {
                    setState(() => _selectedType = value);
                  }
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _messageController,
                style: TextStyle(color: _onCard),
                decoration: InputDecoration(
                  labelText: 'Mensagem',
                  labelStyle: TextStyle(color: Colors.grey),
                  enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: Colors.grey)),
                  focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: BrandColors.primary)),
                ),
                maxLines: 3,
                validator: (value) => value == null || value.isEmpty ? 'Informe a mensagem' : null,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancelar', style: TextStyle(color: Colors.grey)),
          ),
          ElevatedButton(
            onPressed: _submitTicket,
            style: ElevatedButton.styleFrom(backgroundColor: brandColor),
            child: const Text('Enviar', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: darkBackground,
      appBar: AppBar(
        backgroundColor: AppBranding.headerBackground,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text('SUPORTE', style: TextStyle(fontWeight: FontWeight.bold, color: AppBranding.onHeader)),
        centerTitle: true,
        leading: IconButton(
          icon: Icon(Icons.arrow_back, color: AppBranding.onHeader),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator(color: _onBg))
          : _tickets.isEmpty
              ? Center(child: Text('Nenhum chamado encontrado.', style: TextStyle(color: _onBg.withValues(alpha: 0.75))))
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _tickets.length,
                  itemBuilder: (context, index) {
                    final ticket = _tickets[index];
                    // Map fields based on API response
                    final protocol = ticket['oc_protocolo']?.toString() ?? ticket['protocolo']?.toString() ?? 'N/A';
                    final subject = ticket['oc_tipo_descricao'] ?? ticket['assunto'] ?? 'Sem Assunto';
                    final description = ticket['oc_conteudo'] ?? ticket['mensagem'] ?? ticket['descricao'] ?? '';
                    
                    // Date parsing
                    String date = 'Data desconhecida';
                    final rawDate = ticket['oc_data_cadastro'] ?? ticket['data_abertura'] ?? ticket['data_cadastro'];
                    if (rawDate != null) {
                      date = rawDate.toString();
                    }
                    
                    final status = ticket['oc_status_descricao'] ?? ticket['status'] ?? 'Aberto';
                    
                    return _buildTicketCard(protocol, subject, description, date, status);
                  },
                ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNewTicketDialog,
        backgroundColor: brandColor,
        icon: const Icon(Icons.add, color: Colors.white),
        label: const Text('NOVO CHAMADO', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
      ),
    );
  }

  Widget _buildTicketCard(String protocol, String subject, String description, String date, String status) {
    Color statusColor = Colors.orange;
    if (status.toLowerCase().contains('fechado') || status.toLowerCase().contains('finalizado') || status.toLowerCase().contains('resolvido')) {
      statusColor = Colors.green;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cardBackground,
        borderRadius: BorderRadius.circular(12),
        border: Border(
            left: BorderSide(color: brandColor, width: 4),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.12),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Protocolo: $protocol',
                style: TextStyle(color: textGrey, fontSize: 12),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: statusColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  status.toUpperCase(),
                  style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            subject,
            style: TextStyle(color: _onCard, fontSize: 16, fontWeight: FontWeight.bold),
          ),
          if (description.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              description,
              style: TextStyle(color: textGrey, fontSize: 14),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.bottomRight,
            child: Text(
              date,
              style: TextStyle(color: textGrey, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }
}
