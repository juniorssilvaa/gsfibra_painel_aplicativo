import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { subscribeVoiceCallEvents } from '../utils/voiceCallEventBus';
import {
  clearGlobalActiveVoiceCall,
  isInboundVoiceEvent,
  isOutboundVoiceBusy,
  setGlobalActiveVoiceCall,
  setGlobalIncomingVisible,
} from '../utils/voiceCallPainelBus';
import {
  acquireMic,
  authHeaders,
  playRemoteAudio,
  postWebRtcOffer,
  setupVoicePeer,
  unlockAudioElement,
  waitIceComplete,
} from '../utils/voiceCallWebRtc';
import { effectiveProvedorFromUser } from '../utils/effectiveProvedorId';

function formatPhoneDigits(digits) {
  if (!digits) return '';
  const d = digits.startsWith('55') && digits.length >= 12 ? digits.slice(2) : digits;
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  if (digits.length >= 10) return `+${digits}`;
  return '';
}

function formatPeerLabel(peer) {
  if (!peer) return 'Cliente WhatsApp';
  const user = peer.split('@')[0] || peer;
  const domain = (peer.split('@')[1] || '').toLowerCase();
  if (domain === 'lid') return 'Cliente WhatsApp';
  const formatted = formatPhoneDigits(user.replace(/\D/g, ''));
  return formatted || 'Cliente WhatsApp';
}

function formatCallerPn(callerPn) {
  if (!callerPn) return '';
  const user = callerPn.split('@')[0] || callerPn;
  return formatPhoneDigits(user.replace(/\D/g, ''));
}

function isGenericClientLabel(name) {
  if (!name) return true;
  const n = String(name).trim();
  if (!n || n === 'Cliente WhatsApp') return true;
  return /^Cliente\s+\d{6,}$/i.test(n);
}

function resolveContactDisplay(incoming, lookup) {
  const peerName = String(incoming?.peerName || '').trim();
  const lookupName = String(lookup?.contact_name || '').trim();
  // Preferir nome do CRM/contato da empresa; notify do WhatsApp só como fallback.
  if (lookupName && !isGenericClientLabel(lookupName)) return lookupName;
  if (peerName && !isGenericClientLabel(peerName)) return peerName;
  if (lookupName) return lookupName;
  if (peerName) return peerName;
  return formatCallerPn(incoming?.callerPn) || formatPeerLabel(incoming?.peer);
}

function resolveContactPhone(incoming, lookup) {
  return lookup?.contact_phone || formatCallerPn(incoming?.callerPn) || '';
}

/**
 * Escuta chamadas recebidas globalmente (qualquer tela do painel).
 */
export function useGlobalIncomingVoiceCall(user) {
  const navigate = useNavigate();
  const provedorId = effectiveProvedorFromUser(user);

  const [visible, setVisible] = useState(false);
  const [incoming, setIncoming] = useState(null);
  const [lookup, setLookup] = useState(null);
  const [statusText, setStatusText] = useState('');
  const [inCall, setInCall] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState('00:00');
  const [callDisplay, setCallDisplay] = useState(null);

  const callRef = useRef(null);
  const incomingRef = useRef(null);
  const timerRef = useRef(null);
  const ringRef = useRef(null);
  const audioRef = useRef(null);
  const lookupAbortRef = useRef(null);
  const lookupRef = useRef(null);
  const dismissTimerRef = useRef(null);
  const endedCallsRef = useRef(new Map());
  const acceptingRef = useRef(false);
  const acceptAbortRef = useRef(false);
  const acceptSetupRef = useRef(null);
  const connectingRef = useRef(false);
  const handleEventRef = useRef(() => {});

  const eventCallId = (msg) => String(msg?.id || msg?.callId || '').trim();

  const clearDismissTimer = useCallback(() => {
    if (dismissTimerRef.current) {
      clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
  }, []);

  const releaseAcceptSetup = useCallback(() => {
    const setup = acceptSetupRef.current;
    acceptSetupRef.current = null;
    if (!setup) return;
    try {
      setup.stopRemotePump?.();
    } catch (_) {}
    try {
      setup.mic?.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    try {
      setup.pc?.close();
    } catch (_) {}
  }, []);

  const endReasonText = (reason) => {
    if (reason === 'busy') return 'Contato recusou ou está ocupado.';
    if (reason === 'uncallable') {
      return 'Chamada encerrada antes de conectar.';
    }
    if (reason === 'accepted_elsewhere') {
      return 'Chamada atendida em outro dispositivo (celular ou WhatsApp principal).';
    }
    if (reason === 'failed') return 'A chamada falhou antes de conectar.';
    if (reason) return `Chamada encerrada (${reason}).`;
    return 'Chamada encerrada pelo cliente.';
  };

  const stopRing = useCallback(() => {
    if (ringRef.current?.interval) clearInterval(ringRef.current.interval);
    if (ringRef.current?.ctx) {
      try {
        ringRef.current.ctx.close();
      } catch (_) {}
    }
    ringRef.current = null;
  }, []);

  const resetUi = useCallback(() => {
    clearDismissTimer();
    setVisible(false);
    setIncoming(null);
    setLookup(null);
    setStatusText('');
    setInCall(false);
    setConnecting(false);
    setMuted(false);
    setElapsed('00:00');
    setCallDisplay(null);
    incomingRef.current = null;
    lookupRef.current = null;
    acceptingRef.current = false;
    connectingRef.current = false;
    setGlobalIncomingVisible(false);
  }, [clearDismissTimer]);

  const showMissedCall = useCallback(
    (reason) => {
      stopRing();
      clearGlobalActiveVoiceCall();
      setIncoming(null);
      incomingRef.current = null;
      setInCall(false);
      setVisible(true);
      setStatusText(endReasonText(reason));
      clearDismissTimer();
      dismissTimerRef.current = setTimeout(() => {
        resetUi();
      }, 7000);
    },
    [clearDismissTimer, resetUi, stopRing]
  );

  const startRing = useCallback(() => {
    stopRing();
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      const ctx = new AC();
      const beep = () => {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = 'sine';
        o.frequency.value = 520;
        o.connect(g);
        g.connect(ctx.destination);
        const t = ctx.currentTime;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.22, t + 0.05);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.95);
        o.start(t);
        o.stop(t + 0.95);
      };
      beep();
      ringRef.current = { ctx, interval: setInterval(beep, 2200) };
    } catch (_) {}
  }, [stopRing]);

  const cleanupCall = useCallback(async () => {
    const c = callRef.current;
    callRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (c?.callId) clearGlobalActiveVoiceCall(c.callId);
    else clearGlobalActiveVoiceCall();
    stopRing();
    resetUi();
    if (!c) return;
    try {
      await axios.delete(`/api/voice-calls/sessions/${c.sessionId}/calls/${c.callId}/`, {
        headers: authHeaders(),
      });
    } catch (_) {}
    try {
      c.mic?.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    try {
      c.stopRemotePump?.();
    } catch (_) {}
    try {
      c.pc?.close();
    } catch (_) {}
  }, [resetUi, stopRing]);

  const markAnswered = useCallback(() => {
    const c = callRef.current;
    if (!c || c.answered) return;
    c.answered = true;
    c.t0 = Date.now();
    stopRing();
    clearDismissTimer();
    connectingRef.current = false;
    setConnecting(false);
    setStatusText('Em chamada');
    setInCall(true);
    setVisible(true);
    playRemoteAudio(audioRef);
    timerRef.current = setInterval(() => {
      if (!c.t0) return;
      const s = Math.floor((Date.now() - c.t0) / 1000);
      const mm = String(Math.floor(s / 60)).padStart(2, '0');
      const ss = String(s % 60).padStart(2, '0');
      setElapsed(`${mm}:${ss}`);
    }, 1000);
  }, [clearDismissTimer, stopRing]);

  const fetchLookup = useCallback(
    async (peer, callerPn = '') => {
      if (lookupAbortRef.current) lookupAbortRef.current.abort();
      const controller = new AbortController();
      lookupAbortRef.current = controller;
      try {
        const params = new URLSearchParams({ peer });
        if (callerPn) params.set('caller_pn', callerPn);
        const peerName = String(incomingRef.current?.peerName || '').trim();
        if (peerName) params.set('peer_name', peerName);
        if (provedorId) params.set('provedor_id', String(provedorId));
        const res = await axios.get(`/api/voice-calls/incoming-lookup/?${params}`, {
          headers: authHeaders(),
          signal: controller.signal,
        });
        setLookup(res.data);
        lookupRef.current = res.data;
      } catch (err) {
        if (err?.code !== 'ERR_CANCELED') {
          const empty = { peer, contact_name: null, contact_phone: null, conversation_id: null };
          setLookup(empty);
          lookupRef.current = empty;
        }
      }
    },
    [provedorId]
  );

  const showIncoming = useCallback(
    (inc) => {
      // Saída em andamento: não abrir "chamada recebida" (evita dois popups).
      if (isOutboundVoiceBusy()) return;
      // Já em chamada / atendendo de verdade.
      if (callRef.current || acceptingRef.current) return;
      // connecting órfão (crash/accept abortado) não deve bloquear nova chamada.
      if (connectingRef.current && !callRef.current && !acceptingRef.current) {
        connectingRef.current = false;
        setConnecting(false);
      }

      const seedLookupFromEvent = (src) => {
        const name = src?.contact_name || src?.contactName || '';
        const phone = src?.contact_phone || src?.contactPhone || '';
        const conversationId = src?.conversation_id || src?.conversationId || null;
        if (!name && !phone && !conversationId) return;
        setLookup((prev) => {
          if (prev?.contact_name && !isGenericClientLabel(prev.contact_name)) return prev;
          const seeded = {
            ...(prev || {}),
            peer: src.peer || prev?.peer || '',
            contact_name: name || prev?.contact_name || null,
            contact_phone: phone || prev?.contact_phone || null,
            conversation_id: conversationId || prev?.conversation_id || null,
          };
          lookupRef.current = seeded;
          return seeded;
        });
      };

      if (incomingRef.current?.callId === inc.callId) {
        const prev = incomingRef.current;
        const merged = {
          ...prev,
          sessionId: inc.sessionId || prev.sessionId,
          peer: inc.peer || prev.peer,
          callerPn: inc.callerPn || prev.callerPn || '',
          peerName: inc.peerName || prev.peerName || '',
          contact_name: inc.contact_name || inc.contactName || prev.contact_name || '',
          contact_phone: inc.contact_phone || inc.contactPhone || prev.contact_phone || '',
        };
        incomingRef.current = merged;
        setIncoming(merged);
        setVisible(true);
        setGlobalIncomingVisible(true);
        seedLookupFromEvent(merged);
        if (!prev.callerPn && merged.callerPn) {
          fetchLookup(merged.peer, merged.callerPn);
        }
        return;
      }

      const endedReason = endedCallsRef.current.get(inc.callId);
      if (endedReason !== undefined) {
        const soft = String(endedReason || '').toLowerCase() === 'uncallable';
        endedCallsRef.current.delete(inc.callId);
        if (soft) {
          // CAPI uncallable antes do ringing — ainda mostra a chamada (QR segue).
        } else {
          showMissedCall(endedReason);
          return;
        }
      }

      incomingRef.current = inc;
      setIncoming(inc);
      setVisible(true);
      setInCall(false);
      setConnecting(false);
      connectingRef.current = false;
      setStatusText('');
      setGlobalIncomingVisible(true);
      seedLookupFromEvent(inc);
      startRing();
      fetchLookup(inc.peer, inc.callerPn || '');
    },
    [fetchLookup, showMissedCall, startRing]
  );

  const handleEvent = useCallback(
    (msg) => {
      // Normaliza payload (WS pode mandar type=voice_call_event com tipo real dentro).
      if (msg?.type === 'voice_call_event') {
        const inner = msg.voice_event || {};
        msg = { ...msg, ...inner, type: inner.type || msg.event_type || msg.type };
      }
      const callId = eventCallId(msg);
      const c = callRef.current;

      if (msg.type === 'call-ended' || msg.status === 'ended') {
        const reason = msg.reason || '';
        // CAPI companion emite uncallable sem encerrar a chamada QR — ignora por completo.
        if (String(reason).toLowerCase() === 'uncallable') {
          return;
        }
        if (callId) endedCallsRef.current.set(callId, reason);
        const terminalReasons = new Set(['busy', 'failed', 'rejected', 'declined', 'missed', 'timeout']);
        const isOurIncoming =
          (incomingRef.current && callId === incomingRef.current.callId) ||
          (callRef.current && callId === callRef.current.callId);
        if (acceptingRef.current && isOurIncoming) {
          if (terminalReasons.has(reason)) {
            acceptingRef.current = false;
            connectingRef.current = false;
            acceptAbortRef.current = true;
            const partial = callRef.current;
            callRef.current = null;
            if (partial) {
              try {
                partial.stopRemotePump?.();
              } catch (_) {}
              try {
                partial.mic?.getTracks().forEach((t) => t.stop());
              } catch (_) {}
              try {
                partial.pc?.close();
              } catch (_) {}
            }
            releaseAcceptSetup();
            showMissedCall(reason);
          }
          return;
        }
        // Go pode emitir ended durante accept se o contexto HTTP cancelar a rede — ignorar se não for terminal.
        if (acceptingRef.current) return;
        if (c && callId === c.callId) {
          if (connectingRef.current && !c.answered) return;
          cleanupCall();
          return;
        }
        if (incomingRef.current && callId === incomingRef.current.callId) {
          showMissedCall(msg.reason || '');
        }
        return;
      }

      if (c && callId === c.callId) {
        if (msg.type === 'call-status' && msg.status === 'connected') {
          markAnswered();
        }
        return;
      }

      if (msg.type === 'incoming' && isInboundVoiceEvent(msg, callId)) {
        clearDismissTimer();
        showIncoming({
          sessionId: msg.sessionId,
          callId,
          peer: msg.peer || '',
          callerPn: msg.callerPn || msg.caller_pn || '',
          peerName: msg.peerName || msg.peer_name || '',
          contact_name: msg.contact_name || msg.contactName || '',
          contact_phone: msg.contact_phone || msg.contactPhone || '',
          conversation_id: msg.conversation_id || msg.conversationId || null,
        });
        return;
      }

      if (
        msg.type === 'call-status' &&
        msg.status === 'ringing' &&
        !callRef.current &&
        isInboundVoiceEvent(msg, callId)
      ) {
        clearDismissTimer();
        showIncoming({
          sessionId: msg.sessionId,
          callId,
          peer: msg.peer || '',
          callerPn: msg.callerPn || msg.caller_pn || '',
          peerName: msg.peerName || msg.peer_name || '',
          contact_name: msg.contact_name || msg.contactName || '',
          contact_phone: msg.contact_phone || msg.contactPhone || '',
          conversation_id: msg.conversation_id || msg.conversationId || null,
        });
        return;
      }

      if (msg.type === 'call-list' && Array.isArray(msg.calls) && !callRef.current && !incomingRef.current) {
        const ringing = msg.calls.find(
          (row) =>
            (row.status === 'ringing' || row.Status === 'ringing') &&
            (row.direction === 'inbound' || row.Direction === 'inbound')
        );
        if (ringing) {
          showIncoming({
            sessionId: ringing.sessionId || ringing.SessionID,
            callId: ringing.callId || ringing.CallID || ringing.id,
            peer: ringing.peer || ringing.Peer || '',
            callerPn: ringing.callerPn || ringing.CallerPn || ringing.caller_pn || '',
            peerName: ringing.peerName || ringing.PeerName || ringing.peer_name || '',
          });
        }
        return;
      }

      if (msg.type === 'incoming-claimed') {
        if (acceptingRef.current) return;
        if (callRef.current && callId === callRef.current.callId) return;
        if (incomingRef.current && callId === incomingRef.current.callId) {
          showMissedCall('atendida por outro operador');
        }
      }
    },
    [cleanupCall, clearDismissTimer, markAnswered, releaseAcceptSetup, showIncoming, showMissedCall]
  );

  handleEventRef.current = handleEvent;

  // Eventos chegam via WebSocket do painel (NotificationContext → dispatchVoiceCallEvent).
  // SSE do Go fica como fallback secundário.
  useEffect(() => {
    if (!user) return undefined;
    return subscribeVoiceCallEvents((msg) => handleEventRef.current(msg));
  }, [user]);

  useEffect(
    () => () => {
      clearDismissTimer();
      if (lookupAbortRef.current) lookupAbortRef.current.abort();
      if (timerRef.current) clearInterval(timerRef.current);
      stopRing();
      const c = callRef.current;
      if (c) {
        try {
          c.mic?.getTracks().forEach((t) => t.stop());
        } catch (_) {}
        try {
          c.pc?.close();
        } catch (_) {}
      }
    },
    [clearDismissTimer, stopRing]
  );

  const openConversation = useCallback(
    (conversationId) => {
      if (!conversationId || !provedorId) return;
      const path = `/${provedorId}/chat`;
      navigate(path);
      try {
        localStorage.setItem(
          'selectedConversation',
          JSON.stringify({ id: conversationId, _voiceNavigate: true })
        );
      } catch (_) {}
    },
    [navigate, provedorId]
  );

  const acceptIncoming = async () => {
    const inc = incomingRef.current;
    if (!inc || callRef.current || acceptingRef.current) return;

    acceptingRef.current = true;
    acceptAbortRef.current = false;
    connectingRef.current = true;
    clearDismissTimer();
    stopRing();

    // Fecha o modal "Chamada recebida" imediatamente no clique.
    incomingRef.current = null;
    setIncoming(null);
    setGlobalIncomingVisible(false);
    setConnecting(true);
    setVisible(true);
    setInCall(false);
    setStatusText('Conectando…');
    setGlobalActiveVoiceCall(inc.callId);

    const displayName = resolveContactDisplay(inc, lookupRef.current);
    const displayPhone = resolveContactPhone(inc, lookupRef.current);
    setCallDisplay({ name: displayName, phone: displayPhone });

    // No gesto do clique: desbloqueia <audio> e pega o mic ANTES de awaits longos.
    unlockAudioElement(audioRef);
    let earlyMic = null;

    try {
      earlyMic = await acquireMic();
      if (acceptAbortRef.current) {
        earlyMic.getTracks().forEach((t) => t.stop());
        throw new Error('accept_aborted');
      }

      // Ordem do cliente oficial: accept → depois WebRTC.
      await axios.post(
        `/api/voice-calls/sessions/${inc.sessionId}/calls/${inc.callId}/accept/`,
        {},
        { headers: authHeaders() }
      );
      if (acceptAbortRef.current) throw new Error('accept_aborted');

      const { pc, mic, stopRemotePump } = await setupVoicePeer(audioRef, {
        mic: earlyMic,
        onConnectionState: (state) => {
          if (state === 'connected') playRemoteAudio(audioRef);
          if (state === 'failed' || state === 'disconnected') {
            setStatusText(
              'Falha na conexão de áudio. Reinicie o NioHub Telefonia com suporte a áudio (MLow).'
            );
          }
        },
      });
      earlyMic = null;
      acceptSetupRef.current = { pc, mic, stopRemotePump };
      if (acceptAbortRef.current) throw new Error('accept_aborted');
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitIceComplete(pc, { timeoutMs: 8000 });
      if (acceptAbortRef.current) throw new Error('accept_aborted');
      const localSdp = pc.localDescription?.sdp || offer.sdp;

      const ansRes = await postWebRtcOffer(
        `/api/voice-calls/sessions/${inc.sessionId}/calls/${inc.callId}/webrtc/`,
        localSdp
      );
      if (acceptAbortRef.current) throw new Error('accept_aborted');
      await pc.setRemoteDescription({ type: 'answer', sdp: ansRes.data.sdp_answer });
      playRemoteAudio(audioRef);

      callRef.current = {
        pc,
        mic,
        stopRemotePump,
        callId: inc.callId,
        sessionId: inc.sessionId,
        answered: false,
        displayName,
        displayPhone,
      };
      acceptSetupRef.current = null;
      setGlobalActiveVoiceCall(inc.callId);

      const conversationId = lookupRef.current?.conversation_id;
      if (conversationId) openConversation(conversationId);

      markAnswered();
    } catch (err) {
      if (earlyMic) {
        try {
          earlyMic.getTracks().forEach((t) => t.stop());
        } catch (_) {}
      }
      clearGlobalActiveVoiceCall(inc.callId);
      if (err?.message === 'accept_aborted') {
        releaseAcceptSetup();
        return;
      }
      releaseAcceptSetup();
      callRef.current = null;
      connectingRef.current = false;
      setConnecting(false);
      const apiErr = String(err?.response?.data?.error || '');
      if (/no such call/i.test(apiErr)) {
        showMissedCall(endedCallsRef.current.get(inc.callId) || 'uncallable');
        return;
      }
      // Aceite já pode ter ido — tenta encerrar no Go para não deixar chamada zumbi.
      try {
        await axios.delete(
          `/api/voice-calls/sessions/${inc.sessionId}/calls/${inc.callId}/`,
          { headers: authHeaders(), skipErrorToast: true }
        );
      } catch (_) {}
      setIncoming(inc);
      incomingRef.current = inc;
      setStatusText(apiErr || err?.message || 'Erro ao atender');
      setVisible(true);
    } finally {
      acceptingRef.current = false;
    }
  };

  const rejectIncoming = async () => {
    const inc = incomingRef.current;
    if (!inc?.sessionId || !inc?.callId) {
      stopRing();
      resetUi();
      return;
    }
    // Fecha o UI só depois de pedir o reject — se a API falhar, ainda tenta.
    stopRing();
    try {
      await axios.post(
        `/api/voice-calls/sessions/${inc.sessionId}/calls/${inc.callId}/reject/`,
        {},
        { headers: authHeaders(), timeout: 15000 }
      );
    } catch (err) {
      console.error('[voice] reject failed', err);
      // Segunda tentativa rápida (rede/proxy).
      try {
        await axios.post(
          `/api/voice-calls/sessions/${inc.sessionId}/calls/${inc.callId}/reject/`,
          {},
          { headers: authHeaders(), timeout: 15000 }
        );
      } catch (err2) {
        console.error('[voice] reject retry failed', err2);
      }
    } finally {
      incomingRef.current = null;
      resetUi();
    }
  };

  const hangup = async () => {
    const c = callRef.current;
    if (!c) {
      clearGlobalActiveVoiceCall();
      resetUi();
      return;
    }
    callRef.current = null;
    clearGlobalActiveVoiceCall(c.callId);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    stopRing();
    setConnecting(false);
    connectingRef.current = false;
    setInCall(false);
    setStatusText('Encerrando…');
    setVisible(true);
    try {
      await axios.delete(`/api/voice-calls/sessions/${c.sessionId}/calls/${c.callId}/`, {
        headers: authHeaders(),
      });
    } catch (_) {}
    try {
      c.mic?.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    try {
      c.stopRemotePump?.();
    } catch (_) {}
    try {
      c.pc?.close();
    } catch (_) {}
    resetUi();
  };

  const toggleMute = () => {
    const c = callRef.current;
    if (!c?.mic) return;
    const tracks = c.mic.getAudioTracks();
    const on = tracks.length && tracks[0].enabled;
    tracks.forEach((t) => {
      t.enabled = !on;
    });
    setMuted(on);
  };

  const contactName =
    callDisplay?.name || resolveContactDisplay(incoming, lookup);
  const contactPhone =
    callDisplay?.phone || resolveContactPhone(incoming, lookup);

  const popupOpen = visible || inCall || connecting;

  return {
    visible: popupOpen,
    incoming,
    inCall,
    connecting,
    statusText,
    elapsed,
    muted,
    contactName,
    contactPhone,
    audioRef,
    acceptIncoming,
    rejectIncoming,
    hangup,
    toggleMute,
    dismiss: () => {
      if (inCall || connecting) return;
      clearDismissTimer();
      resetUi();
    },
  };
}
