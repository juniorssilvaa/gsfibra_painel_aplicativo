import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:flutter_svg/flutter_svg.dart';
import '../../config.dart';
import '../../provider.dart';
import '../../theme/app_branding.dart';
import '../../theme/brand_colors.dart';
import '../../utils/user_facing_error.dart';
import '../../widgets/brand_login_background.dart';

import '../../services/sgp_service.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _cpfController = TextEditingController();
  bool _isLoading = false;
  bool _rememberMe = false;
  String? _savedName;
  String? _savedCpf;
  String? _savedPassword;

  Color get brandColor => Theme.of(context).colorScheme.primary;

  @override
  void initState() {
    super.initState();
    _loadSavedCpf();
  }

  Future<void> _loadSavedCpf() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedCpf = prefs.getString('saved_cpf');
      final savedName = prefs.getString('saved_name');
      final savedPassword = prefs.getString('centralPassword');
      
      if (savedCpf != null && savedCpf.isNotEmpty) {
        setState(() {
          _cpfController.text = savedCpf;
          _savedCpf = savedCpf;
          _savedName = savedName;
          _savedPassword = savedPassword;
          _rememberMe = true;
        });
      }
    } catch (e) {
      debugPrint('Erro ao carregar CPF salvo: $e');
    }
  }

  String _maskCpfCnpj(String value) {
    // Remove caracteres não numéricos
    final digits = value.replaceAll(RegExp(r'\D'), '');
    
    if (digits.length == 11) {
      // CPF: 123.456.789-01 -> ***.456.789-**
      return '***.${digits.substring(3, 6)}.${digits.substring(6, 9)}-**';
    } else if (digits.length == 14) {
      // CNPJ: 12.345.678/0001-99 -> **.***.678/0001-**
      return '**.***.${digits.substring(5, 8)}/${digits.substring(8, 12)}-**';
    }
    return value;
  }

  Future<void> _handleLogin() async {
    final cpf = _cpfController.text.trim();
    if (cpf.isEmpty) {
      _showTopErrorBanner('Por favor, informe seu CPF/CNPJ');
      return;
    }

    setState(() => _isLoading = true);

      // 1. Verificar Status do Provedor / cliente
    try {
      final cpfDigits = cpf.replaceAll(RegExp(r'[^\d]'), '');
      final configBase = AppConfig.apiUrl('public/config/');
      final configUrl = configBase.replace(queryParameters: {
        ...configBase.queryParameters,
        'cpf': cpfDigits,
      });
      final configResponse = await http.get(
        configUrl,
        headers: AppConfig.apiHeaders,
      ).timeout(const Duration(seconds: 5));
      Map<String, dynamic>? configData;
      if (configResponse.body.isNotEmpty) {
        try {
          configData = json.decode(configResponse.body) as Map<String, dynamic>?;
        } catch (_) {}
      }

      if (configData?['user_blocked'] == true) {
        setState(() => _isLoading = false);
        _showUserBlockedDialog();
        return;
      }
      final providerBlocked = configData?['provider_blocked'] == true ||
          configData?['is_blocked'] == true ||
          configData?['is_active'] == false ||
          (configResponse.statusCode == 403 && configData?['user_blocked'] != true);
      if (providerBlocked) {
        setState(() => _isLoading = false);
        if (mounted) {
          context.read<AppProvider>().setProviderBlocked(true);
        }
        return;
      }
    } catch (e) {
      debugPrint('Erro ao verificar status do provedor: $e');
      // Continua o login em caso de erro de rede na verificação
    }

    // Ocultar teclado
    FocusScope.of(context).unfocus();

    try {
      // 1. Salvar ou remover CPF das preferências (CPF salvamos logo no início se marcado)
      final prefs = await SharedPreferences.getInstance();
      if (_rememberMe) {
        await prefs.setString('saved_cpf', cpf);
      } else {
        await prefs.remove('saved_cpf');
        await prefs.remove('saved_name');
      }

      final provider = context.read<AppProvider>();
      
      // Inicializar serviço SGP para consulta
      final sgpService = SGPService(
        providerToken: AppConfig.apiToken,
      );

      // 1. Buscar dados do cliente no SGP
      Map<String, dynamic>? clientData;
      String? extractedPassword;
      List<dynamic> contratos = [];
      Map<String, dynamic>? result;

      try {
        // 1. Busca inicial para obter a senha da central
        debugPrint('LOGIN: Iniciando busca via cliente/consulta...');
        result = await sgpService.getClientByCpf(cpf);
        debugPrint('LOGIN: RAW Consulta Cliente: $result');
        
        if (result != null) {
          // 1. Tentar extrair senha do objeto principal
          extractedPassword = result['contratoCentralSenha'] ?? 
                             result['senha_central'] ?? 
                             result['senha'] ?? 
                             result['central_senha'] ?? 
                             result['password'];
                             
          // 2. Se não achou, tentar extrair do primeiro contrato da lista (comum no SGP)
          if (extractedPassword == null && result['contratos'] is List && (result['contratos'] as List).isNotEmpty) {
            final firstContract = (result['contratos'] as List).first;
            extractedPassword = firstContract['contratoCentralSenha'] ?? 
                               firstContract['senha_central'] ?? 
                               firstContract['senha'] ?? 
                               firstContract['password'];
          }
          
          // 3. Fallback para senha salva se ainda for null
          extractedPassword ??= _savedPassword;
                             
          debugPrint('LOGIN: Senha extraída: ${extractedPassword != null ? "SUCESSO" : "NÃO ENCONTRADA"}');
        }

        // 2. Buscar a lista completa de contratos usando a senha (sempre que possível)
        if (extractedPassword != null || (cpf == _savedCpf && _savedPassword != null)) {
          final pass = extractedPassword ?? _savedPassword!;
          debugPrint('LOGIN: Buscando lista completa via central/contratos...');
          try {
            final list = await sgpService.getContratos(cpf, pass);
            debugPrint('LOGIN: RAW Lista Central: $list');
            if (list.isNotEmpty) {
              contratos = list;
              extractedPassword = pass;
              debugPrint('LOGIN: ${contratos.length} contratos carregados da Central.');
            }
          } catch (e) {
            debugPrint('LOGIN: Erro ao carregar da Central: $e');
          }
        }

        // 3. Fallbacks se a Central falhar ou não houver senha
        if (contratos.isEmpty) {
          if (result != null && result.containsKey('contratos') && result['contratos'] is List) {
            contratos = result['contratos'];
            debugPrint('LOGIN: Usando contratos do fallback Consulta (URA).');
          } else {
            debugPrint('LOGIN: Tentando fallback final com CPF como senha...');
            try {
              final centralResult = await sgpService.getContratos(cpf, cpf);
              if (centralResult.isNotEmpty) {
                contratos = centralResult;
                extractedPassword = cpf;
                debugPrint('LOGIN: Contratos encontrados via fallback CPF.');
              }
            } catch (_) {}
          }
        }

        if (contratos.isNotEmpty) {
           // 1. Mapear TODOS os contratos disponíveis
           final List<Map<String, dynamic>> allMappedContracts = [];
           
           for (var c in contratos) {
             // Construção robusta do endereço (usando a lógica do provider)
             String logradouro = (c['endereco_logradouro'] ?? c['logradouro'] ?? '').toString().trim();
             String numero = (c['endereco_numero'] ?? c['numero'] ?? 'S/N').toString().trim();
             String bairro = (c['endereco_bairro'] ?? c['bairro'] ?? '').toString().trim();
             
             // Suporte a endereço aninhado se disponível
             if (logradouro.isEmpty && c['endereco_instalacao'] is Map) {
                final ei = c['endereco_instalacao'] as Map;
                logradouro = (ei['logradouro'] ?? '').toString();
                numero = (ei['numero'] ?? 'S/N').toString();
                bairro = (ei['bairro'] ?? '').toString();
             }

             String endereco = logradouro;
             if (numero.isNotEmpty && numero != '0') endereco += ', $numero';
             if (bairro.isNotEmpty) endereco += ' - $bairro';
             if (endereco.isEmpty) endereco = 'Endereço não informado';
             
             String dataCadastro = c['dataCadastro'] ?? c['data_cadastro'] ?? '24/10/2024';
             if (dataCadastro.contains(' ')) {
               dataCadastro = dataCadastro.split(' ')[0];
             }

             allMappedContracts.add({
               'id': c['id']?.toString() ?? c['contratoId']?.toString() ?? c['contrato']?.toString() ?? '1',
               'status': c['contratoStatusDisplay'] ?? c['status'] ?? 'ATIVO',
               'plan_name': c['planointernet'] ?? c['servico_plano'] ?? 'PLANO INTERNET',
               'contract_due_day': c['cobVencimento']?.toString() ?? c['vencimento']?.toString() ?? '30',
               'registration_date': dataCadastro,
               'address': endereco,
               'expiry_date': '29/05/2025', 
               'last_invoice_value': '0,00', 
               'last_invoice_due': '--/--/----',
                'last_invoice_status': 'pending',
                'login': c['login'],
                'pppoe_login': c['pppoe_login'],
                'servico_login': c['servico_login'],
                'razaoSocial': c['razaoSocial'] ?? c['razaosocial'] ?? c['razao_social'] ?? c['nomeCliente'] ?? c['nome'],
             });
           }

           // 2. Permitir seleção se houver mais de um
           Map<String, dynamic> selectedContract;
           if (allMappedContracts.length > 1) {
              debugPrint('LOGIN: Exibindo modal de seleção para ${allMappedContracts.length} contratos');
              // Ocultar loading temporariamente para mostrar o dialog
              setState(() => _isLoading = false);
              
              final selection = await showModalBottomSheet<Map<String, dynamic>>(
                context: context,
                isScrollControlled: true,
                backgroundColor: Colors.transparent,
                builder: (context) => Container(
                  height: MediaQuery.of(context).size.height * 0.7,
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  decoration: const BoxDecoration(
                    color: Color(0xFF121212),
                    borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
                  ),
                  child: Column(
                    children: [
                      const SizedBox(height: 12),
                      Container(
                        width: 40,
                        height: 4,
                        decoration: BoxDecoration(
                          color: Colors.white24,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                      const SizedBox(height: 24),
                      const Text(
                        'SELECIONE O CONTRATO',
                        style: TextStyle(
                          fontSize: 18, 
                          fontWeight: FontWeight.bold, 
                          color: Colors.white,
                          letterSpacing: 1.2,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Encontramos mais de um vínculo para você',
                        style: TextStyle(color: Colors.grey[500], fontSize: 13),
                      ),
                      const SizedBox(height: 24),
                      Expanded(
                        child: ListView.builder(
                          itemCount: allMappedContracts.length,
                          itemBuilder: (context, index) {
                            final contract = allMappedContracts[index];
                            final id = contract['id'].toString();
                            final status = contract['status']?.toString().toUpperCase() ?? 'ATIVO';
                            final plano = contract['plan_name'] ?? 'PLANO INTERNET';
                            final address = contract['address'] ?? 'Endereço não informado';
                            
                            // Lógica atualizada: Verifica se é SUSPENSO ou CANCELADO (status 3 costuma ser cancelado)
                            // Se o texto contiver "CANCELADO", também considera
                            final isSuspended = status.contains('SUSPENSO');
                            final isCanceled = status.contains('CANCELADO') || status == '3';
                            
                            // Define a cor e o texto do status
                            final Color statusColor = (isSuspended || isCanceled) ? Colors.red : Colors.green;
                            final String statusText = isCanceled ? 'CANCELADO' : status;

                            return Container(
                              margin: const EdgeInsets.only(bottom: 16),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1E1E1E),
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(color: Colors.white10),
                              ),
                              child: Material(
                                color: Colors.transparent,
                                child: InkWell(
                                  onTap: () => Navigator.pop(context, contract),
                                  borderRadius: BorderRadius.circular(16),
                                  child: Padding(
                                    padding: const EdgeInsets.all(16),
                                    child: Row(
                                      children: [
                                        Container(
                                          padding: const EdgeInsets.all(10),
                                          decoration: BoxDecoration(
                                            color: brandColor,
                                            borderRadius: BorderRadius.circular(12),
                                          ),
                                          child: SvgPicture.string(
                                            _contractSvg,
                                            width: 24,
                                            height: 24,
                                            colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
                                          ),
                                        ),
                                        const SizedBox(width: 16),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Row(
                                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                children: [
                                                  Text(
                                                    'Contrato $id',
                                                    style: const TextStyle(
                                                      color: Colors.white,
                                                      fontWeight: FontWeight.bold,
                                                      fontSize: 16,
                                                    ),
                                                  ),
                                                  Container(
                                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                                    decoration: BoxDecoration(
                                                      color: statusColor.withOpacity(0.2),
                                                      borderRadius: BorderRadius.circular(4),
                                                    ),
                                                    child: Text(
                                                      statusText,
                                                      style: TextStyle(
                                                        color: statusColor,
                                                        fontSize: 10,
                                                        fontWeight: FontWeight.bold,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 6),
                                              Text(
                                                plano,
                                                style: const TextStyle(color: Colors.white70, fontSize: 14, fontWeight: FontWeight.w500),
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                address,
                                                style: TextStyle(color: Colors.grey[500], fontSize: 12),
                                                maxLines: 2,
                                                overflow: TextOverflow.ellipsis,
                                              ),
                                            ],
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Icon(Icons.arrow_forward_ios, color: brandColor, size: 16),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              );

              if (selection == null) {
                debugPrint('LOGIN: Seleção cancelada pelo usuário');
                return; // Cancelado pelo usuário
              }
              
              selectedContract = selection;
              setState(() => _isLoading = true); // Volta loading
           } else {
             selectedContract = allMappedContracts.first;
           }

           // Tentar extrair senha da central se ainda não tivermos
           if (extractedPassword == null) {
              final firstRaw = contratos.first;
              extractedPassword = firstRaw['contratoCentralSenha'] ?? 
                                  firstRaw['senha'] ?? 
                                  firstRaw['central_senha'] ?? 
                                  firstRaw['password'];
           }

           String resolvedName = (
             selectedContract['razaoSocial']
             ?? selectedContract['razaosocial']
             ?? selectedContract['razao_social']
             ?? selectedContract['nomeCliente']
             ?? selectedContract['nome']
             ?? contratos.first['razaoSocial']
             ?? contratos.first['razaosocial']
             ?? contratos.first['razao_social']
             ?? contratos.first['nomeCliente']
             ?? contratos.first['nome']
             ?? ''
           ).toString().trim();
           if (resolvedName.isEmpty) {
             for (final raw in contratos) {
               final assinaturas = raw['assinaturaEletronica'];
               if (assinaturas is! List) continue;
               for (final doc in assinaturas) {
                 if (doc is! Map) continue;
                 final statuses = doc['status'];
                 if (statuses is! List) continue;
                 for (final st in statuses) {
                   if (st is! Map) continue;
                   final obs = (st['observacao'] ?? '').toString();
                   final m = RegExp(r'Assinado Por:\s*(.+)$', caseSensitive: false).firstMatch(obs);
                   if (m != null && m.group(1)!.trim().isNotEmpty) {
                     resolvedName = m.group(1)!.trim();
                     break;
                   }
                 }
                 if (resolvedName.isNotEmpty) break;
               }
               if (resolvedName.isNotEmpty) break;
             }
           }
           if (resolvedName.isEmpty) resolvedName = 'Cliente';

           clientData = {
             'nome': resolvedName,
             'contratos': allMappedContracts
           };

           // Buscar dados reais da fatura para complementar o SELECIONADO
           try {
             final invoices = await sgpService.getInvoices(cpf);
             if (invoices.isNotEmpty) {
               final List<Map<String, dynamic>> sortedInvoices = [];
               
               for (var inv in invoices) {
                 if (inv is Map<String, dynamic>) {
                   final status = inv['status']?.toString().toLowerCase().trim();
                   if (status != 'aberto') continue;

                   String? rawDate = inv['dataVencimento'] ?? inv['data_vencimento'];
                   if (rawDate != null) {
                       try {
                         // Parsing manual para evitar desvios de fuso horário
                         final dateParts = rawDate.split('-');
                         DateTime dt;
                         if (dateParts.length == 3) {
                           dt = DateTime(
                             int.parse(dateParts[0]), 
                             int.parse(dateParts[1]), 
                             int.parse(dateParts[2])
                           );
                         } else {
                           dt = DateTime.parse(rawDate);
                         }
                         inv['parsedDate'] = dt;
                         sortedInvoices.add(inv);
                       } catch (e) {}
                   }
                 }
               }

               sortedInvoices.sort((a, b) {
                 final dA = a['parsedDate'] as DateTime;
                 final dB = b['parsedDate'] as DateTime;
                 return dA.compareTo(dB);
               });
               
               // Tentar encontrar fatura para o contrato selecionado
               Map<String, dynamic>? priorityInvoice;
               try {
                 priorityInvoice = sortedInvoices.firstWhere(
                   (inv) => (inv['clienteContrato'] ?? inv['contrato_id'] ?? inv['contrato'])?.toString() == selectedContract['id'].toString(),
                   orElse: () => <String, dynamic>{},
                 );
                 if (priorityInvoice != null && priorityInvoice.isEmpty) priorityInvoice = null;
               } catch (_) {
                 if (allMappedContracts.length == 1 && sortedInvoices.isNotEmpty) {
                   priorityInvoice = sortedInvoices.first;
                 }
               }

                if (priorityInvoice != null) {
                  if (priorityInvoice['valor'] != null) {
                    double val = double.tryParse(priorityInvoice['valor'].toString()) ?? 0.0;
                    double valCorr = double.tryParse((priorityInvoice['valorCorrigido'] ?? priorityInvoice['valor_corrigido'] ?? priorityInvoice['valor']).toString()) ?? val;
                    
                    selectedContract['last_invoice_value'] = val.toStringAsFixed(2).replaceAll('.', ',');
                    selectedContract['last_invoice_corrected_value'] = valCorr.toStringAsFixed(2).replaceAll('.', ',');
                    selectedContract['last_invoice_interest'] = (valCorr - val).toStringAsFixed(2).replaceAll('.', ',');
                  }
                 
                 String? rawDate = priorityInvoice['dataVencimento'] ?? priorityInvoice['data_vencimento'];
                  if (rawDate != null) {
                    try {
                       // Parsing manual robusto
                       final dateParts = rawDate.split('-');
                       DateTime dueDate;
                       if (dateParts.length == 3) {
                         dueDate = DateTime(
                           int.parse(dateParts[0]), 
                           int.parse(dateParts[1]), 
                           int.parse(dateParts[2])
                         );
                       } else {
                         dueDate = DateTime.parse(rawDate);
                       }

                       final parts = rawDate.split('-');
                      if (parts.length == 3) {
                        selectedContract['last_invoice_due'] = '${parts[2]}/${parts[1]}/${parts[0]}';
                        selectedContract['expiry_date'] = selectedContract['last_invoice_due'];
                      } else {
                        selectedContract['last_invoice_due'] = rawDate;
                      }

                       final now = AppConfig.getToday();
                       final today = DateTime(now.year, now.month, now.day);
                       final due = DateTime(dueDate.year, dueDate.month, dueDate.day);
                       
                       // Verificação ultra-robusta para o Login
                       bool serverSaysLate = priorityInvoice['esta_atrasada'] ?? false;
                       if (serverSaysLate) {
                         selectedContract['invoice_status_code'] = 'overdue';
                       } else if (due.year == today.year && due.month == today.month && due.day == today.day) {
                         selectedContract['invoice_status_code'] = 'open';
                       } else if (due.isBefore(today)) {
                         selectedContract['invoice_status_code'] = 'overdue';
                       } else {
                         selectedContract['invoice_status_code'] = 'open';
                       }
                   } catch (_) {
                     selectedContract['last_invoice_due'] = rawDate;
                     selectedContract['invoice_status_code'] = 'open';
                   }
                 }

                 if (priorityInvoice['codigoPix'] != null) {
                   selectedContract['pix_code'] = priorityInvoice['codigoPix'];
                 }
                 if (priorityInvoice['linhaDigitavel'] != null) {
                   selectedContract['barcode'] = priorityInvoice['linhaDigitavel'];
                 }
               } else {
                  selectedContract['invoice_status_code'] = 'paid';
               }
             } else {
               selectedContract['invoice_status_code'] = 'paid';
             }
           } catch (e) {
             debugPrint('Erro ao complementar dados da fatura: $e');
           }

           allMappedContracts.remove(selectedContract);
           allMappedContracts.insert(0, selectedContract);
        } else if (result != null) {
           // Fallback antigo se o formato for diferente
           clientData = result;
        }
      } catch (e) {
        debugPrint('Erro ao buscar cliente: $e');
        final msg = e.toString();
        if (msg.contains('USER_BLOCKED') || msg.contains('403')) {
          rethrow;
        }
      }

      // 2. Se falhar, tentar via faturas (fallback comum)
      if (clientData == null) {
        try {
          final invoices = await sgpService.getInvoices(cpf);
          if (invoices.isNotEmpty) {
            final first = invoices.first;
            // Tentar extrair endereço e vencimento da fatura se possível
          String? endereco;
          String? vencimento;
          String? valor;
          
          if (first['endereco'] != null) {
             endereco = '${first['endereco']}, ${first['numero'] ?? 'S/N'} - ${first['bairro'] ?? ''}';
          }
          if (first['data_vencimento'] != null) vencimento = first['data_vencimento'];
          if (first['valor'] != null) valor = first['valor'].toString();

          clientData = {
            'nome': first['sacado'] ?? 'Cliente gsfibra',
            'contratos': [
              {
                'id': first['contrato_id']?.toString() ?? '1',
                'status': 'ATIVO', // Assume ativo se tem fatura
                'plan_name': first['descricao'] ?? 'PLANO INTERNET',
                'address': endereco ?? 'Endereço não informado',
                'expiry_date': vencimento ?? '29/05/2025',
                'last_invoice_value': valor ?? '50,00',
                'last_invoice_due': vencimento ?? '29/06/2025',
                'last_invoice_status': 'pending'
              }
            ]
          };
          }
        } catch (e) {
          debugPrint('Erro ao buscar faturas: $e');
        }
      }

      // Se ainda for null, lançar erro (sem fallback de mock data em produção)
      if (clientData == null) {
        throw Exception('Cliente não encontrado para o CPF/CNPJ informado.');
      }

      // Processar dados para login
      final String userName = clientData['nome'] ?? clientData['razao_social'] ?? 'Cliente';
      
      // Salvar nome e senha se "Lembrar" estiver marcado
      if (_rememberMe) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('saved_name', userName);
        if (extractedPassword != null) {
          await prefs.setString('centralPassword', extractedPassword);
        }
      }

      Map<String, dynamic> contract = {};
      if (clientData['contratos'] != null && (clientData['contratos'] as List).isNotEmpty) {
        contract = (clientData['contratos'] as List).first;
      }

      // VALIDAÇÃO FINAL: Impede login se não tiver um ID de contrato válido
      // Relaxado: Permite '1' como ID se for o único contrato (comum em alguns SGPs)
      final String contractId = contract['id']?.toString() ?? '';
      if (contractId.isEmpty || contractId == 'N/A') {
         debugPrint('LOGIN: Falha na validação do contrato: ID=$contractId');
         throw Exception('Não foi possível identificar um contrato válido vinculado a este CPF.');
      }

      await provider.login(
        cpf: cpf,
        token: 'mock_token', // Token de sessão do app
        providerToken: AppConfig.apiToken,
        userName: userName,
        contract: contract,
        centralPassword: extractedPassword,
        info: clientData,
      );

      if (mounted) {
        Navigator.of(context).pushReplacementNamed('/home');
      }
    } catch (e) {
      final raw = e.toString();
      if (raw.contains('USER_BLOCKED') || raw.contains('403')) {
        if (!mounted) return;
        final provider = context.read<AppProvider>();
        await provider.fetchAppConfig();
        if (!mounted) return;
        setState(() => _isLoading = false);
        if (provider.isBlocked) return;
        _showUserBlockedDialog();
        return;
      }
      String errorMessage = UserFacingError.from(raw);

      if (!mounted) return;
      _showTopErrorBanner(errorMessage);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showMaintenanceDialog(String providerName) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF222222),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.orange, size: 28),
            SizedBox(width: 12),
            Expanded(child: Text('Manutenção', style: TextStyle(color: Colors.white))),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'O aplicativo está temporariamente em manutenção.',
              style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Text(
              'Entre em contato com a $providerName.',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ],
        ),
      ),
    );

    // Fecha automaticamente após 6 segundos
    Future.delayed(const Duration(seconds: 6), () {
      if (mounted && Navigator.canPop(context)) {
        Navigator.of(context).pop();
      }
    });
  }

  void _showUserBlockedDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF222222),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.block, color: Colors.redAccent, size: 28),
            SizedBox(width: 12),
            Expanded(child: Text('Acesso desativado', style: TextStyle(color: Colors.white))),
          ],
        ),
        content: const Text(
          'Seu acesso ao aplicativo foi desativado. Entre em contato com o provedor.',
          style: TextStyle(color: Colors.white70, fontSize: 14),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final text = AppBranding.loginTextColor;
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          BrandLoginBackground(base: AppBranding.loginBackground, glow: BrandColors.primary),
          SafeArea(
            child: SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: MediaQuery.of(context).size.height - MediaQuery.of(context).padding.top - MediaQuery.of(context).padding.bottom,
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24.0),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.start,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: 56),
                      Center(
                        child: Image(
                          image: AppBranding.loginLogoProvider(),
                          height: 135,
                          fit: BoxFit.contain,
                          errorBuilder: (_, __, ___) => Image.asset(AppBranding.defaultLoginLogoAsset, height: 135),
                        ),
                      ),
                      const SizedBox(height: 48),
                      Text(
                        'Acesse sua conta',
                        style: TextStyle(
                          color: text,
                          fontSize: 28,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Informe seu CPF ou CNPJ para começar',
                        style: TextStyle(
                          color: text.withValues(alpha: 0.92),
                          fontSize: 17,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                      const SizedBox(height: 34),
                      if (_savedCpf != null && _savedCpf!.isNotEmpty)
                        _buildSavedUserCard()
                      else
                        _buildCpfInputField(),
                      const SizedBox(height: 38),
                      _buildEnterButton(),
                      const SizedBox(height: 48),
                      Center(
                        child: TextButton(
                          style: TextButton.styleFrom(foregroundColor: text),
                          onPressed: () async {
                            final digits = AppBranding.whatsappDigits;
                            final message = Uri.encodeComponent('Preciso de ajuda para acessar o app');
                            final waDeepLink = Uri.parse("whatsapp://send?phone=$digits&text=$message");
                            final waWeb = Uri.parse("https://wa.me/$digits?text=$message");
                            if (await canLaunchUrl(waDeepLink)) {
                              await launchUrl(waDeepLink, mode: LaunchMode.externalApplication);
                            } else if (await canLaunchUrl(waWeb)) {
                              await launchUrl(waWeb, mode: LaunchMode.externalApplication);
                            } else {
                              if (context.mounted) _showTopBanner('Não foi possível abrir o WhatsApp');
                            }
                          },
                          child: Text(
                            'Preciso de ajuda?',
                            style: TextStyle(
                              color: text,
                              fontSize: 16,
                              decoration: TextDecoration.none,
                            ),
                          ),
                        ),
                      ),
                      Center(
                        child: TextButton(
                          style: TextButton.styleFrom(foregroundColor: text),
                          onPressed: () {
                            Navigator.of(context).pushNamed('/planos');
                          },
                          child: Text(
                            'Ver planos',
                            style: TextStyle(
                              color: text,
                              fontSize: 16,
                              decoration: TextDecoration.none,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _shade(Color c, double amount) {
    final hsl = HSLColor.fromColor(c);
    return hsl.withLightness((hsl.lightness + amount).clamp(0.0, 1.0)).toColor();
  }

  Widget _buildEnterButton() {
    const radius = 29.0;
    final button = AppBranding.loginButtonColor;
    return Container(
      height: 58,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.40),
            blurRadius: 16,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: _shade(button, -0.3).withValues(alpha: 0.55),
            blurRadius: 10,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _isLoading ? null : _handleLogin,
          borderRadius: BorderRadius.circular(radius),
          child: Ink(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(radius),
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  _shade(button, 0.14),
                  button,
                  _shade(button, -0.16),
                ],
                stops: const [0.0, 0.42, 1.0],
              ),
              border: Border.all(
                color: _shade(button, 0.3).withValues(alpha: 0.55),
                width: 1.2,
              ),
            ),
            child: Center(
              child: _isLoading
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(
                        color: Colors.white,
                        strokeWidth: 2.4,
                      ),
                    )
                  : const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.login_rounded, color: Colors.white, size: 22),
                        SizedBox(width: 10),
                        Text(
                          'ENTRAR',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.8,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSavedUserCard() {
    final String initial = (_savedName != null && _savedName!.isNotEmpty)
        ? _savedName![0].toUpperCase()
        : 'C';
    final accent = AppBranding.loginBackground;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: accent,
            radius: 24,
            child: Text(
              initial,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _savedName ?? 'Cliente',
                  style: TextStyle(
                    color: accent,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  _maskCpfCnpj(_savedCpf!),
                  style: TextStyle(
                    color: accent.withValues(alpha: 0.75),
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: () async {
              final prefs = await SharedPreferences.getInstance();
              await prefs.remove('saved_cpf');
              await prefs.remove('saved_name');
              await prefs.remove('centralPassword');
              setState(() {
                _savedCpf = null;
                _savedName = null;
                _savedPassword = null;
                _cpfController.clear();
                _rememberMe = false;
              });
            },
            style: TextButton.styleFrom(
              foregroundColor: accent,
              padding: const EdgeInsets.symmetric(horizontal: 12),
            ),
            child: Text(
              'Trocar',
              style: TextStyle(fontWeight: FontWeight.bold, color: accent),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCpfInputField() {
    final text = AppBranding.loginTextColor;
    final border = OutlineInputBorder(
      borderRadius: const BorderRadius.all(Radius.circular(16)),
      borderSide: BorderSide(color: text, width: 2),
    );

    return Theme(
      data: Theme.of(context).copyWith(
        colorScheme: Theme.of(context).colorScheme.copyWith(
          surface: Colors.transparent,
          onSurface: text,
        ),
        inputDecorationTheme: const InputDecorationTheme(
          filled: false,
          fillColor: Colors.transparent,
        ),
      ),
      child: Column(
        children: [
          Material(
            type: MaterialType.transparency,
            elevation: 0,
            shadowColor: Colors.transparent,
            child: TextField(
              controller: _cpfController,
              keyboardType: TextInputType.number,
              style: TextStyle(color: text, fontSize: 18),
              cursorColor: text,
              decoration: InputDecoration(
                hintText: 'CPF/CNPJ',
                hintStyle: TextStyle(color: text, fontSize: 18),
                floatingLabelBehavior: FloatingLabelBehavior.never,
                filled: false,
                fillColor: Colors.transparent,
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 22),
                enabledBorder: border,
                focusedBorder: OutlineInputBorder(
                  borderRadius: const BorderRadius.all(Radius.circular(16)),
                  borderSide: BorderSide(color: text, width: 2.4),
                ),
                border: border,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              SizedBox(
                height: 24,
                width: 24,
                child: Checkbox(
                  value: _rememberMe,
                  onChanged: (value) {
                    setState(() {
                      _rememberMe = value ?? false;
                    });
                  },
                  activeColor: text,
                  checkColor: AppBranding.loginBackground,
                  side: BorderSide(color: text, width: 2),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: GestureDetector(
                  onTap: () {
                    setState(() {
                      _rememberMe = !_rememberMe;
                    });
                  },
                  child: Text(
                    'Lembrar meu CPF/CNPJ neste dispositivo',
                    style: TextStyle(color: text, fontSize: 15),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _showTopBanner(String message) {
    _showTopErrorBanner(message);
  }

  void _showTopErrorBanner(String message) {
    showTopNotice(
      content: Row(
        children: [
          const Icon(Icons.info_outline, size: 22),
          const SizedBox(width: 12),
          Expanded(child: Text(message)),
        ],
      ),
      backgroundColor: const Color(0xFFB00020),
    );
  }
}

const String _contractSvg = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M14 2H6C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M14 2V8H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16 13H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16 17H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';
