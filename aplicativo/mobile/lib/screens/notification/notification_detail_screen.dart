import 'package:flutter/material.dart';
import '../../theme/brand_colors.dart';

class NotificationDetailScreen extends StatelessWidget {
  const NotificationDetailScreen({super.key});

  Color _typeColor(String? type) {
    switch (type) {
      case 'promo':
        return Colors.purple;
      case 'warning':
        return Colors.orange;
      case 'critical':
        return Colors.red;
      case 'success':
        return Colors.green;
      default:
        return Colors.blue;
    }
  }

  IconData _typeIcon(String? type) {
    switch (type) {
      case 'promo':
        return Icons.local_offer;
      case 'warning':
        return Icons.warning_amber_rounded;
      case 'critical':
        return Icons.error_outline;
      case 'success':
        return Icons.check_circle_outline;
      default:
        return Icons.info_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    final Map<String, dynamic> notif =
        (args is Map<String, dynamic>) ? args : {};
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final brandColor = BrandColors.primary;
    final type = notif['type']?.toString();

    return Scaffold(
      backgroundColor: isDark ? const Color(0xFF000000) : Colors.white,
      appBar: AppBar(
        backgroundColor: brandColor,
        foregroundColor: Colors.white,
        title: const Text('Notificação', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(_typeIcon(type), color: _typeColor(type), size: 28),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    notif['title']?.toString() ?? 'Notificação',
                    style: TextStyle(
                      color: isDark ? Colors.white : Colors.black87,
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              notif['body']?.toString() ?? notif['message']?.toString() ?? '',
              style: TextStyle(
                color: isDark ? Colors.white70 : Colors.black87,
                fontSize: 16,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
