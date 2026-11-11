import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:gsfibra/config.dart';
import 'package:gsfibra/utils/user_facing_error.dart';

class SupportReplyPreview {
  final int? id;
  final String content;
  final String messageType;
  final bool? isFromCustomer;
  final String? agentName;

  const SupportReplyPreview({
    this.id,
    required this.content,
    this.messageType = 'text',
    this.isFromCustomer,
    this.agentName,
  });

  factory SupportReplyPreview.fromJson(Map<String, dynamic> json) {
    final fromCustomer = json['is_from_customer'];
    return SupportReplyPreview(
      id: int.tryParse('${json['id'] ?? ''}'),
      content: '${json['content'] ?? ''}',
      messageType: '${json['message_type'] ?? 'text'}',
      isFromCustomer: fromCustomer is bool ? fromCustomer : null,
      agentName: json['agent_name']?.toString(),
    );
  }

  factory SupportReplyPreview.fromMessage(SupportChatMessage message) {
    return SupportReplyPreview(
      id: message.id,
      content: message.previewText,
      messageType: message.messageType,
      isFromCustomer: message.isFromCustomer,
      agentName: message.agentName,
    );
  }
}

class SupportReaction {
  final String emoji;
  final bool isFromCustomer;
  final DateTime? createdAt;

  const SupportReaction({required this.emoji, required this.isFromCustomer, this.createdAt});

  factory SupportReaction.fromJson(Map<String, dynamic> json) {
    return SupportReaction(
      emoji: '${json['emoji'] ?? ''}',
      isFromCustomer: json['is_from_customer'] == true,
      createdAt: DateTime.tryParse('${json['created_at'] ?? ''}'),
    );
  }
}

class SupportChatMessage {
  final int? id;
  final String content;
  final String messageType;
  final bool isFromCustomer;
  final DateTime timestamp;
  final String? fileUrl;
  final String? fileName;
  final bool fromAi;
  final String? agentName;
  final bool pending;
  final String? error;
  final SupportReplyPreview? replyTo;
  final List<SupportReaction> reactions;

  SupportChatMessage({
    this.id,
    required this.content,
    this.messageType = 'text',
    required this.isFromCustomer,
    DateTime? timestamp,
    this.fileUrl,
    this.fileName,
    this.fromAi = false,
    this.agentName,
    this.pending = false,
    this.error,
    this.replyTo,
    this.reactions = const [],
  }) : timestamp = timestamp ?? DateTime.now();

  static const _mediaLabels = {
    'image': '📷 Imagem',
    'audio': '🎵 Áudio',
    'ptt': '🎤 Mensagem de voz',
    'video': '🎬 Vídeo',
    'document': '📎 Arquivo',
    'sticker': 'Figurinha',
    'location': '📍 Localização',
  };

  String get previewText {
    final text = content.trim();
    if (text.isNotEmpty) return text;
    return _mediaLabels[messageType] ?? (fileName ?? 'Mensagem');
  }

  /// Reação mais recente do cliente.
  SupportReaction? get customerReaction => _latest(reactions.where((r) => r.isFromCustomer));

  /// Reação mais recente do atendente.
  SupportReaction? get agentReaction => _latest(reactions.where((r) => !r.isFromCustomer));

  static SupportReaction? _latest(Iterable<SupportReaction> items) {
    SupportReaction? best;
    for (final r in items) {
      if (best == null || (r.createdAt ?? DateTime(0)).isAfter(best.createdAt ?? DateTime(0))) {
        best = r;
      }
    }
    return best;
  }

  SupportChatMessage copyWith({List<SupportReaction>? reactions}) {
    return SupportChatMessage(
      id: id,
      content: content,
      messageType: messageType,
      isFromCustomer: isFromCustomer,
      timestamp: timestamp,
      fileUrl: fileUrl,
      fileName: fileName,
      fromAi: fromAi,
      agentName: agentName,
      pending: pending,
      error: error,
      replyTo: replyTo,
      reactions: reactions ?? this.reactions,
    );
  }

  factory SupportChatMessage.fromJson(Map<String, dynamic> json) {
    final rawContent = '${json['content'] ?? ''}';
    final fromCustomer = json['is_from_customer'] == true;
    final rawReply = json['reply_to'];
    final rawReactions = json['reactions'];
    return SupportChatMessage(
      id: int.tryParse('${json['id'] ?? ''}'),
      content: fromCustomer ? rawContent : stripAgentSignature(rawContent),
      messageType: '${json['message_type'] ?? 'text'}',
      isFromCustomer: fromCustomer,
      timestamp: DateTime.tryParse('${json['created_at'] ?? ''}')?.toLocal() ?? DateTime.now(),
      fileUrl: json['file_url']?.toString(),
      fileName: json['file_name']?.toString(),
      fromAi: json['from_ai'] == true,
      agentName: json['agent_name']?.toString(),
      replyTo: rawReply is Map ? SupportReplyPreview.fromJson(Map<String, dynamic>.from(rawReply)) : null,
      reactions: rawReactions is List ? rawReactions.whereType<Map>().map((r) => SupportReaction.fromJson(Map<String, dynamic>.from(r))).where((r) => r.emoji.isNotEmpty).toList() : const [],
    );
  }

  /// Remove assinaturas embutidas (*Nome disse:* / *Nome*) — o app já mostra o nome na bolha.
  static String stripAgentSignature(String content) {
    var text = content.trim();
    if (text.isEmpty) return text;
    text = text.replaceFirst(
      RegExp(r'^\s*\*{1,2}.+?\s+disse:\*{0,2}\s*', caseSensitive: false),
      '',
    );
    text = text.replaceFirst(RegExp(r'^\s*\*[^*\n]+\*\s*\n+'), '');
    return text.trim();
  }
}

class SupportService {
  Future<Map<String, dynamic>> fetchMessages({
    required String cpf,
    int? afterId,
  }) async {
    final params = {
      'cpf': cpf.replaceAll(RegExp(r'[^\d]'), ''),
      if (afterId != null) 'after_id': '$afterId',
    };
    final url = AppConfig.apiUrl('support/messages/').replace(queryParameters: params);
    final response = await http.get(url, headers: AppConfig.apiHeaders).timeout(const Duration(seconds: 25));
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    return {
      'error': UserFacingError.atendimento,
    };
  }

  Future<Map<String, dynamic>> sendMessage({
    required String cpf,
    String content = '',
    String? name,
    String messageType = 'text',
    String? filePath,
    String? fileName,
    int? replyToId,
  }) async {
    final url = AppConfig.apiUrl('support/messages/');
    final request = http.MultipartRequest('POST', url);
    request.headers.addAll(AppConfig.apiHeaders);
    request.fields['cpf'] = cpf.replaceAll(RegExp(r'[^\d]'), '');
    request.fields['content'] = content;
    request.fields['message_type'] = messageType;
    if (replyToId != null) {
      request.fields['reply_to_message_id'] = '$replyToId';
    }
    if (name != null && name.isNotEmpty) {
      request.fields['name'] = name;
    }
    if (filePath != null && filePath.isNotEmpty) {
      request.files.add(await http.MultipartFile.fromPath(
        'file',
        filePath,
        filename: fileName,
      ));
    }
    final streamed = await request.send().timeout(const Duration(seconds: 60));
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    }
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      return {
        'error': UserFacingError.from(body['error'], fallback: UserFacingError.generic),
      };
    } catch (_) {
      return {'error': 'Não foi possível enviar a mensagem. Tente novamente.'};
    }
  }

  /// Emoji vazio remove a reação do cliente.
  Future<Map<String, dynamic>> react({
    required String cpf,
    required int messageId,
    required String emoji,
  }) async {
    final url = AppConfig.apiUrl('support/reactions/');
    try {
      final response = await http
          .post(
            url,
            headers: {...AppConfig.apiHeaders, 'Content-Type': 'application/json'},
            body: jsonEncode({
              'cpf': cpf.replaceAll(RegExp(r'[^\d]'), ''),
              'message_id': messageId,
              'emoji': emoji,
            }),
          )
          .timeout(const Duration(seconds: 20));
      if (response.statusCode >= 200 && response.statusCode < 300) {
        return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      }
    } catch (_) {
      // cai no erro genérico abaixo
    }
    return {'error': 'Não foi possível reagir à mensagem. Tente novamente.'};
  }
}
