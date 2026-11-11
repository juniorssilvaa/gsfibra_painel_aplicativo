import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../../provider.dart';
import '../../utils/user_facing_error.dart';
import '../../theme/brand_colors.dart';

class SelectContractScreen extends StatefulWidget {
  const SelectContractScreen({super.key});

  @override
  State<SelectContractScreen> createState() => _SelectContractScreenState();
}

class _SelectContractScreenState extends State<SelectContractScreen> {
  bool _isSwitching = false;

  final String _contractSvg = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M14 2H6C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M14 2V8H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16 13H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M16 17H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M10 9H8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
''';

  Future<void> _handleContractSelection(Map<String, dynamic> contract) async {
    final provider = context.read<AppProvider>();
    final currentId = (provider.userContract['id'] ?? provider.userContract['contrato_id'] ?? provider.userContract['contrato'])?.toString();
    final newId = (contract['id'] ?? contract['contract_id'] ?? contract['contrato'])?.toString();

    if (currentId == newId) {
      Navigator.pop(context);
      return;
    }

    setState(() => _isSwitching = true);

    try {
      await provider.updateContract(contract);
      await provider.refreshData();
      if (mounted) {
        final screenHeight = MediaQuery.of(context).size.height;
        Navigator.pushNamedAndRemoveUntil(context, '/home', (route) => false);
        
        showTopSnackBar(context, 
          SnackBar(
            content: const Text(
              'Contrato alterado com sucesso!',
              textAlign: TextAlign.center,
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            backgroundColor: Colors.green,
            behavior: SnackBarBehavior.floating,
            margin: EdgeInsets.only(
              bottom: screenHeight - 210, // Posiciona logo abaixo do cabeçalho
              left: 20,
              right: 20,
            ),
            duration: const Duration(seconds: 3),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        showTopSnackBar(context, 
          SnackBar(content: Text(UserFacingError.from(e)), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _isSwitching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final brandColor = BrandColors.primary;
    final provider = context.watch<AppProvider>();
    
    final List<dynamic> contratos = provider.userInfo['contratos'] ?? [];
    final currentContractId = (provider.userContract['id'] ?? provider.userContract['contrato_id'] ?? provider.userContract['contrato'])?.toString();

    return Scaffold(
      backgroundColor: isDark ? const Color(0xFF121212) : Colors.grey[50],
      appBar: AppBar(
        backgroundColor: brandColor,
        elevation: 0,
        title: const Text(
          'ALTERAR CONTRATO',
          style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
        ),
        centerTitle: true,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: Stack(
        children: [
          contratos.isEmpty
              ? Center(
                  child: Text(
                    'Nenhum contrato encontrado.',
                    style: TextStyle(color: isDark ? Colors.white70 : Colors.grey[600]),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: contratos.length,
                  itemBuilder: (context, index) {
                    final contract = Map<String, dynamic>.from(contratos[index]);
                    final id = contract['id']?.toString() ?? '1';
                    final status = contract['status']?.toString().toUpperCase() ?? 'ATIVO';
                    final plano = contract['plan_name'] ?? 'PLANO INTERNET';
                    final address = contract['address'] ?? 'Endereço não informado';
                    
                    final isSelected = id == currentContractId;
                    
                    final isSuspended = status.contains('SUSPENSO');
                    final isCanceled = status.contains('CANCELADO') || status == '3';
                    final Color statusColor = (isSuspended || isCanceled) ? Colors.red : Colors.green;

                    return Container(
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: isDark ? const Color(0xFF1E1E1E) : Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: isSelected ? brandColor : (isDark ? Colors.white10 : Colors.black12),
                          width: isSelected ? 2 : 1,
                        ),
                        boxShadow: [
                          if (!isSelected)
                            BoxShadow(
                              color: Colors.black.withOpacity(0.05),
                              blurRadius: 8,
                              offset: const Offset(0, 2),
                            ),
                        ],
                      ),
                      child: Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: _isSwitching ? null : () => _handleContractSelection(contract),
                          borderRadius: BorderRadius.circular(16),
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: isSelected ? brandColor : (isDark ? Colors.white.withOpacity(0.05) : Colors.grey[200]),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: SvgPicture.string(
                                    _contractSvg,
                                    width: 24,
                                    height: 24,
                                    colorFilter: ColorFilter.mode(
                                      isSelected ? Colors.white : (isDark ? Colors.white70 : Colors.grey[700]!),
                                      BlendMode.srcIn,
                                    ),
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
                                            style: TextStyle(
                                              color: isDark ? Colors.white : Colors.black,
                                              fontWeight: FontWeight.bold,
                                              fontSize: 16,
                                            ),
                                          ),
                                          if (isSelected)
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                              decoration: BoxDecoration(
                                                color: brandColor.withOpacity(0.1),
                                                borderRadius: BorderRadius.circular(4),
                                              ),
                                              child: Text(
                                                'ATUAL',
                                                style: TextStyle(
                                                  color: brandColor,
                                                  fontSize: 10,
                                                  fontWeight: FontWeight.bold,
                                                ),
                                              ),
                                            )
                                          else
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                              decoration: BoxDecoration(
                                                color: statusColor.withOpacity(0.1),
                                                borderRadius: BorderRadius.circular(4),
                                              ),
                                              child: Text(
                                                status,
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
                                        style: TextStyle(
                                          color: isDark ? Colors.white70 : Colors.grey[800],
                                          fontSize: 14,
                                          fontWeight: FontWeight.w500,
                                        ),
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
                                if (!isSelected) ...[
                                  const SizedBox(width: 8),
                                  Icon(Icons.arrow_forward_ios, color: brandColor, size: 16),
                                ],
                              ],
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
          if (_isSwitching)
            Container(
              color: Colors.black54,
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircularProgressIndicator(color: brandColor),
                    const SizedBox(height: 16),
                    const Text(
                      'Alterando contrato...',
                      style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
