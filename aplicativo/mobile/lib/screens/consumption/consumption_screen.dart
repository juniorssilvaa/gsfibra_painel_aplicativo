import 'package:flutter/material.dart';
import '../../widgets/top_notice.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../provider.dart';
import '../../utils/user_facing_error.dart';
import '../../services/sgp_service.dart';
import '../../theme/brand_colors.dart';

class ConsumptionScreen extends StatefulWidget {
  const ConsumptionScreen({super.key});

  @override
  State<ConsumptionScreen> createState() => _ConsumptionScreenState();
}

class _ConsumptionScreenState extends State<ConsumptionScreen> {
  bool _isLoading = false;
  List<dynamic> _consumptionData = [];
  DateTime _selectedDate = DateTime.now();

  // Colors based on the new design
  final Color brandColor = BrandColors.primary;
  final Color darkBackground = const Color(0xFF121212); // Almost black background
  final Color cardBackground = const Color(0xFF1E1E1E); // Dark Grey for cards
  final Color textGrey = const Color(0xFFAAAAAA);
  
  @override
  void initState() {
    super.initState();
    _fetchConsumption();
  }

  Future<void> _fetchConsumption() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final appProvider = Provider.of<AppProvider>(context, listen: false);
      final sgpService = appProvider.sgpService;

      if (sgpService == null) {
        throw Exception("Serviço SGP não inicializado");
      }

      String contractId = appProvider.userContract['id']?.toString() ?? '';
      String? cpf = appProvider.cpf;
      String? password = appProvider.centralPassword;
      
      // Tenta recuperar a senha se estiver vazia (recarregando do SharedPreferences)
      if (password == null || password.isEmpty) {
        await appProvider.initialize();
        password = appProvider.centralPassword;
      }

      if (password == null || password.isEmpty) {
        if (mounted) {
          showTopSnackBar(context, 
            const SnackBar(
              content: Text('Sessão expirada ou senha não encontrada. Por favor, faça login novamente.'),
              backgroundColor: Colors.red,
            ),
          );
        }
        return;
      }
      
      // Garante que cpf não seja nulo
      if (cpf == null || cpf.isEmpty) {
         cpf = appProvider.userInfo['cpf_cnpj'] ?? '';
      }

      if (contractId.isEmpty) {
        try {
          final contracts = await sgpService.getContratos(cpf!, password);
          if (contracts.isNotEmpty) {
             // Tenta pegar o ID de várias formas possíveis
             contractId = contracts[0]['id']?.toString() ?? 
                          contracts[0]['contrato']?.toString() ?? 
                          contracts[0]['contract_id']?.toString() ?? '';
          }
        } catch (e) {
          debugPrint('Erro ao buscar contratos para consumo: $e');
        }
      }

      if (contractId.isNotEmpty) {
        debugPrint('Buscando consumo para contrato: $contractId');
        final data = await sgpService.getConsumption(
          cpf!,
          password,
          contractId,
          _selectedDate.month,
          _selectedDate.year,
        );
        
        // Sort data by date just in case
        if (data.isNotEmpty) {
          try {
             data.sort((a, b) {
               final dateA = DateTime.parse(a['data']);
               final dateB = DateTime.parse(b['data']);
               return dateA.compareTo(dateB);
             });
          } catch (_) {}
        }
        
        setState(() {
          _consumptionData = data;
        });
      }
    } catch (e) {
      print('Error fetching consumption: $e');
      if (mounted) {
        showTopSnackBar(context, 
          SnackBar(content: Text(UserFacingError.from(e, fallback: 'Não foi possível carregar o consumo agora.'))),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _changeMonth(int offset) {
    setState(() {
      _selectedDate = DateTime(_selectedDate.year, _selectedDate.month + offset);
    });
    _fetchConsumption();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: darkBackground,
      appBar: AppBar(
        title: const Text('CONSUMO', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        centerTitle: true,
        backgroundColor: brandColor,
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      body: _isLoading 
        ? Center(child: CircularProgressIndicator(color: brandColor))
        : SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildSectionTitle('MÊS E ANO'),
                const SizedBox(height: 8),
                _buildDateSelector(),
                const SizedBox(height: 24),
                
                _buildSectionTitle('GRÁFICO'),
                const SizedBox(height: 8),
                _buildChartSection(),
                const SizedBox(height: 24),
                
                _buildSectionTitle('RELATÓRIO'),
                const SizedBox(height: 8),
                _buildReportList(),
              ],
            ),
          ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Center(
      child: Text(
        title,
        style: TextStyle(
          color: textGrey,
          fontSize: 12,
          letterSpacing: 1.2,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildDateSelector() {
    return Container(
      decoration: BoxDecoration(
        color: cardBackground,
        borderRadius: BorderRadius.circular(8),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          IconButton(
            icon: const Icon(Icons.chevron_left, color: Colors.white),
            onPressed: () => _changeMonth(-1),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
          ),
          Text(
            DateFormat('MMM/yyyy', 'pt_BR').format(_selectedDate).toUpperCase(),
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
           IconButton(
            icon: const Icon(Icons.chevron_right, color: Colors.white),
            onPressed: () => _changeMonth(1),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
          ),
        ],
      ),
    );
  }

  Widget _buildChartSection() {
    return Container(
      height: 300,
      decoration: BoxDecoration(
        color: cardBackground,
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Legend
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildLegendItem('Download', brandColor),
              const SizedBox(width: 16),
              _buildLegendItem('Upload', Colors.white),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _consumptionData.isEmpty 
              ? Center(child: Text('Sem dados', style: TextStyle(color: textGrey)))
              : LineChart(
                  LineChartData(
                    gridData: FlGridData(
                      show: true,
                      drawVerticalLine: false,
                      horizontalInterval: _getMaxY() > 0 ? _getMaxY() / 4 : 1,
                      getDrawingHorizontalLine: (value) {
                        return FlLine(
                          color: Colors.grey.withOpacity(0.1),
                          strokeWidth: 1,
                          dashArray: [5, 5],
                        );
                      },
                    ),
                    titlesData: FlTitlesData(
                      show: true,
                      rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      bottomTitles: AxisTitles(
                        sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: 22,
                          interval: 5, // Show every 5th day approx
                          getTitlesWidget: (value, meta) {
                             int index = value.toInt();
                             if (index >= 0 && index < _consumptionData.length) {
                               final item = _consumptionData[index];
                               final dateStr = item['data'] ?? '';
                               if (dateStr.isNotEmpty) {
                                 try {
                                   final date = DateTime.parse(dateStr);
                                   // Show date if it fits interval
                                   return Padding(
                                     padding: const EdgeInsets.only(top: 8.0),
                                     child: Text(
                                       DateFormat('dd/MM').format(date),
                                       style: TextStyle(color: textGrey, fontSize: 10),
                                     ),
                                   );
                                 } catch (_) {}
                               }
                             }
                             return const Text('');
                          },
                        ),
                      ),
                      leftTitles: AxisTitles(
                        sideTitles: SideTitles(
                          showTitles: true,
                          interval: _getMaxY() > 0 ? _getMaxY() / 4 : 1,
                          reservedSize: 40,
                          getTitlesWidget: (value, meta) {
                            if (value == 0) return const Text(''); // Hide 0
                            return Text(
                              '${value.toInt()} GB',
                              style: TextStyle(color: textGrey, fontSize: 10),
                            );
                          },
                        ),
                      ),
                    ),
                    borderData: FlBorderData(show: false),
                    minX: 0,
                    maxX: (_consumptionData.length - 1).toDouble(),
                    minY: 0,
                    maxY: _getMaxY(),
                    lineBarsData: [
                      // Download Line
                      LineChartBarData(
                        spots: _getSpots('download'),
                        isCurved: true,
                        color: brandColor,
                        barWidth: 2,
                        isStrokeCapRound: true,
                        dotData: const FlDotData(show: false),
                        belowBarData: BarAreaData(
                          show: true,
                          color: brandColor.withOpacity(0.1),
                        ),
                      ),
                      // Upload Line
                      LineChartBarData(
                        spots: _getSpots('upload'),
                        isCurved: true,
                        color: Colors.white,
                        barWidth: 2,
                        isStrokeCapRound: true,
                        dotData: const FlDotData(show: false),
                         belowBarData: BarAreaData(
                          show: true,
                          color: Colors.white.withOpacity(0.05),
                        ),
                      ),
                    ],
                    lineTouchData: LineTouchData(
                      touchTooltipData: LineTouchTooltipData(
                         getTooltipItems: (touchedSpots) {
                           return touchedSpots.map((spot) {
                             final isDownload = spot.barIndex == 0;
                             return LineTooltipItem(
                               '${spot.y.toStringAsFixed(2)} GB',
                               TextStyle(
                                 color: isDownload ? brandColor : Colors.white,
                                 fontWeight: FontWeight.bold,
                               ),
                             );
                           }).toList();
                         }
                      ),
                    ),
                  ),
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildLegendItem(String label, Color color) {
    return Row(
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(label, style: TextStyle(color: textGrey, fontSize: 12)),
      ],
    );
  }

  Widget _buildReportList() {
    if (_consumptionData.isEmpty) {
      return Center(child: Text('Nenhum registro.', style: TextStyle(color: textGrey)));
    }
    
    // Reverse order for the list (Newest first)
    final reversedList = _consumptionData.reversed.toList();

    return ListView.separated(
      physics: const NeverScrollableScrollPhysics(),
      shrinkWrap: true,
      itemCount: reversedList.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final item = reversedList[index];
        String dateStr = item['data'] ?? '';
        String formattedDate = dateStr;
        try {
           formattedDate = DateFormat('dd/MM/yyyy').format(DateTime.parse(dateStr));
        } catch (_) {}

        return Container(
          decoration: BoxDecoration(
            color: cardBackground,
            borderRadius: BorderRadius.circular(12),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    formattedDate,
                    style: TextStyle(color: textGrey, fontSize: 12),
                  ),
                  Icon(Icons.bar_chart, color: brandColor, size: 20),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(child: _buildTrafficItem(Icons.arrow_downward, _formatBytes(item['download']))),
                  Expanded(child: _buildTrafficItem(Icons.arrow_upward, _formatBytes(item['upload']))),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildTrafficItem(IconData icon, String value) {
    return Row(
      children: [
        Icon(icon, color: Colors.white, size: 16),
        const SizedBox(width: 8),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  String _formatBytes(dynamic value) {
    if (value == null) return '0 B';
    double bytes = 0;
    if (value is num) {
      bytes = value.toDouble();
    } else {
      try {
        bytes = double.parse(value.toString());
      } catch (_) {
        return value.toString();
      }
    }
    
    if (bytes >= 1073741824) {
      return '${(bytes / 1073741824).toStringAsFixed(1)} GB';
    } else if (bytes >= 1048576) {
      return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    } else if (bytes >= 1024) {
      return '${(bytes / 1024).toStringAsFixed(1)} KB';
    }
    return '${bytes.toStringAsFixed(0)} B';
  }

  double _getMaxY() {
    double max = 0;
    for (var item in _consumptionData) {
      double down = _parseTraffic(item['download']);
      double up = _parseTraffic(item['upload']);
      if (down > max) max = down;
      if (up > max) max = up;
    }
    return max == 0 ? 10 : max * 1.2;
  }
  
  List<FlSpot> _getSpots(String key) {
    List<FlSpot> spots = [];
    for (int i = 0; i < _consumptionData.length; i++) {
      final item = _consumptionData[i];
      double val = _parseTraffic(item[key]);
      spots.add(FlSpot(i.toDouble(), val));
    }
    return spots;
  }

  double _parseTraffic(dynamic value) {
    if (value == null) return 0;
    if (value is num) {
      return value.toDouble() / 1073741824.0; // Bytes to GB
    }

    String v = value.toString().toUpperCase();
    double multiplier = 1; 
    
    if (v.contains('GB')) {
      multiplier = 1;
      v = v.replaceAll('GB', '');
    } else if (v.contains('MB')) {
      multiplier = 0.001;
      v = v.replaceAll('MB', '');
    } else if (v.contains('KB')) {
      multiplier = 0.000001;
      v = v.replaceAll('KB', '');
    } else if (v.contains('B')) {
      multiplier = 0.000000001;
      v = v.replaceAll('B', '');
    } else {
      try {
        return double.parse(v.trim()) / 1073741824.0;
      } catch (_) {
        return 0;
      }
    }
    
    try {
      return double.parse(v.trim()) * multiplier;
    } catch (e) {
      return 0;
    }
  }
}
