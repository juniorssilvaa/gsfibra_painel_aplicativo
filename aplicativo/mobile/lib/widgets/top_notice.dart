import 'dart:async';

import 'package:flutter/material.dart';

import '../main.dart' show navigatorKey;

OverlayEntry? _currentEntry;
GlobalKey<_TopNoticeState>? _currentKey;

/// Mostra um aviso no topo da tela (no lugar do SnackBar, que aparece embaixo).
/// Aceita o mesmo [SnackBar] já montado nas telas: usa o conteúdo, a cor e a duração dele.
void showTopSnackBar(BuildContext context, SnackBar snackBar) {
  showTopNotice(
    content: snackBar.content,
    backgroundColor: snackBar.backgroundColor,
    duration: snackBar.duration,
  );
}

void showTopMessage(String message, {Color? backgroundColor, Duration duration = const Duration(seconds: 3)}) {
  showTopNotice(
    content: Text(message),
    backgroundColor: backgroundColor,
    duration: duration,
  );
}

void showTopNotice({required Widget content, Color? backgroundColor, Duration duration = const Duration(seconds: 4)}) {
  final overlay = navigatorKey.currentState?.overlay;
  if (overlay == null) return;
  hideTopNotice();

  final key = GlobalKey<_TopNoticeState>();
  late final OverlayEntry entry;
  entry = OverlayEntry(
    builder: (_) => _TopNotice(
      key: key,
      content: content,
      backgroundColor: backgroundColor ?? const Color(0xFF323232),
      duration: duration,
      onDismissed: () {
        if (identical(_currentEntry, entry)) {
          _currentEntry = null;
          _currentKey = null;
        }
        if (entry.mounted) entry.remove();
      },
    ),
  );
  _currentEntry = entry;
  _currentKey = key;
  overlay.insert(entry);
}

/// Fecha o aviso atual imediatamente (sem animação).
void hideTopNotice() {
  final entry = _currentEntry;
  _currentEntry = null;
  _currentKey = null;
  if (entry != null && entry.mounted) entry.remove();
}

/// Fecha o aviso atual com a animação de saída.
void dismissTopNotice() => _currentKey?.currentState?.dismiss();

class _TopNotice extends StatefulWidget {
  const _TopNotice({
    super.key,
    required this.content,
    required this.backgroundColor,
    required this.duration,
    required this.onDismissed,
  });

  final Widget content;
  final Color backgroundColor;
  final Duration duration;
  final VoidCallback onDismissed;

  @override
  State<_TopNotice> createState() => _TopNoticeState();
}

class _TopNoticeState extends State<_TopNotice> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 250),
  );
  Timer? _timer;
  bool _closing = false;

  @override
  void initState() {
    super.initState();
    _controller.forward();
    _timer = Timer(widget.duration, dismiss);
  }

  Future<void> dismiss() async {
    if (_closing || !mounted) return;
    _closing = true;
    _timer?.cancel();
    await _controller.reverse();
    widget.onDismissed();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textColor = ThemeData.estimateBrightnessForColor(widget.backgroundColor) == Brightness.dark ? Colors.white : const Color(0xFF1F2124);
    final curved = CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic);

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: SafeArea(
        bottom: false,
        child: SlideTransition(
          position: Tween(begin: const Offset(0, -1.2), end: Offset.zero).animate(curved),
          child: FadeTransition(
            opacity: curved,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Dismissible(
                key: const ValueKey('top_notice'),
                direction: DismissDirection.up,
                onDismissed: (_) {
                  _timer?.cancel();
                  widget.onDismissed();
                },
                child: GestureDetector(
                  onTap: dismiss,
                  child: Material(
                    color: widget.backgroundColor,
                    elevation: 8,
                    shadowColor: Colors.black54,
                    borderRadius: BorderRadius.circular(14),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      child: DefaultTextStyle.merge(
                        style: TextStyle(color: textColor, fontSize: 14, fontWeight: FontWeight.w600),
                        child: IconTheme.merge(
                          data: IconThemeData(color: textColor),
                          child: widget.content,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
