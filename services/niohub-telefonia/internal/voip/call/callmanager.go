package call

import (
	"context"
	"log/slog"
	"sync"
	"time"
	"wacalls/internal/voip/core"
	"wacalls/internal/voip/media"
	"wacalls/internal/voip/signaling"
	"wacalls/internal/voip/transport"
	"wacalls/internal/voip/wanode"

	"go.mau.fi/whatsmeow/types"
)

type CallManager struct {
	sock core.VoipSocket
	log  *slog.Logger

	mu          sync.Mutex
	currentCall *CallInfo

	rtpSession  *media.RtpSession
	srtpSession *media.SrtpSession
	codec       media.Codec
	relay       RelayTransport

	selfSsrc      uint32
	peerSsrcs     []uint32
	actualPeerSet bool

	firstPacketSent       bool
	initialTransportSent  bool
	outgoingPreacceptSent bool
	acceptedByJid         string
	peerDeviceJid         string // JID with device ID, populated from first relaylatency
	callerAlt             types.JID // Caller's PN JID (s.whatsapp.net), from CallCreatorAlt
	peerName              string    // WhatsApp notify / contact push name
	debeEnabled           bool

	encodeBuf    []float32
	encodeBufPos int

	lastCaptureAt     time.Time
	keepaliveStop     chan struct{}
	dropCaptureCount  int
	peerAudioCount    int

	OnStateChange func(*CallInfo)
	OnIncoming    func(*CallInfo)
	OnEnded       func(*CallInfo)
	OnPeerAudio   func([]float32)
}

func NewCallManager(sock core.VoipSocket, log *slog.Logger) *CallManager {
	if log == nil {
		log = slog.Default()
	}
	m := &CallManager{
		sock:        sock,
		log:         log,
		debeEnabled: true,
	}
	relay := transport.NewSctpRelayManager(log)
	relay.SetOnConnected(func(ip string, port int) { m.onRelayConnected() })
	relay.SetOnReceive(func(data []byte) { m.onRelayData(data) })
	m.relay = relay
	return m
}

func (m *CallManager) CurrentCall() *CallInfo {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.currentCall
}

func (m *CallManager) emitState() {
	if m.OnStateChange != nil && m.currentCall != nil {
		m.OnStateChange(m.currentCall)
	}
}

func (m *CallManager) StartCall(ctx context.Context, callID string, peerJid types.JID, isVideo bool) error {
	m.mu.Lock()
	if m.currentCall != nil && !m.currentCall.IsEnded() {
		m.mu.Unlock()
		return &CallError{"a call is already in progress"}
	}

	mediaType := core.CallMediaTypeAudio
	if isVideo {
		mediaType = core.CallMediaTypeVideo
	}
	creator := m.sock.OwnLID()
	if creator.IsEmpty() {
		creator = m.sock.OwnPN()
	}
	resolved := m.sock.ResolveLIDForPN(ctx, peerJid)

	call := NewOutgoingCall(callID, resolved.String(), creator.String(), mediaType)
	callKey := media.GenerateCallKey()
	call.EncryptionKey = callKey
	m.currentCall = call
	m.initialTransportSent = false
	m.outgoingPreacceptSent = false

	selfJid := creator.String()
	m.selfSsrc = media.GenerateSecureSsrc(callID, selfJid, 0)
	m.rtpSession = media.NewWhatsAppOpusSession(m.selfSsrc)
	m.peerSsrcs = []uint32{media.GenerateSecureSsrc(callID, resolved.String(), 0)}
	m.initCodec()
	m.mu.Unlock()

	offer, err := signaling.BuildOfferStanza(ctx, m.sock, callID, callKey, resolved, isVideo)
	if err != nil {
		return err
	}

	m.mu.Lock()
	_ = m.currentCall.ApplyTransition(Transition{Type: TransitionOfferSent})
	m.emitState()
	m.mu.Unlock()

	// Envia o offer e trata o ack em background: o aparelho toca quando recebe o
	// offer, não quando o Query retorna. Antes travava até 15s no timeout do Query.
	go func() {
		ackNode, qerr := m.sock.Query(context.Background(), offer)
		if qerr != nil {
			m.log.Error("offer query error", "err", qerr)
			return
		}
		if ackNode != nil {
			m.log.Info("offer ack", "xml", ackNode.String())
			m.HandleCallAck(context.Background(), ackNode)
		}
	}()

	m.log.Info("call offer sent", "call_id", callID, "peer", resolved.String())
	return nil
}

func (m *CallManager) AcceptCall(ctx context.Context, callID string) error {
	m.mu.Lock()
	call := m.currentCall
	if call == nil || call.CallID != callID {
		m.mu.Unlock()
		return &CallError{"no incoming call with id " + callID}
	}
	if !call.CanAccept() {
		m.mu.Unlock()
		return &CallError{"call cannot be accepted in state " + string(call.StateData.State)}
	}
	_ = call.ApplyTransition(Transition{Type: TransitionLocalAccepted})
	m.emitState()
	key := call.EncryptionKey
	peer := wanode.MustJID(call.PeerJid)
	creator := wanode.MustJID(call.CallCreator)
	isVideo := call.MediaType == core.CallMediaTypeVideo
	relayData := call.RelayData
	m.mu.Unlock()

	if key != nil {
		acceptNode, err := signaling.BuildAcceptStanza(ctx, m.sock, callID, key, peer, creator, isVideo)
		if err != nil {
			m.log.Error("build accept failed", "err", err)
		} else {
			// envia o accept em background: não bloquear a UI até 15s no timeout do ack
			go func() {
				if _, err := m.sock.Query(context.Background(), acceptNode); err != nil {
					m.log.Error("accept query error", "err", err)
				}
			}()
		}
	}

	if relayData != nil {
		m.connectRelays(relayData.Endpoints)
	}
	m.log.Info("call accepted", "call_id", callID)
	return nil
}

func (m *CallManager) RejectCall(ctx context.Context, callID string, reason core.EndCallReason) error {
	m.mu.Lock()
	call := m.currentCall
	if call == nil || call.CallID != callID {
		m.mu.Unlock()
		return &CallError{"no call with id " + callID}
	}
	peerJid := wanode.MustJID(call.PeerJid)
	creatorJid := wanode.MustJID(call.CallCreator)
	callIDStr := call.CallID
	callerAlt := m.callerAlt
	if callerAlt.IsEmpty() && call.CallerPn != "" {
		callerAlt = wanode.MustJID(call.CallerPn)
	}
	peerDevice := m.peerDeviceJid
	ownFrom := m.sock.OwnPN()
	if ownFrom.IsEmpty() {
		ownFrom = m.sock.OwnLID()
	}
	// Marca ended só DEPOIS de montar os destinos — emitState remove a call do registry.
	_ = call.ApplyTransition(Transition{Type: TransitionLocalRejected, Reason: reason})
	m.mu.Unlock()

	sendReject := func(to, creator types.JID, label string) {
		if to.IsEmpty() || creator.IsEmpty() {
			return
		}
		node := signaling.BuildRejectCallNode(ownFrom, to, creator, callIDStr)
		if err := m.sock.SendNode(ctx, node); err != nil {
			m.log.Warn("reject send failed", "via", label, "to", to.String(), "err", err)
		} else {
			m.log.Info("reject sent", "via", label, "to", to.String(), "creator", creator.String(), "call_id", callIDStr)
		}
	}

	// 1) Principal (Baileys): to = peer do offer (LID), call-creator = creator do offer (LID).
	sendReject(peerJid, creatorJid, "peer+creator")

	// 2) Device específico do peer (relaylatency) — costuma ser o aparelho que está tocando.
	if peerDevice != "" {
		sendReject(wanode.MustJID(peerDevice), creatorJid, "peer-device")
	}

	// 3) Device :0 do LID
	peerDev0 := peerJid
	peerDev0.Device = 0
	sendReject(peerDev0, creatorJid, "peer:0")

	// 4) PN do cliente com call-creator = LID do offer (casa com a oferta LID).
	if !callerAlt.IsEmpty() {
		sendReject(callerAlt.ToNonAD(), creatorJid, "pn+lid-creator")
		sendReject(callerAlt.ToNonAD(), callerAlt.ToNonAD(), "pn+pn-creator")
	}

	// Terminate reforça o fim.
	_ = m.sock.SendNode(ctx, signaling.BuildTerminateStanza(peerJid, callIDStr, creatorJid))
	if peerDevice != "" {
		_ = m.sock.SendNode(ctx, signaling.BuildTerminateStanza(wanode.MustJID(peerDevice), callIDStr, creatorJid))
	}
	if !callerAlt.IsEmpty() {
		_ = m.sock.SendNode(ctx, signaling.BuildTerminateStanza(callerAlt.ToNonAD(), callIDStr, creatorJid))
	}

	m.log.Info("sent reject+terminate", "peer", peerJid.String(), "peer_device", peerDevice, "pn", callerAlt.String(), "call_id", callIDStr)

	m.mu.Lock()
	m.emitState()
	m.mu.Unlock()
	m.cleanupMedia()
	return nil
}

func (m *CallManager) SetCallerAlt(jid types.JID) {
	m.mu.Lock()
	m.callerAlt = jid
	m.mu.Unlock()
}

func (m *CallManager) SetPeerName(name string) {
	m.mu.Lock()
	m.peerName = name
	m.mu.Unlock()
}

func (m *CallManager) EndCall(ctx context.Context, reason core.EndCallReason) error {
	m.mu.Lock()
	call := m.currentCall
	if call == nil || call.IsEnded() {
		m.mu.Unlock()
		return nil
	}
	_ = call.ApplyTransition(Transition{Type: TransitionTerminated, Reason: reason})
	node := signaling.BuildTerminateStanza(wanode.MustJID(call.PeerJid), call.CallID, wanode.MustJID(call.CallCreator))
	ended := call
	m.emitState()
	m.mu.Unlock()

	go func() { _ = m.sock.SendNode(context.Background(), node) }()
	if m.OnEnded != nil {
		m.OnEnded(ended)
	}
	m.cleanupMedia()
	return nil
}

func (m *CallManager) ownCredJid() string {
	lid := m.sock.OwnLID()
	if !lid.IsEmpty() {
		return lid.String()
	}
	return m.sock.OwnPN().String()
}

type CallError struct{ Msg string }

func (e *CallError) Error() string { return e.Msg }
