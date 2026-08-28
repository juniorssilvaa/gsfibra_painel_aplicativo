package main

import (
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
)

// browserAPI é inicializado uma única vez. Quando WACALLS_PUBLIC_IP e
// WACALLS_UDP_PORT estão definidos, o WebRTC com o navegador usa porta fixa
// (UDP + ICE-TCP na mesma porta) e anuncia o IP público como candidato (NAT 1:1).
// O ICE-TCP garante a mídia mesmo quando UDP de entrada é bloqueado.
var (
	browserAPIOnce sync.Once
	browserAPI     *webrtc.API
)

// detectPublicIP descobre o IP público real do host. Em produção o serviço roda
// dentro de um container Docker (rede overlay, sem network_mode: host), então
// olhar o endereço local do socket de saída (LocalAddr) retorna o IP INTERNO
// do overlay (ex.: 172.18.x.x) — inalcançável pelo navegador do atendente, o que
// resulta em ligação sem áudio. Por isso perguntamos a um serviço externo de
// "echo IP", que vê o endereço já depois do NAT do host. Se não houver saída
// para a internet, cai no fallback antigo (IP da interface de saída padrão).
func detectPublicIP() string {
	if ip := detectPublicIPViaEcho(); ip != "" {
		return ip
	}
	if ip := detectLocalOutboundIP(); ip != "" && !isPrivateOrLocalIP(ip) {
		return ip
	}
	return ""
}

func detectPublicIPViaEcho() string {
	client := &http.Client{Timeout: 3 * time.Second}
	for _, url := range []string{
		"https://api.ipify.org",
		"https://ifconfig.me/ip",
		"https://icanhazip.com",
	} {
		resp, err := client.Get(url)
		if err != nil {
			continue
		}
		body, err := io.ReadAll(io.LimitReader(resp.Body, 64))
		resp.Body.Close()
		if err != nil {
			continue
		}
		ip := strings.TrimSpace(string(body))
		if net.ParseIP(ip) != nil && !isPrivateOrLocalIP(ip) {
			return ip
		}
	}
	return ""
}

func detectLocalOutboundIP() string {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return ""
	}
	defer conn.Close()
	if a, ok := conn.LocalAddr().(*net.UDPAddr); ok {
		return a.IP.String()
	}
	return ""
}

func isPrivateOrLocalIP(s string) bool {
	ip := net.ParseIP(s)
	if ip == nil {
		return true
	}
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsUnspecified() {
		return true
	}
	if ip4 := ip.To4(); ip4 != nil {
		switch {
		case ip4[0] == 10:
			return true
		case ip4[0] == 172 && ip4[1] >= 16 && ip4[1] <= 31:
			return true
		case ip4[0] == 192 && ip4[1] == 168:
			return true
		case ip4[0] == 100 && ip4[1] >= 64 && ip4[1] <= 127: // CGNAT
			return true
		}
	}
	return false
}

func getBrowserAPI(log *slog.Logger) *webrtc.API {
	browserAPIOnce.Do(func() {
		publicIP := strings.TrimSpace(os.Getenv("WACALLS_PUBLIC_IP"))
		udpPort, _ := strconv.Atoi(os.Getenv("WACALLS_UDP_PORT"))
		if publicIP == "auto" || publicIP == "" {
			detected := detectPublicIP()
			if detected != "" {
				publicIP = detected
				log.Info("browser webrtc: auto-detected public IP", "ip", publicIP)
			} else {
				log.Warn("browser webrtc: could not auto-detect public IP")
				publicIP = ""
			}
		} else if isPrivateOrLocalIP(publicIP) {
			log.Warn("browser webrtc: WACALLS_PUBLIC_IP is private/local; ignoring", "ip", publicIP)
			publicIP = ""
		}
		if publicIP == "" || udpPort == 0 {
			browserAPI = webrtc.NewAPI()
			return
		}
		se := webrtc.SettingEngine{}
		se.SetNAT1To1IPs([]string{publicIP}, webrtc.ICECandidateTypeHost)
		se.SetNetworkTypes([]webrtc.NetworkType{
			webrtc.NetworkTypeUDP4, webrtc.NetworkTypeUDP6,
			webrtc.NetworkTypeTCP4, webrtc.NetworkTypeTCP6,
		})
		udpConn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: udpPort})
		if err != nil {
			log.Error("browser webrtc: bind udp mux failed; falling back to ephemeral", "port", udpPort, "err", err)
			browserAPI = webrtc.NewAPI()
			return
		}
		se.SetICEUDPMux(webrtc.NewICEUDPMux(nil, udpConn))
		log.Info("browser webrtc: fixed udp port + nat1to1 enabled", "public_ip", publicIP, "udp_port", udpPort)
		if tcpListener, terr := net.ListenTCP("tcp", &net.TCPAddr{IP: net.IPv4zero, Port: udpPort}); terr == nil {
			se.SetICETCPMux(webrtc.NewICETCPMux(nil, tcpListener, 8))
			log.Info("browser webrtc: ice-tcp fallback enabled", "tcp_port", udpPort)
		} else {
			log.Error("browser webrtc: ice-tcp bind failed", "port", udpPort, "err", terr)
		}
		browserAPI = webrtc.NewAPI(webrtc.WithSettingEngine(se))
	})
	return browserAPI
}

type Bridge struct {
	pc         *webrtc.PeerConnection
	localTrack *webrtc.TrackLocalStaticSample
	log        *slog.Logger

	OnBrowserRTP  func(payload []byte)
	OnTerminalICE func()
}

func NewBridge(offerSDP string, log *slog.Logger) (*Bridge, string, error) {
	pc, err := getBrowserAPI(log).NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		return nil, "", err
	}

	br := &Bridge{pc: pc, log: log}

	localTrack, err := webrtc.NewTrackLocalStaticSample(

		webrtc.RTPCodecCapability{
			MimeType:    webrtc.MimeTypeOpus,
			ClockRate:   48000,
			Channels:    2,
			SDPFmtpLine: "minptime=10;useinbandfec=1",
		},
		"audio", "wacalls",
	)
	if err != nil {
		pc.Close()
		return nil, "", err
	}
	br.localTrack = localTrack

	pc.OnTrack(func(tr *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		go func() {
			for {
				pkt, _, err := tr.ReadRTP()
				if err != nil {
					return
				}
				if br.OnBrowserRTP != nil && len(pkt.Payload) > 0 {
					br.OnBrowserRTP(pkt.Payload)
				}
			}
		}()
	})

	pc.OnICEConnectionStateChange(func(s webrtc.ICEConnectionState) {
		log.Debug("browser ice state", "state", s.String())
		if s == webrtc.ICEConnectionStateFailed || s == webrtc.ICEConnectionStateClosed {
			if br.OnTerminalICE != nil {
				br.OnTerminalICE()
			}
		}
	})

	if err := pc.SetRemoteDescription(webrtc.SessionDescription{Type: webrtc.SDPTypeOffer, SDP: offerSDP}); err != nil {
		pc.Close()
		return nil, "", err
	}
	if _, err := pc.AddTrack(localTrack); err != nil {
		pc.Close()
		return nil, "", err
	}
	answer, err := pc.CreateAnswer(nil)
	if err != nil {
		pc.Close()
		return nil, "", err
	}
	gatherComplete := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(answer); err != nil {
		pc.Close()
		return nil, "", err
	}
	<-gatherComplete

	return br, pc.LocalDescription().SDP, nil
}

func (b *Bridge) WriteOpus(payload []byte, dur time.Duration) error {
	if b.localTrack == nil {
		return nil
	}
	return b.localTrack.WriteSample(media.Sample{Data: payload, Duration: dur})
}

func (b *Bridge) Close() {
	if b.pc != nil {
		_ = b.pc.Close()
	}
}
