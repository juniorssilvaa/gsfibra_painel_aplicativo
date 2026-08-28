import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  addVoiceCallListener,
  getGlobalActiveVoiceCall,
  isGlobalIncomingVisible,
  isOutboundVoiceBusy,
  registerOutboundVoiceCall,
  setOutboundVoiceBusy,
  unregisterOutboundVoiceCall,
} from '../utils/voiceCallPainelBus';
import { mapVoiceCallApiError, WHATSAPP_CALL_REJECTED_MSG } from '../lib/apiError';
import { toast } from '../lib/notify';
import {
  authHeaders,
  playRemoteAudio,
  postWebRtcOffer,
  setupVoicePeer,
  unlockAudioElement,
  waitIceComplete,
} from '../utils/voiceCallWebRtc';

/** Evita toast em operações silenciosas (capability, encerrar chamada). */
const voiceCallSilentConfig = { skipErrorToast: true };
/**
 * WebRTC de voz via NioHub Calls (proxy Django) — apenas chamadas de saída.
 * Chamadas recebidas: useGlobalIncomingVoiceCall.
 */
export function useNioHubVoiceCall(conversationId) {
  const [capability, setCapability] = useState(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [inCall, setInCall] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState('00:00');
  const [suppressForIncoming, setSuppressForIncoming] = useState(() => isGlobalIncomingVisible());

  const callRef = useRef(null);
  const timerRef = useRef(null);
  const audioRef = useRef(null);
  const outboundGenRef = useRef(0);
  const pendingCallIdRef = useRef(null);

  const cleanupCall = useCallback(async () => {
    const c = callRef.current;
    callRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setInCall(false);
    setConnecting(false);
    setElapsed('00:00');
    if (c?.callId) unregisterOutboundVoiceCall(c.callId);
    setOutboundVoiceBusy(false);
    if (!c) return;
    try {
      if (c.sessionId) {
        await axios.delete(
          `/api/voice-calls/sessions/${c.sessionId}/calls/${c.callId}/`,
          { headers: authHeaders(), ...voiceCallSilentConfig }
        );
      } else {
        await axios.delete(
          `/api/conversations/${conversationId}/voice-call/${c.callId}/`,
          { headers: authHeaders(), ...voiceCallSilentConfig }
        );
      }
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
  }, [conversationId]);

  const markAnswered = useCallback(() => {
    const c = callRef.current;
    if (!c || c.answered) return;
    c.answered = true;
    c.t0 = Date.now();
    setConnecting(false);
    setStatusText('Em chamada');
    playRemoteAudio(audioRef);
    timerRef.current = setInterval(() => {
      if (!c.t0) return;
      const s = Math.floor((Date.now() - c.t0) / 1000);
      const mm = String(Math.floor(s / 60)).padStart(2, '0');
      const ss = String(s % 60).padStart(2, '0');
      setElapsed(`${mm}:${ss}`);
    }, 1000);
  }, []);

  const handleEvent = useCallback(
    (msg) => {
      const c = callRef.current;
      const eventCallId = String(msg?.id || msg?.callId || '').trim();
      if (msg.type === 'call-ended' || msg.status === 'ended') {
        const reason = String(msg.reason || '').toLowerCase();
        const matchesPending = pendingCallIdRef.current && eventCallId === pendingCallIdRef.current;
        const matchesActive = c && eventCallId === c.callId;
        if (!matchesPending && !matchesActive) return;
        outboundGenRef.current += 1;
        pendingCallIdRef.current = null;
        const wasActive = Boolean(callRef.current);
        cleanupCall();
        if (reason === 'failed' || reason === 'busy' || reason === 'rejected') {
          const userMsg =
            reason === 'busy'
              ? 'Contato recusou ou está ocupado.'
              : WHATSAPP_CALL_REJECTED_MSG;
          setStatusText(userMsg);
          setPanelOpen(true);
          toast.error(userMsg);
        } else if (wasActive) {
          setPanelOpen(false);
          setStatusText('');
        } else {
          setPanelOpen(false);
          setStatusText('');
        }
        return;
      }
      if (!c || eventCallId !== c.callId) return;
      if (msg.type === 'call-status') {
        if (msg.status === 'connected' || msg.status === 'ringing') {
          if (msg.status === 'connected') markAnswered();
          else if (!c.answered) setStatusText('Chamando…');
        }
      }
    },
    [cleanupCall, markAnswered]
  );

  const refreshCapability = useCallback(async () => {
    if (!conversationId) {
      setCapability(null);
      return;
    }
    try {
      const res = await axios.get(`/api/conversations/${conversationId}/voice-call/capability/`, {
        headers: authHeaders(),
        ...voiceCallSilentConfig,
      });
      setCapability(res.data);
    } catch {
      setCapability({ available: false, reason: 'Erro ao verificar ligações.' });
    }
  }, [conversationId]);

  useEffect(() => {
    refreshCapability();
    if (!conversationId) return undefined;
    const offEvents = addVoiceCallListener(handleEvent);
    const offBus = addVoiceCallListener((msg) => {
      if (msg?.type === 'global-incoming-visible') {
        setSuppressForIncoming(Boolean(msg.visible));
        if (msg.visible) {
          // Não misturar painel de saída com popup de entrada.
          setPanelOpen(false);
        }
      }
      if (msg?.type === 'global-voice-active' && msg.callId) {
        setPanelOpen(false);
      }
    });
    return () => {
      offEvents();
      offBus();
    };
  }, [conversationId, refreshCapability, handleEvent]);

  useEffect(
    () => () => {
      cleanupCall();
      setOutboundVoiceBusy(false);
    },
    [cleanupCall]
  );

  const startOutboundCall = async () => {
    if (!capability?.available) return;
    if (getGlobalActiveVoiceCall() || isGlobalIncomingVisible()) {
      setStatusText('Atenda ou recuse a chamada recebida antes de ligar.');
      setPanelOpen(true);
      return;
    }
    if (isOutboundVoiceBusy() && !callRef.current) {
      setStatusText('Já existe uma ligação em andamento.');
      setPanelOpen(true);
      return;
    }
    const gen = outboundGenRef.current + 1;
    outboundGenRef.current = gen;
    setOutboundVoiceBusy(true);
    setPanelOpen(true);
    setConnecting(true);
    setStatusText('Conectando…');
    let outboundId = null;
    let pc = null;
    let mic = null;
    let stopRemotePump = null;
    const aborted = () => gen !== outboundGenRef.current;
    try {
      unlockAudioElement(audioRef);
      ({ pc, mic, stopRemotePump } = await setupVoicePeer(audioRef, {
        onConnectionState: (state) => {
          // ICE com o Go ≠ cliente atendeu. Só toca áudio remoto; timer vem do call-status.
          if (state === 'connected') {
            playRemoteAudio(audioRef);
          } else if (state === 'failed' || state === 'disconnected') {
            setStatusText(
              'Falha na conexão de áudio. Reinicie o NioHub Telefonia com suporte a áudio (MLow).'
            );
          }
        },
      }));
      if (aborted()) return;
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const iceReady = waitIceComplete(pc, { timeoutMs: 8000 });

      const startRes = await axios.post(
        `/api/conversations/${conversationId}/voice-call/start/`,
        {},
        { headers: authHeaders() }
      );
      if (aborted()) return;
      const callId = startRes.data.call_id;
      outboundId = callId;
      pendingCallIdRef.current = callId;
      const sessionId = startRes.data.session_id || null;
      registerOutboundVoiceCall(callId);

      await iceReady;
      if (aborted()) throw new Error('call_aborted');
      const localSdp = pc.localDescription?.sdp || offer.sdp;
      const ansRes = await postWebRtcOffer(
        `/api/conversations/${conversationId}/voice-call/${callId}/webrtc/`,
        localSdp
      );
      if (aborted()) throw new Error('call_aborted');
      await pc.setRemoteDescription({ type: 'answer', sdp: ansRes.data.sdp_answer });
      callRef.current = { pc, mic, stopRemotePump, callId, sessionId, answered: false };
      pendingCallIdRef.current = null;
      setInCall(true);
      setConnecting(true);
      setStatusText('Chamando…');
      playRemoteAudio(audioRef);
    } catch (err) {
      if (err?.message === 'call_aborted') {
        try {
          stopRemotePump?.();
        } catch (_) {}
        try {
          mic?.getTracks().forEach((t) => t.stop());
        } catch (_) {}
        try {
          pc?.close();
        } catch (_) {}
        setOutboundVoiceBusy(false);
        return;
      }
      if (outboundId) unregisterOutboundVoiceCall(outboundId);
      pendingCallIdRef.current = null;
      setOutboundVoiceBusy(false);
      await cleanupCall();
      setPanelOpen(true);
      const apiErr = String(err?.response?.data?.error || err?.response?.data?.detail || '');
      const userMsg = mapVoiceCallApiError(apiErr) || apiErr || err?.message || 'Erro ao ligar';
      setStatusText(userMsg);
    }
  };

  const dismissPanel = () => {
    outboundGenRef.current += 1;
    setPanelOpen(false);
    setStatusText('');
  };

  const hangup = async () => {
    await cleanupCall();
    setPanelOpen(false);
    setStatusText('');
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

  return {
    capability,
    panelOpen,
    setPanelOpen,
    statusText,
    inCall,
    connecting,
    incoming: null,
    muted,
    elapsed,
    audioRef,
    /** Esconde painel de saída enquanto popup global de entrada estiver aberto. */
    panelVisible: !suppressForIncoming && (inCall || panelOpen),
    startOutboundCall,
    acceptIncoming: () => {},
    rejectIncoming: () => {},
    hangup,
    toggleMute,
    refreshCapability,
    dismissPanel,
  };
}
