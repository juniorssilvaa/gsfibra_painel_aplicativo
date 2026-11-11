import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../widgets/top_notice.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:record/record.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../provider.dart';
import '../../services/proximity_service.dart';
import '../../services/support_service.dart';
import '../../theme/brand_colors.dart';
import '../../utils/user_facing_error.dart';

class AIChatScreen extends StatefulWidget {
  const AIChatScreen({super.key});

  @override
  State<AIChatScreen> createState() => _AIChatScreenState();
}

class _AIChatScreenState extends State<AIChatScreen> with WidgetsBindingObserver {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final SupportService _service = SupportService();
  final ImagePicker _picker = ImagePicker();
  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();
  final List<SupportChatMessage> _messages = [];

  bool _loading = true;
  bool _sending = false;
  bool _hasText = false;
  bool _recording = false;
  String? _playingUrl;
  bool _audioPlaying = false;
  Duration _audioPosition = Duration.zero;
  Duration _audioDuration = Duration.zero;
  String? _error;
  Timer? _pollTimer;
  StreamSubscription? _posSub;
  StreamSubscription? _durSub;
  StreamSubscription? _stateSub;
  StreamSubscription? _completeSub;
  AppProvider? _appProvider;
  SupportChatMessage? _replyingTo;
  final Map<int, GlobalKey> _messageKeys = {};
  int? _highlightId;
  Timer? _highlightTimer;
  bool _proximityOn = false;
  bool _earpiece = false;
  bool _switchingRoute = false;

  static const List<String> _quickReactions = ['👍', '❤️', '😂', '😮', '😢', '🙏'];

  static final AudioContext _speakerContext = AudioContext(
    android: const AudioContextAndroid(),
    iOS: AudioContextIOS(category: AVAudioSessionCategory.playback),
  );

  static final AudioContext _earpieceContext = AudioContext(
    android: const AudioContextAndroid(
      isSpeakerphoneOn: false,
      audioMode: AndroidAudioMode.inCommunication,
      stayAwake: true,
      contentType: AndroidContentType.speech,
      usageType: AndroidUsageType.voiceCommunication,
      audioFocus: AndroidAudioFocus.gainTransient,
    ),
    iOS: AudioContextIOS(category: AVAudioSessionCategory.playAndRecord),
  );

  static Color get brandColor => BrandColors.primary;
  static Color get userBubbleBg => BrandColors.accent;
  static const Color cardBg = Color(0xFF1E1E1E);
  static const Color voiceBubbleBg = Color(0xFF1E1E1E);
  static const Color scrubberBlue = Color(0xFF53BDEB);
  static const Color receivedText = Color(0xFFFFFFFF);
  static const Color receivedTime = Color(0xFFBDBDBD);

  void _setSuppressPush(bool value) {
    _appProvider?.pushService.suppressSupportChatAlerts = value;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _messageController.addListener(() {
      final has = _messageController.text.trim().isNotEmpty;
      if (has != _hasText) setState(() => _hasText = has);
    });
    _posSub = _player.onPositionChanged.listen((p) {
      if (mounted && _playingUrl != null) setState(() => _audioPosition = p);
    });
    _durSub = _player.onDurationChanged.listen((d) {
      if (mounted && _playingUrl != null) setState(() => _audioDuration = d);
    });
    _stateSub = _player.onPlayerStateChanged.listen((s) {
      if (!mounted) return;
      setState(() => _audioPlaying = s == PlayerState.playing);
      if (_switchingRoute) return;
      if (s == PlayerState.playing) {
        _startProximity();
      } else {
        _stopProximity();
      }
    });
    _completeSub = _player.onPlayerComplete.listen((_) {
      if (!mounted) return;
      setState(() {
        _playingUrl = null;
        _audioPlaying = false;
        _audioPosition = Duration.zero;
      });
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<AppProvider>();
      _appProvider = provider;
      _setSuppressPush(true);
      provider.clearSupportChatNotifications();
      final cpf = provider.cpf;
      if (cpf != null && cpf.isNotEmpty) {
        String? customerId = provider.userInfo['id']?.toString() ?? provider.userInfo['id_cliente']?.toString() ?? provider.userContract['id']?.toString();
        provider.pushService.registerDevice(cpf: cpf, contractId: customerId, name: provider.userName);
      }
      _loadMessages();
      _pollTimer = Timer.periodic(const Duration(seconds: 4), (_) => _loadMessages(silent: true));
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _setSuppressPush(true);
      if (mounted) context.read<AppProvider>().clearSupportChatNotifications();
    } else {
      _setSuppressPush(false);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _setSuppressPush(false);
    _pollTimer?.cancel();
    _posSub?.cancel();
    _durSub?.cancel();
    _stateSub?.cancel();
    _completeSub?.cancel();
    _highlightTimer?.cancel();
    if (_proximityOn) ProximityService.disable();
    _messageController.dispose();
    _scrollController.dispose();
    _recorder.dispose();
    if (_earpiece) {
      _player.setAudioContext(_speakerContext).whenComplete(_player.dispose);
    } else {
      _player.dispose();
    }
    super.dispose();
  }

  bool _isNearBottom({double threshold = 120}) {
    if (!_scrollController.hasClients) return true;
    final pos = _scrollController.position;
    if (!pos.hasContentDimensions) return true;
    return pos.maxScrollExtent - pos.pixels <= threshold;
  }

  Future<void> _loadMessages({bool silent = false}) async {
    final provider = context.read<AppProvider>();
    final cpf = (provider.cpf ?? '').replaceAll(RegExp(r'[^\d]'), '');
    if (cpf.isEmpty) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = 'Faça login para falar com o atendimento.';
        });
      }
      return;
    }
    try {
      final stayAtBottom = !silent || _isNearBottom();
      final data = await _service.fetchMessages(cpf: cpf);
      if (!mounted) return;
      if (data['error'] != null) {
        setState(() {
          _loading = false;
          if (!silent) _error = UserFacingError.from(data['error'], fallback: UserFacingError.atendimento);
        });
        return;
      }
      final raw = data['messages'];
      final list = <SupportChatMessage>[];
      if (raw is List) {
        for (final item in raw) {
          if (item is Map<String, dynamic>) {
            list.add(SupportChatMessage.fromJson(item));
          } else if (item is Map) {
            list.add(SupportChatMessage.fromJson(Map<String, dynamic>.from(item)));
          }
        }
      }
      final pendingKeep = <SupportChatMessage>[];
      for (final m in _messages.where((m) => m.pending)) {
        final alreadyOnServer = list.any((s) => s.isFromCustomer && s.messageType == m.messageType && s.content == m.content && (s.fileName ?? '') == (m.fileName ?? ''));
        if (!alreadyOnServer) pendingKeep.add(m);
      }
      setState(() {
        _messages
          ..clear()
          ..addAll(list)
          ..addAll(pendingKeep);
        _loading = false;
        _error = null;
      });
      context.read<AppProvider>().clearSupportChatNotifications();
      if (stayAtBottom) _scrollToBottom();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        if (!silent) _error = UserFacingError.atendimento;
      });
    }
  }

  Future<void> _send({
    String content = '',
    String messageType = 'text',
    String? filePath,
    String? fileName,
  }) async {
    final text = content.trim();
    if (text.isEmpty && (filePath == null || filePath.isEmpty)) return;
    final provider = context.read<AppProvider>();
    final cpf = (provider.cpf ?? '').replaceAll(RegExp(r'[^\d]'), '');
    if (cpf.isEmpty) return;

    final replyTarget = _replyingTo;
    final pending = SupportChatMessage(
      content: text,
      messageType: messageType,
      isFromCustomer: true,
      fileUrl: filePath,
      fileName: fileName,
      pending: true,
      replyTo: replyTarget != null ? SupportReplyPreview.fromMessage(replyTarget) : null,
    );
    setState(() {
      _messages.add(pending);
      _sending = true;
      _replyingTo = null;
      _messageController.clear();
    });
    _scrollToBottom();

    try {
      final result = await _service.sendMessage(
        cpf: cpf,
        content: text,
        name: provider.userName,
        messageType: messageType,
        filePath: filePath,
        fileName: fileName,
        replyToId: replyTarget?.id,
      );
      if (!mounted) return;
      if (result['error'] != null) {
        setState(() {
          _sending = false;
          _messages.remove(pending);
        });
        showTopSnackBar(
          context,
          SnackBar(content: Text(result['error'].toString())),
        );
        return;
      }
      setState(() {
        _sending = false;
        _messages.remove(pending);
      });
      await _loadMessages(silent: true);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _sending = false;
        _messages.remove(pending);
      });
      showTopSnackBar(
        context,
        const SnackBar(content: Text('Falha ao enviar. Tente novamente.')),
      );
    }
  }

  Future<void> _pickCamera() async {
    final cam = await Permission.camera.request();
    if (!cam.isGranted) {
      if (!mounted) return;
      showTopSnackBar(
        context,
        const SnackBar(content: Text('Permissão da câmera necessária.')),
      );
      return;
    }
    final file = await _picker.pickImage(source: ImageSource.camera, imageQuality: 85, maxWidth: 1600);
    if (file == null) return;
    await _send(messageType: 'image', filePath: file.path, fileName: file.name);
  }

  Future<void> _pickDocument() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.any,
      allowMultiple: false,
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    if (file.path == null) return;
    final ext = (file.extension ?? '').toLowerCase();
    String type = 'document';
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic'].contains(ext)) type = 'image';
    if (['mp3', 'm4a', 'aac', 'ogg', 'wav', 'opus', 'amr'].contains(ext)) type = 'audio';
    if (['mp4', 'mov', 'avi'].contains(ext)) type = 'video';
    await _send(messageType: type, filePath: file.path, fileName: file.name, content: '');
  }

  Future<void> _toggleRecording() async {
    if (_sending) return;
    if (_recording) {
      final path = await _recorder.stop();
      setState(() => _recording = false);
      if (path == null || path.isEmpty) return;
      final name = 'audio_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _send(messageType: 'audio', filePath: path, fileName: name, content: '');
      return;
    }

    final mic = await Permission.microphone.request();
    if (!mic.isGranted) {
      if (!mounted) return;
      showTopSnackBar(
        context,
        const SnackBar(content: Text('Permissão do microfone necessária.')),
      );
      return;
    }
    if (!await _recorder.hasPermission()) {
      if (!mounted) return;
      showTopSnackBar(
        context,
        const SnackBar(content: Text('Sem permissão para gravar áudio.')),
      );
      return;
    }

    final dir = await getTemporaryDirectory();
    final path = '${dir.path}/support_${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc, bitRate: 128000, sampleRate: 44100),
      path: path,
    );
    if (mounted) setState(() => _recording = true);
  }

  void _startReply(SupportChatMessage message) {
    if (message.id == null || message.pending) return;
    HapticFeedback.selectionClick();
    setState(() => _replyingTo = message);
  }

  String _authorLabel({bool? isFromCustomer, String? agentName}) {
    if (isFromCustomer == true) return 'Você';
    final name = (agentName ?? '').trim();
    return name.isNotEmpty ? name : 'Suporte';
  }

  void _replaceMessage(int id, SupportChatMessage Function(SupportChatMessage current) update) {
    final index = _messages.indexWhere((m) => m.id == id);
    if (index < 0) return;
    setState(() => _messages[index] = update(_messages[index]));
  }

  Future<void> _react(SupportChatMessage message, String emoji) async {
    final id = message.id;
    if (id == null || message.pending) return;
    final cpf = (context.read<AppProvider>().cpf ?? '').replaceAll(RegExp(r'[^\d]'), '');
    if (cpf.isEmpty) return;

    final next = message.customerReaction?.emoji == emoji ? '' : emoji;
    final previous = message.reactions;
    _replaceMessage(
      id,
      (current) => current.copyWith(reactions: [
        ...current.reactions.where((r) => !r.isFromCustomer),
        if (next.isNotEmpty) SupportReaction(emoji: next, isFromCustomer: true, createdAt: DateTime.now()),
      ]),
    );

    final result = await _service.react(cpf: cpf, messageId: id, emoji: next);
    if (!mounted) return;
    if (result['error'] != null) {
      _replaceMessage(id, (current) => current.copyWith(reactions: previous));
      showTopMessage(result['error'].toString());
    }
  }

  Future<void> _scrollToMessage(int? id) async {
    if (id == null) return;
    final index = _messages.indexWhere((m) => m.id == id);
    if (index < 0) {
      showTopMessage('A mensagem original não está mais disponível.');
      return;
    }
    var target = _messageKeys[id]?.currentContext;
    if (target == null && _scrollController.hasClients) {
      final max = _scrollController.position.maxScrollExtent;
      final ratio = _messages.length <= 1 ? 0.0 : index / (_messages.length - 1);
      _scrollController.jumpTo((max * ratio).clamp(0.0, max));
      await WidgetsBinding.instance.endOfFrame;
      target = _messageKeys[id]?.currentContext;
    }
    if (target != null && target.mounted) {
      await Scrollable.ensureVisible(
        target,
        alignment: 0.3,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }
    if (!mounted) return;
    setState(() => _highlightId = id);
    _highlightTimer?.cancel();
    _highlightTimer = Timer(const Duration(milliseconds: 1400), () {
      if (mounted) setState(() => _highlightId = null);
    });
  }

  Source _sourceFor(String url) => url.startsWith('http') ? UrlSource(url) : DeviceFileSource(url);

  void _startProximity() {
    if (_proximityOn) return;
    _proximityOn = true;
    ProximityService.enable(_onProximity);
  }

  void _stopProximity() {
    if (!_proximityOn) return;
    _proximityOn = false;
    ProximityService.disable();
    if (_earpiece) {
      _earpiece = false;
      _player.setAudioContext(_speakerContext).catchError((_) {});
    }
  }

  /// Perto do rosto: áudio sai pelo alto-falante de ouvido (tela apaga no nativo).
  /// Afastou: pausa no mesmo ponto e volta para o alto-falante, como no WhatsApp.
  Future<void> _onProximity(bool near) async {
    final url = _playingUrl;
    if (!mounted || url == null || _switchingRoute) return;
    if (near && _audioPlaying && !_earpiece) {
      await _switchRoute(url, earpiece: true, resume: true);
    } else if (!near && _earpiece) {
      await _switchRoute(url, earpiece: false, resume: false);
      _stopProximity();
    }
  }

  Future<void> _switchRoute(String url, {required bool earpiece, required bool resume}) async {
    _switchingRoute = true;
    var position = _audioPosition;
    try {
      position = await _player.getCurrentPosition() ?? _audioPosition;
      await _player.stop();
      await _player.setAudioContext(earpiece ? _earpieceContext : _speakerContext);
      _earpiece = earpiece;
      if (resume) {
        await _player.play(_sourceFor(url), position: position, mode: PlayerMode.mediaPlayer);
      } else {
        await _player.setSource(_sourceFor(url));
        await _player.seek(position);
      }
    } catch (_) {
      // mantém o player no estado atual se a troca de saída falhar
    } finally {
      _switchingRoute = false;
    }
    if (mounted) {
      setState(() {
        _audioPosition = position;
        _audioPlaying = resume;
      });
    }
  }

  Future<void> _playAudio(String url) async {
    try {
      if (_playingUrl == url) {
        if (_audioPlaying) {
          await _player.pause();
        } else {
          await _player.resume();
        }
        return;
      }
      await _player.stop();
      if (_earpiece) {
        _earpiece = false;
        await _player.setAudioContext(_speakerContext);
      }
      if (mounted) {
        setState(() {
          _playingUrl = url;
          _audioPosition = Duration.zero;
          _audioDuration = Duration.zero;
          _audioPlaying = false;
        });
      }
      await _player.play(_sourceFor(url), mode: PlayerMode.mediaPlayer);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _playingUrl = null;
        _audioPlaying = false;
      });
      showTopSnackBar(
        context,
        const SnackBar(content: Text('Não foi possível reproduzir o áudio.')),
      );
    }
  }

  Future<void> _seekAudio(String url, double ratio) async {
    if (_playingUrl != url || _audioDuration.inMilliseconds <= 0) return;
    final ms = (_audioDuration.inMilliseconds * ratio.clamp(0.0, 1.0)).round();
    await _player.seek(Duration(milliseconds: ms));
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  String _fmtDuration(Duration d) {
    final total = d.inSeconds;
    final m = total ~/ 60;
    final s = (total % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: brandColor,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: const Text('Atendimento', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
      ),
      body: Container(
        decoration: const BoxDecoration(
          image: DecorationImage(
            image: AssetImage('assets/modo_claro.png'),
            fit: BoxFit.cover,
            alignment: Alignment.topCenter,
          ),
        ),
        child: Column(
          children: [
            if (_error != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.72),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  children: [
                    Text(
                      UserFacingError.from(_error, fallback: UserFacingError.atendimento),
                      style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.35),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 10),
                    TextButton(
                      onPressed: () {
                        setState(() {
                          _loading = true;
                          _error = null;
                        });
                        _loadMessages();
                      },
                      child: const Text('Tentar novamente', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                    ),
                  ],
                ),
              ),
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator(color: brandColor))
                  : _messages.isEmpty
                      ? Center(
                          child: Container(
                            margin: const EdgeInsets.all(24),
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: Colors.black.withOpacity(0.45),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Text(
                              'Envie uma mensagem para falar com o atendimento.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.white),
                            ),
                          ),
                        )
                      : ListView.builder(
                          controller: _scrollController,
                          padding: const EdgeInsets.all(16),
                          itemCount: _messages.length,
                          itemBuilder: (context, index) => _buildBubble(_messages[index]),
                        ),
            ),
            if (_sending || _recording)
              LinearProgressIndicator(
                color: _recording ? Colors.orange : brandColor,
                backgroundColor: Colors.white10,
              ),
            _buildInputArea(),
          ],
        ),
      ),
    );
  }

  void _insertEmoji(String emoji) {
    final text = _messageController.text;
    final selection = _messageController.selection;
    final start = selection.start >= 0 ? selection.start : text.length;
    final end = selection.end >= 0 ? selection.end : text.length;
    final newText = text.replaceRange(start, end, emoji);
    _messageController.value = TextEditingValue(
      text: newText,
      selection: TextSelection.collapsed(offset: start + emoji.length),
    );
  }

  void _showMessageActions(SupportChatMessage message) {
    if (message.id == null || message.pending) return;
    HapticFeedback.mediumImpact();
    final mine = message.customerReaction?.emoji;
    final agent = message.agentReaction?.emoji;
    final agentLabel = _authorLabel(isFromCustomer: false, agentName: message.agentName);
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1E1E1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 14, 12, 8),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFF2A2A2A),
                  borderRadius: BorderRadius.circular(30),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    for (final emoji in _quickReactions)
                      InkWell(
                        borderRadius: BorderRadius.circular(22),
                        onTap: () {
                          Navigator.pop(ctx);
                          _react(message, emoji);
                        },
                        child: Container(
                          width: 42,
                          height: 42,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: mine == emoji ? Colors.white24 : Colors.transparent,
                          ),
                          child: Text(emoji, style: const TextStyle(fontSize: 26)),
                        ),
                      ),
                    InkWell(
                      borderRadius: BorderRadius.circular(22),
                      onTap: () {
                        Navigator.pop(ctx);
                        _showEmojiPicker(onPick: (emoji) => _react(message, emoji));
                      },
                      child: const SizedBox(
                        width: 42,
                        height: 42,
                        child: Icon(Icons.add, color: Colors.white70),
                      ),
                    ),
                  ],
                ),
              ),
              if (agent != null || mine != null) ...[
                const SizedBox(height: 12),
                if (agent != null) _reactionInfoRow(agent, agentLabel),
                if (mine != null)
                  _reactionInfoRow(mine, 'Você', onRemove: () {
                    Navigator.pop(ctx);
                    _react(message, mine);
                  }),
              ],
              const SizedBox(height: 4),
              ListTile(
                leading: const Icon(Icons.reply, color: Colors.white),
                title: const Text('Responder', style: TextStyle(color: Colors.white)),
                onTap: () {
                  Navigator.pop(ctx);
                  _startReply(message);
                },
              ),
              if (message.content.trim().isNotEmpty)
                ListTile(
                  leading: const Icon(Icons.copy, color: Colors.white),
                  title: const Text('Copiar', style: TextStyle(color: Colors.white)),
                  onTap: () {
                    Navigator.pop(ctx);
                    Clipboard.setData(ClipboardData(text: message.content));
                    showTopMessage('Mensagem copiada.');
                  },
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _reactionInfoRow(String emoji, String who, {VoidCallback? onRemove}) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 20)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              who == 'Você' ? 'Sua reação' : '$who reagiu',
              style: const TextStyle(color: Colors.white70, fontSize: 14),
            ),
          ),
          if (onRemove != null)
            TextButton(
              onPressed: onRemove,
              child: const Text('Remover', style: TextStyle(color: Colors.redAccent)),
            ),
        ],
      ),
    );
  }

  void _showEmojiPicker({void Function(String emoji)? onPick}) {
    const emojis = [
      '😀',
      '😁',
      '😂',
      '🤣',
      '😊',
      '😍',
      '😘',
      '😎',
      '🤔',
      '😅',
      '😢',
      '😭',
      '😡',
      '👍',
      '👎',
      '👏',
      '🙏',
      '🔥',
      '❤️',
      '💯',
      '✅',
      '❌',
      '🎉',
      '🙌',
      '🤝',
      '💪',
      '😴',
      '🤗',
      '👌',
      '👋',
    ];
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1E1E1E),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 16, 12, 12),
          child: GridView.builder(
            shrinkWrap: true,
            itemCount: emojis.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 8,
              mainAxisSpacing: 4,
              crossAxisSpacing: 4,
            ),
            itemBuilder: (_, i) => InkWell(
              onTap: () {
                Navigator.pop(ctx);
                if (onPick != null) {
                  onPick(emojis[i]);
                } else {
                  _insertEmoji(emojis[i]);
                }
              },
              child: Center(
                child: Text(emojis[i], style: const TextStyle(fontSize: 26)),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildInputArea() {
    return Container(
      color: Colors.black.withOpacity(0.55),
      padding: EdgeInsets.only(
        left: 10,
        right: 10,
        top: 8,
        bottom: MediaQuery.of(context).padding.bottom + 12,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_replyingTo != null) _buildReplyComposer(_replyingTo!),
          _buildInputRow(),
        ],
      ),
    );
  }

  Widget _buildReplyComposer(SupportChatMessage target) {
    final fromMe = target.isFromCustomer;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E1E),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white10),
      ),
      child: Row(
        children: [
          Expanded(
            child: _buildReplyQuote(
              SupportReplyPreview.fromMessage(target),
              onTap: () => _scrollToMessage(target.id),
              title: fromMe ? 'Respondendo a você' : 'Respondendo a ${_authorLabel(isFromCustomer: false, agentName: target.agentName)}',
            ),
          ),
          IconButton(
            tooltip: 'Cancelar resposta',
            onPressed: () => setState(() => _replyingTo = null),
            icon: const Icon(Icons.close, color: Colors.white70, size: 20),
          ),
        ],
      ),
    );
  }

  Widget _buildInputRow() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E1E),
              borderRadius: BorderRadius.circular(30),
              border: Border.all(color: Colors.white10),
            ),
            child: Row(
              children: [
                IconButton(
                  tooltip: 'Emoji',
                  onPressed: _sending || _recording ? null : () => _showEmojiPicker(),
                  icon: const Icon(Icons.emoji_emotions_outlined, color: Colors.white70, size: 24),
                ),
                Expanded(
                  child: TextField(
                    controller: _messageController,
                    maxLines: null,
                    enabled: !_recording,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      hintText: _recording ? 'Gravando áudio...' : 'Mensagem',
                      hintStyle: TextStyle(color: _recording ? Colors.orangeAccent : Colors.grey),
                      border: InputBorder.none,
                      isDense: true,
                      contentPadding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                    onSubmitted: (_) {
                      if (_hasText) _send(content: _messageController.text);
                    },
                  ),
                ),
                IconButton(
                  tooltip: 'Arquivo',
                  onPressed: _sending || _recording ? null : _pickDocument,
                  icon: const Icon(Icons.attach_file, color: Colors.white70, size: 22),
                ),
                IconButton(
                  tooltip: 'Câmera',
                  onPressed: _sending || _recording ? null : _pickCamera,
                  icon: const Icon(Icons.photo_camera_outlined, color: Colors.white70, size: 22),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 8),
        GestureDetector(
          onTap: _sending
              ? null
              : () {
                  if (_hasText) {
                    _send(content: _messageController.text);
                  } else {
                    _toggleRecording();
                  }
                },
          child: Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: _recording ? Colors.orange : brandColor,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: (_recording ? Colors.orange : brandColor).withOpacity(0.4),
                  blurRadius: 8,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Icon(
              _hasText ? Icons.send : (_recording ? Icons.stop : Icons.mic),
              color: Colors.white,
              size: 20,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildBubble(SupportChatMessage message) {
    final isUser = message.isFromCustomer;
    final isAudio = message.messageType == 'audio' || message.messageType == 'ptt';
    final isImageOnly = message.messageType == 'image' && (message.fileUrl ?? '').isNotEmpty && message.content.trim().isEmpty;
    final timeColor = isUser ? Colors.white : receivedTime;
    final maxBubble = MediaQuery.of(context).size.width * 0.78;
    final agentLabel = message.fromAi ? 'Suporte' : ((message.agentName ?? '').trim().isNotEmpty ? message.agentName!.trim() : 'Suporte');

    Widget agentNameTag() => Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text(
            agentLabel,
            style: TextStyle(
              color: brandColor,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        );

    Widget timeRow() => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              message.pending ? 'Enviando...' : _fmtTime(message.timestamp),
              style: TextStyle(color: timeColor, fontSize: 10),
            ),
            if (isUser && !message.pending) ...[
              const SizedBox(width: 4),
              Icon(Icons.done_all, size: 14, color: Colors.white.withOpacity(0.95)),
            ],
          ],
        );

    final Widget bubble;
    if (isAudio && (message.fileUrl ?? '').isNotEmpty) {
      bubble = _buildVoiceBubble(message);
    } else if (isImageOnly && message.replyTo == null) {
      final url = message.fileUrl!;
      final isLocal = !url.startsWith('http');
      bubble = Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: isLocal ? Image.file(File(url), fit: BoxFit.cover) : Image.network(url, fit: BoxFit.cover),
          ),
          const SizedBox(height: 4),
          timeRow(),
        ],
      );
    } else {
      bubble = IntrinsicWidth(
        child: Container(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
          decoration: BoxDecoration(
            color: isUser ? userBubbleBg : cardBg,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (message.replyTo != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: _buildReplyQuote(message.replyTo!, onTap: () => _scrollToMessage(message.replyTo!.id)),
                ),
              _buildMedia(message),
              if (message.content.trim().isNotEmpty)
                Text(
                  message.content,
                  softWrap: true,
                  style: const TextStyle(color: Colors.white, height: 1.35, fontSize: 15),
                ),
              const SizedBox(height: 4),
              Align(
                alignment: Alignment.centerRight,
                child: timeRow(),
              ),
            ],
          ),
        ),
      );
    }

    final canInteract = message.id != null && !message.pending;
    final hasReactions = message.customerReaction != null || message.agentReaction != null;
    final highlighted = message.id != null && message.id == _highlightId;

    Widget content = Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxBubble),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            if (!isUser) agentNameTag(),
            GestureDetector(
              onLongPress: canInteract ? () => _showMessageActions(message) : null,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  bubble,
                  if (hasReactions)
                    Positioned(
                      bottom: -16,
                      right: isUser ? 10 : null,
                      left: isUser ? null : 10,
                      child: _buildReactionChip(message),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );

    content = AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      padding: EdgeInsets.only(bottom: hasReactions ? 28 : 12, top: 2),
      color: highlighted ? Colors.white.withOpacity(0.14) : Colors.transparent,
      child: _SwipeToReply(
        onReply: canInteract ? () => _startReply(message) : null,
        child: content,
      ),
    );

    if (message.id == null) return content;
    return KeyedSubtree(
      key: _messageKeys.putIfAbsent(message.id!, () => GlobalKey()),
      child: content,
    );
  }

  Widget _buildReplyQuote(SupportReplyPreview reply, {VoidCallback? onTap, String? title}) {
    final fromMe = reply.isFromCustomer == true;
    final accent = fromMe ? const Color(0xFF06CF9C) : scrubberBlue;
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.black.withOpacity(0.22),
            border: Border(left: BorderSide(color: accent, width: 4)),
          ),
          padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                title ?? _authorLabel(isFromCustomer: reply.isFromCustomer, agentName: reply.agentName),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: accent, fontSize: 12, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 2),
              Text(
                reply.content,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: Colors.white.withOpacity(0.85), fontSize: 13, height: 1.3),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildReactionChip(SupportChatMessage message) {
    final agent = message.agentReaction?.emoji;
    final mine = message.customerReaction?.emoji;
    final emojis = <String>[if (agent != null) agent, if (mine != null && mine != agent) mine];
    final total = (agent != null ? 1 : 0) + (mine != null ? 1 : 0);
    return GestureDetector(
      onTap: () => _showMessageActions(message),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: const Color(0xFF2A2A2A),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.black.withOpacity(0.6), width: 1.5),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(emojis.join(' '), style: const TextStyle(fontSize: 15)),
            if (total > 1 && emojis.length == 1)
              const Padding(
                padding: EdgeInsets.only(left: 3),
                child: Text('2', style: TextStyle(color: Colors.white70, fontSize: 11)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildVoiceBubble(SupportChatMessage message) {
    final url = message.fileUrl!;
    final isUser = message.isFromCustomer;
    final active = _playingUrl == url;
    final playing = active && _audioPlaying;
    final progress = active && _audioDuration.inMilliseconds > 0 ? (_audioPosition.inMilliseconds / _audioDuration.inMilliseconds).clamp(0.0, 1.0) : 0.0;
    final durationLabel = active && _audioDuration.inMilliseconds > 0 ? _fmtDuration(playing || _audioPosition.inMilliseconds > 0 ? _audioPosition : _audioDuration) : '0:00';
    final bubbleColor = isUser ? userBubbleBg : voiceBubbleBg;
    final waveColor = Colors.white.withOpacity(0.55);
    final wavePlayed = Colors.white.withOpacity(0.95);

    return Container(
      width: 260,
      padding: const EdgeInsets.fromLTRB(10, 10, 10, 8),
      decoration: BoxDecoration(
        color: bubbleColor,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (message.replyTo != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _buildReplyQuote(message.replyTo!, onTap: () => _scrollToMessage(message.replyTo!.id)),
            ),
          Row(
            children: [
              InkWell(
                onTap: message.pending ? null : () => _playAudio(url),
                borderRadius: BorderRadius.circular(20),
                child: SizedBox(
                  width: 28,
                  height: 28,
                  child: Icon(
                    playing ? Icons.pause : Icons.play_arrow,
                    color: Colors.white,
                    size: 26,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    return GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTapDown: (details) {
                        final ratio = details.localPosition.dx / constraints.maxWidth;
                        _seekAudio(url, ratio);
                        if (!active) _playAudio(url);
                      },
                      child: SizedBox(
                        height: 28,
                        child: CustomPaint(
                          painter: _WaveformPainter(
                            progress: progress,
                            barColor: waveColor,
                            playedColor: wavePlayed,
                            thumbColor: scrubberBlue,
                          ),
                          size: Size(constraints.maxWidth, 28),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              const SizedBox(width: 36),
              Text(
                message.pending ? '...' : durationLabel,
                style: const TextStyle(color: Colors.white, fontSize: 11),
              ),
              const Spacer(),
              Text(
                message.pending ? 'Enviando...' : _fmtTime(message.timestamp),
                style: const TextStyle(color: Colors.white, fontSize: 11),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMedia(SupportChatMessage message) {
    final url = message.fileUrl;
    if (url == null || url.isEmpty) return const SizedBox.shrink();
    if (message.messageType == 'image') {
      final isLocal = !url.startsWith('http');
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: isLocal ? Image.file(File(url), height: 180, fit: BoxFit.cover) : Image.network(url, height: 180, fit: BoxFit.cover),
        ),
      );
    }
    final label = {
          'video': 'Vídeo',
        }[message.messageType] ??
        (message.fileName ?? 'Arquivo');
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: url.startsWith('http') ? () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication) : null,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.insert_drive_file, color: Colors.white),
            const SizedBox(width: 8),
            Flexible(child: Text(label, style: const TextStyle(color: Colors.white))),
          ],
        ),
      ),
    );
  }

  String _fmtTime(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }
}

/// Arrastar a bolha para a direita inicia a resposta (como no WhatsApp).
class _SwipeToReply extends StatefulWidget {
  final Widget child;
  final VoidCallback? onReply;

  const _SwipeToReply({required this.child, this.onReply});

  @override
  State<_SwipeToReply> createState() => _SwipeToReplyState();
}

class _SwipeToReplyState extends State<_SwipeToReply> {
  static const double _threshold = 64;
  static const double _maxOffset = 90;
  double _dx = 0;
  bool _dragging = false;
  bool _armed = false;

  void _reset() {
    setState(() {
      _dx = 0;
      _dragging = false;
      _armed = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (widget.onReply == null) return widget.child;
    final progress = (_dx / _threshold).clamp(0.0, 1.0);
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragStart: (_) => setState(() => _dragging = true),
      onHorizontalDragUpdate: (details) {
        setState(() => _dx = (_dx + details.delta.dx).clamp(0.0, _maxOffset));
        if (!_armed && _dx >= _threshold) {
          _armed = true;
          HapticFeedback.selectionClick();
        } else if (_armed && _dx < _threshold) {
          _armed = false;
        }
      },
      onHorizontalDragEnd: (_) {
        final armed = _armed;
        _reset();
        if (armed) widget.onReply?.call();
      },
      onHorizontalDragCancel: _reset,
      child: Stack(
        children: [
          Positioned(
            left: 6,
            top: 0,
            bottom: 0,
            child: Center(
              child: Opacity(
                opacity: progress,
                child: Transform.scale(
                  scale: 0.6 + 0.4 * progress,
                  child: const CircleAvatar(
                    radius: 15,
                    backgroundColor: Colors.black54,
                    child: Icon(Icons.reply, size: 18, color: Colors.white),
                  ),
                ),
              ),
            ),
          ),
          AnimatedContainer(
            duration: _dragging ? Duration.zero : const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            transform: Matrix4.translationValues(_dx, 0, 0),
            child: widget.child,
          ),
        ],
      ),
    );
  }
}

class _WaveformPainter extends CustomPainter {
  final double progress;
  final Color barColor;
  final Color playedColor;
  final Color thumbColor;

  _WaveformPainter({
    required this.progress,
    required this.barColor,
    required this.playedColor,
    required this.thumbColor,
  });

  static const _pattern = <double>[
    0.35,
    0.55,
    0.28,
    0.72,
    0.45,
    0.88,
    0.40,
    0.62,
    0.30,
    0.78,
    0.50,
    0.68,
    0.38,
    0.92,
    0.42,
    0.58,
    0.33,
    0.75,
    0.48,
    0.65,
    0.36,
    0.82,
    0.44,
    0.60,
    0.32,
    0.70,
    0.52,
    0.85,
    0.40,
    0.55,
    0.29,
    0.66,
    0.47,
    0.80,
    0.38,
    0.58,
    0.34,
    0.73,
    0.49,
    0.63,
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final barWidth = 2.2;
    final gap = 2.0;
    final count = ((size.width + gap) / (barWidth + gap)).floor().clamp(8, _pattern.length);
    final paint = Paint()..style = PaintingStyle.fill;
    final thumbX = (progress.clamp(0.0, 1.0) * size.width);

    for (var i = 0; i < count; i++) {
      final h = (_pattern[i % _pattern.length] * size.height).clamp(4.0, size.height);
      final x = i * (barWidth + gap);
      final y = (size.height - h) / 2;
      final played = x + barWidth <= thumbX;
      paint.color = played ? playedColor : barColor;
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(x, y, barWidth, h), const Radius.circular(1)),
        paint,
      );
    }

    canvas.drawCircle(Offset(thumbX, size.height / 2), 5.5, Paint()..color = thumbColor);
  }

  @override
  bool shouldRepaint(covariant _WaveformPainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.barColor != barColor || oldDelegate.playedColor != playedColor;
  }
}
