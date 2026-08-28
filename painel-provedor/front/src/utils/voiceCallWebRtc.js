import axios from 'axios';
import { buildApiPath } from './apiBaseUrl';

export function authHeaders() {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
  return token ? { Authorization: `Token ${token}` } : {};
}

export function isValidSdpOffer(sdp) {
  const text = (sdp || '').trim();
  return text.startsWith('v=0') && text.includes('m=audio') && text.length >= 40;
}

export async function postWebRtcOffer(url, sdpOffer, axiosConfig = {}) {
  const sdp = (sdpOffer || '').trim();
  if (!isValidSdpOffer(sdp)) {
    throw new Error('SDP WebRTC inválido no navegador.');
  }
  return axios.post(
    url,
    { sdp_offer: sdp },
    {
      ...axiosConfig,
      headers: {
        ...authHeaders(),
        'Content-Type': 'application/json',
        ...(axiosConfig.headers || {}),
      },
    }
  );
}

export async function waitIceComplete(pc, { timeoutMs = 1500 } = {}) {
  if (pc.iceGatheringState === 'complete') return;
  await new Promise((resolve) => {
    const check = () => {
      if (pc.iceGatheringState === 'complete') {
        pc.removeEventListener('icegatheringstatechange', check);
        resolve();
      }
    };
    pc.addEventListener('icegatheringstatechange', check);
    setTimeout(() => {
      pc.removeEventListener('icegatheringstatechange', check);
      resolve();
    }, timeoutMs);
  });
}

/** Desbloqueia autoplay no gesto do clique (antes de qualquer await longo). */
export function unlockAudioElement(audioRef) {
  const el = audioRef?.current;
  if (!el) return;
  el.muted = false;
  el.volume = 1;
  const p = el.play();
  if (p && typeof p.catch === 'function') {
    p.catch(() => {});
  }
}

/** Tenta reproduzir áudio remoto. */
export function playRemoteAudio(audioRef) {
  const el = audioRef?.current;
  if (!el) {
    console.warn('[voice] playRemoteAudio: <audio> não montado');
    return;
  }
  el.muted = false;
  el.volume = 1;
  const p = el.play();
  if (p && typeof p.catch === 'function') {
    p.catch((err) => {
      console.warn('[voice] audio.play() bloqueado:', err?.name || err);
    });
  }
}

/**
 * Liga o MediaStream remoto ao <audio>. Não use display:none —
 * Chrome/Edge podem não tocar áudio com hidden.
 */
export function attachRemoteStream(audioRef, stream) {
  if (!stream || !audioRef) return false;
  const el = audioRef.current;
  if (!el) {
    console.warn('[voice] attachRemoteStream: <audio> não montado');
    return false;
  }
  if (el.srcObject !== stream) el.srcObject = stream;
  playRemoteAudio(audioRef);
  return true;
}

export async function acquireMic() {
  const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  mic.getAudioTracks().forEach((t) => {
    t.enabled = true;
  });
  return mic;
}

/**
 * @param {React.RefObject} audioRef
 * @param {{ onConnectionState?: Function, mic?: MediaStream }} [opts]
 */
export async function setupVoicePeer(audioRef, { onConnectionState, mic: existingMic } = {}) {
  // Uma única m-line sendrecv (addTrack). O recvonly extra do cliente oficial
  // gera 2 m=audio e o AddTrack do Go pode amarrar o retorno no mid errado —
  // agente não ouve o peer mesmo com Peer RTP decoded.
  const mic = existingMic || (await acquireMic());
  mic.getAudioTracks().forEach((t) => {
    t.enabled = true;
  });
  const pc = new RTCPeerConnection({ iceServers: [] });
  mic.getAudioTracks().forEach((t) => pc.addTrack(t, mic));

  let remoteStream = null;
  const tryAttach = () => {
    if (!remoteStream) {
      for (const receiver of pc.getReceivers()) {
        const track = receiver?.track;
        if (track?.kind === 'audio' && track.readyState !== 'ended') {
          remoteStream = new MediaStream([track]);
          break;
        }
      }
    }
    if (remoteStream) attachRemoteStream(audioRef, remoteStream);
  };

  pc.ontrack = (ev) => {
    remoteStream = ev.streams?.[0] || (ev.track ? new MediaStream([ev.track]) : null);
    console.info('[voice] ontrack', {
      streams: ev.streams?.length || 0,
      trackState: ev.track?.readyState,
      muted: ev.track?.muted,
    });
    tryAttach();
  };

  const pump = setInterval(() => {
    if (pc.connectionState === 'closed' || pc.connectionState === 'failed') {
      clearInterval(pump);
      return;
    }
    tryAttach();
  }, 200);

  const notifyState = () => {
    onConnectionState?.(pc.connectionState || pc.iceConnectionState);
    if (pc.connectionState === 'connected' || pc.iceConnectionState === 'connected') {
      tryAttach();
    }
  };
  pc.oniceconnectionstatechange = notifyState;
  pc.onconnectionstatechange = notifyState;

  return {
    pc,
    mic,
    stopRemotePump: () => clearInterval(pump),
  };
}
