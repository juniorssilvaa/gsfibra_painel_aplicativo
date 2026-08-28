import IncomingCallPopup from './IncomingCallPopup';
import { useGlobalIncomingVoiceCall } from '../hooks/useGlobalIncomingVoiceCall';

/**
 * Popup global de chamada recebida — montado em App.jsx para cobrir chat e painel admin.
 */
export default function GlobalIncomingVoiceCallHost({ user }) {
  const voice = useGlobalIncomingVoiceCall(user);

  return (
    <IncomingCallPopup
      open={voice.visible}
      contactName={voice.contactName}
      contactPhone={voice.contactPhone}
      statusText={voice.statusText}
      inCall={voice.inCall}
      connecting={voice.connecting}
      incoming={voice.incoming}
      elapsed={voice.elapsed}
      muted={voice.muted}
      onAccept={voice.acceptIncoming}
      onReject={voice.rejectIncoming}
      onHangup={voice.hangup}
      onToggleMute={voice.toggleMute}
      onDismiss={voice.dismiss}
      audioRef={voice.audioRef}
    />
  );
}
