import React, { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from '../lib/notify';
import axios from 'axios';
import { MessageCircle, Send, XCircle, Edit2, Plus, Save, Globe, MoreVertical, Trash2, Copy, Check, Phone, Smartphone } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import niohubLogo from '../assets/logo.png';
import { buildAuthenticatedWebSocketUrl, buildPainelWebSocketEndpoint } from '../utils/websocketUrl';
import { getApiBaseUrl, buildApiPath } from '../utils/apiBaseUrl';
import { useNavigate } from 'react-router-dom';
import { Switch } from './ui/switch';
import instagramIcon from '../assets/instagram.png';
import whatsappIcon from '../assets/whatsapp.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';

const MODAL_INPUT_CLASS =
  'bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2.5 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/60 focus:border-primary/50 transition w-full';

const MODAL_INPUT_COMPACT_CLASS =
  'bg-[#1a1b2e] border border-[#35365a] text-white px-2.5 py-2 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/60 focus:border-primary/50 transition w-full';

const CHANNEL_TYPE_ICONS = {
  whatsapp_oficial: whatsappIcon,
  whatsapp: whatsappIcon,
  whatsapp_session: whatsappIcon,
  telegram: telegramIcon,
  email: gmailIcon,
  instagram: instagramIcon,
};

const WHATSAPP_TYPE_META = {
  whatsapp_oficial: {
    title: 'WhatsApp Oficial',
    subtitle: 'API Cloud Meta — número verificado',
    description:
      'Conecte via Meta Business para enviar templates, botões interativos, cobranças PIX/boleto e CSAT.',
    bullets: [
      'Conta Meta Business e número aprovado na Cloud API',
      'Suporte a listas, order details e mensagens interativas',
      'Conexão guiada após criar a instância',
    ],
  },
  whatsapp: {
    title: 'WhatsApp',
    subtitle: 'Instância dedicada no painel',
    description:
      'Crie uma instância com nome único para conectar seu WhatsApp e centralizar os atendimentos.',
    bullets: [
      'Escolha um nome fácil de identificar (ex.: Suporte, Financeiro)',
      'Após salvar, use QR Code ou código de pareamento para conectar',
      'Ideal para operação via integração Evolution/Uazapi',
    ],
  },
  whatsapp_session: {
    title: 'WhatsApp QR Code',
    subtitle: 'Pareamento rápido por QR',
    description:
      'Conecte o WhatsApp escaneando o QR Code ou informando o código de pareamento no celular.',
    bullets: [
      'Mantenha o celular conectado à internet durante o pareamento',
      'Evite bloqueios: comece com mensagens manuais antes da automação',
      'Nome da instância ajuda a organizar múltiplos números',
    ],
  },
};

function AddChannelModalHeader({ image, icon: Icon, iconClassName, title, subtitle, compact = false }) {
  return (
    <div className={`flex items-center ${compact ? 'gap-2' : 'gap-3'}`}>
      <div
        className={`${compact ? 'w-9 h-9 rounded-lg' : 'w-11 h-11 rounded-xl'} bg-muted border border-border flex items-center justify-center shrink-0`}
      >
        {image ? (
          <img src={image} alt="" className={`${compact ? 'w-5 h-5' : 'w-6 h-6'} object-contain`} />
        ) : Icon ? (
          <Icon className={`${compact ? 'w-4 h-4' : 'w-5 h-5'} ${iconClassName || 'text-primary'}`} />
        ) : null}
      </div>
      <div className="min-w-0">
        <p className={`${compact ? 'text-sm' : 'text-sm'} font-semibold text-foreground`}>{title}</p>
        {subtitle ? <p className="text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
    </div>
  );
}

function AddChannelInfoBox({ description, bullets = [], compact = false }) {
  if (compact) {
    return description ? (
      <p className="text-xs text-muted-foreground rounded-md border border-border bg-muted/30 px-3 py-2 leading-snug">
        {description}
      </p>
    ) : null;
  }

  return (
    <div className="rounded-lg border border-border border-l-4 border-l-primary bg-muted/40 p-4 space-y-3">
      {description ? (
        <p className="text-sm text-foreground leading-relaxed">{description}</p>
      ) : null}
      {bullets.length > 0 ? (
        <ul className="text-xs text-muted-foreground space-y-1.5">
          {bullets.map((item, idx) => (
            <li key={typeof item === 'string' ? item : idx} className="flex items-start gap-2">
              <span className="mt-0.5 text-primary font-bold shrink-0">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function AddChannelField({ label, hint, children, compact = false }) {
  return (
    <div className={`flex flex-col ${compact ? 'gap-1' : 'gap-1.5'}`}>
      <label className={`${compact ? 'text-xs' : 'text-sm'} font-semibold text-foreground`}>{label}</label>
      {children}
      {hint ? <p className="text-[11px] text-muted-foreground leading-tight">{hint}</p> : null}
    </div>
  );
}

function AddChannelFooter({
  cancelLabel,
  onCancel,
  submitLabel,
  loadingLabel,
  onSubmit,
  disabled = false,
  loading = false,
}) {
  return (
    <div className="flex justify-end gap-2 pt-1">
      <button
        type="button"
        onClick={onCancel}
        className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-semibold shadow transition"
      >
        {cancelLabel}
      </button>
      <button
        type="button"
        onClick={onSubmit}
        disabled={disabled || loading}
        className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg text-sm font-semibold shadow transition disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? loadingLabel : submitLabel}
      </button>
    </div>
  );
}

function StatusBadge({ status, t }) {
  let color = 'bg-yellow-500';
  let text = 'text-yellow-900';
  let statusText = t('desconectado');

  if (status === 'processing' || status === 'Conectando...') {
    color = 'bg-yellow-500';
    text = 'text-yellow-900';
    statusText = 'Conectando...';
  } else if (status === 'Conectado' || status === 'connected' || status === 'open') {
    color = 'bg-green-500';
    text = 'text-green-900';
    statusText = t('conectado');
  } else if (status === 'Desconectado' || status === 'disconnected') {
    color = 'bg-red-500';
    text = 'text-red-900';
    statusText = t('desconectado');
  }

  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${color} ${text}`}>
      {statusText}
    </span>
  );
}

function ChannelCard({ channel, onConnect, onDelete, onDisconnect, onCheckStatus, onDeleteInstance, deletingChannelId, isProcessing, onToggleIA, onVoiceCallsSetup, onVoiceCallsDisable, voiceCallsBusyId, providerConfig, onEditName, t }) {
  const [canalIdCopied, setCanalIdCopied] = React.useState(false);
  const [authProfileSrc, setAuthProfileSrc] = React.useState(null);
  const [profileLoadFailed, setProfileLoadFailed] = React.useState(false);
  const isWhatsapp = channel.tipo === 'whatsapp' || channel.tipo === 'whatsapp_session';
  const isWhatsappOficial = channel.tipo === 'whatsapp_oficial';
  const isInstagram = channel.tipo === 'instagram';
  const isAppMobile = channel.tipo === 'app_mobile';
  const voiceCalls = channel.dados_extras?.voice_calls || {};
  const voiceCallsStatus = voiceCalls.status || 'disabled';
  const voiceCallsConnected = voiceCallsStatus === 'connected';
  const voiceCallsPairing = voiceCallsStatus === 'pairing';
  const voiceCallsBusy = voiceCallsBusyId === channel.id;

  const copyCanalId = async () => {
    const id = String(channel.id ?? '');
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      const el = document.createElement('textarea');
      el.value = id;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCanalIdCopied(true);
    setTimeout(() => setCanalIdCopied(false), 2000);
  };

  // Usar state do backend (que vem como 'open', 'connected', etc) ou status do frontend
  const channelState = channel.state || channel.status;
  // Para WhatsApp Oficial, verificar se está ativo E status é 'connected'
  // Se estiver em processing, não considerar conectado
  const isConnected = isAppMobile
    ? Boolean(channel.app_token_verified) && (channelState === 'connected' || channelState === 'open')
    : isWhatsappOficial
    ? (!isProcessing && channel.ativo && channelState === 'connected')
    : isInstagram
      ? (channelState === 'connected' && Boolean((channel.dados_extras || {}).instagram_user_id))
      : (channelState === 'open' || channelState === 'connected' || channelState === 'Conectado');

  // Para WhatsApp Oficial, verificar se está em processamento
  const isProcessingState = isWhatsappOficial && isProcessing;
  const perdeuConexaoMeta = isWhatsappOficial && !isConnected && !isProcessingState && Boolean(channel.phone_number_id);

  // Obter status da sessão WhatsApp (Uazapi) se disponível
  // whatsapp_session é o valor do banco de dados para sessões Uazapi
  const sessionStatus = channel.tipo === 'whatsapp_session' ? channel.sessionStatus : null;

  // Obter informações do Telegram se disponível
  const telegramInfo = channel.tipo === 'telegram' ? channel.telegramInfo : null;
  const telegramStatus = channel.tipo === 'telegram' ? channel.telegramStatus : null;

  // Buscar foto de perfil de múltiplas fontes
  // Para sessão WhatsApp (Uazapi): sessionStatus.instance.profilePicUrl > sessionStatus.profilePicUrl
  // Para Telegram: telegramInfo.profile_pic (já vem como data URL)
  // Fallback: channel.profile_pic > dados_extras.profilePicUrl
  // WhatsApp Oficial: NÃO usar URL crua da Meta (fbcdn) — exige proxy autenticado
  const profileName = sessionStatus?.instance?.profileName || sessionStatus?.profileName || telegramInfo?.first_name;
  const status = sessionStatus?.status || telegramStatus?.status || channelState;

  const isMetaCdnUrl = (url) => {
    if (!url || typeof url !== 'string') return false;
    return /fbcdn\.net|scontent|lookaside\.fbsbx|facebook\.com\/.*\/picture/i.test(url);
  };

  // Primeiro, buscar foto de perfil de todas as fontes possíveis
  let profilePicRaw = (
    (sessionStatus?.instance?.profilePicUrl) ||
    (sessionStatus?.profilePicUrl) ||
    (telegramInfo?.profile_pic) ||
    (telegramInfo?.profile_pic_base64) ||
    channel.profile_pic ||
    (channel.dados_extras?.profilePicUrl) ||
    (channel.dados_extras?.profile_picture_url) ||
    null
  );

  // WhatsApp Oficial: preferir proxy do backend; nunca apontar <img> direto para CDN Meta
  if (isWhatsappOficial) {
    if (!profilePicRaw || isMetaCdnUrl(profilePicRaw)) {
      profilePicRaw = buildApiPath(`/api/whatsapp/profile-picture/proxy/?channel_id=${channel.id}`);
    }
  }

  // Verificar se o canal está desconectado
  const isDisconnected = status === 'disconnected' || status === 'Disconectado' ||
    (sessionStatus?.connected === false && sessionStatus?.loggedIn === false) ||
    (!isConnected && (channel.tipo === 'whatsapp' || channel.tipo === 'whatsapp_session' || channel.tipo === 'whatsapp_oficial' || channel.tipo === 'instagram'));

  // CORREÇÃO: Mostrar GIF APENAS se canal está desconectado
  // Se conectado, SEMPRE mostrar foto (mesmo que seja null, não mostrar GIF)
  // Se desconectado, SEMPRE mostrar GIF (nunca mostrar foto)
  const shouldShowGif = isDisconnected;

  // Adicionar cache-busting se a foto viera de uma URL externa (não data URL)
  // Usa o status como chave para forçar recarregamento quando o status muda
  // CORREÇÃO: Só processar profilePic se não deve mostrar GIF (ou seja, se está conectado)
  // NÃO adicionar ?v= em URLs assinadas da Meta (quebra a assinatura)
  const statusKey = status || 'unknown';
  const needsAuthFetch = isWhatsappOficial && !shouldShowGif && Boolean(profilePicRaw) && !String(profilePicRaw).startsWith('data:');
  const profilePic = shouldShowGif ? null : (
    profilePicRaw && profilePicRaw.startsWith('data:')
      ? profilePicRaw
      : profilePicRaw
        ? (isMetaCdnUrl(profilePicRaw) || needsAuthFetch
            ? profilePicRaw
            : `${profilePicRaw}${profilePicRaw.includes('?') ? '&' : '?'}v=${statusKey}-${channel.id || '0'}`)
        : null
  );

  // <img> não envia Authorization — baixar via fetch autenticado e usar blob URL
  React.useEffect(() => {
    setProfileLoadFailed(false);
    if (!needsAuthFetch || !profilePicRaw) {
      setAuthProfileSrc(null);
      return undefined;
    }
    let cancelled = false;
    let objectUrl = null;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    const proxyUrl = buildApiPath(`/api/whatsapp/profile-picture/proxy/?channel_id=${channel.id}`);

    (async () => {
      try {
        const res = await fetch(proxyUrl, {
          headers: token ? { Authorization: `Token ${token}` } : {},
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const nextUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        objectUrl = nextUrl;
        setAuthProfileSrc(nextUrl);
      } catch {
        if (!cancelled) {
          setAuthProfileSrc(null);
          setProfileLoadFailed(true);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [needsAuthFetch, profilePicRaw, channel.id]);

  const displayProfilePic = needsAuthFetch ? authProfileSrc : profilePic;

  return (
    <div className="bg-card p-6 rounded-xl shadow-lg border border-border flex justify-between items-center relative">
      <div className="flex items-center gap-4">
        {channel.tipo === 'whatsapp_session' ? (
          <div className={`w-16 h-16 rounded-full overflow-hidden flex items-center justify-center relative -top-1 ${!shouldShowGif && profilePic ? 'bg-orange-500' : 'bg-black'}`}>
            {shouldShowGif ? (
              <img key={`null-${channel.id}-${status}`} src={niohubLogo} alt="NioHub" className="w-full h-full object-contain p-1" />
            ) : (
              <img key={`profile-${channel.id}-${status}`} src={profilePic} alt="Profile" className="w-full h-full object-cover" />
            )}
          </div>
        ) : channel.tipo === 'whatsapp' ? (
          <div className={`w-16 h-16 rounded-full overflow-hidden flex items-center justify-center relative -top-1 ${!shouldShowGif && profilePic ? 'bg-green-500' : 'bg-black'}`}>
            {shouldShowGif ? (
              <img key={`null-${channel.id}-${status}`} src={niohubLogo} alt="NioHub" className="w-full h-full object-contain p-1" />
            ) : (
              <img key={`profile-${channel.id}-${status}`} src={profilePic} alt="Profile" className="w-full h-full object-cover" />
            )}
          </div>
        ) : channel.tipo === 'telegram' ? (
          <div className="w-16 h-16 rounded-full overflow-hidden flex items-center justify-center bg-blue-500 relative -top-1">
            {profilePic ? (
              <img src={profilePic} alt="Profile" className="w-full h-full object-cover" />
            ) : (
              <Send className="w-8 h-8 text-white" />
            )}
          </div>
        ) : channel.tipo === 'whatsapp_oficial' ? (
          <div className={`w-16 h-16 rounded-full overflow-hidden flex items-center justify-center relative -top-1 ${!shouldShowGif && displayProfilePic ? 'bg-green-500' : 'bg-black'}`}>
            {shouldShowGif ? (
              <img key={`null-${channel.id}-${status}`} src={niohubLogo} alt="NioHub" className="w-full h-full object-contain p-1" />
            ) : displayProfilePic && !profileLoadFailed ? (
              <img
                key={`profile-${channel.id}-${status}`}
                src={displayProfilePic}
                alt=""
                className="w-full h-full object-cover"
                onError={() => setProfileLoadFailed(true)}
              />
            ) : (
              <img src={whatsappIcon} alt="WhatsApp" className="w-9 h-9 object-contain" />
            )}
          </div>
        ) : channel.tipo === 'instagram' ? (
          <div className={`w-16 h-16 rounded-full overflow-hidden flex items-center justify-center relative -top-1 ${!shouldShowGif && profilePic ? 'bg-gradient-to-br from-purple-600 to-pink-500' : 'bg-gradient-to-br from-purple-600 to-pink-500'}`}>
            {shouldShowGif ? (
              <img src={instagramIcon} alt="Instagram" className="w-9 h-9 object-contain" />
            ) : profilePic ? (
              <img key={`ig-profile-${channel.id}-${status}`} src={profilePic} alt="Instagram" className="w-full h-full object-cover" />
            ) : (
              <img src={instagramIcon} alt="Instagram" className="w-9 h-9 object-contain" />
            )}
          </div>
        ) : channel.tipo === 'app_mobile' ? (
          <div className="w-16 h-16 rounded-full overflow-hidden flex items-center justify-center bg-muted border border-border relative -top-1">
            <Smartphone className="w-9 h-9 text-orange-500" />
          </div>
        ) : (
          <div className="w-16 h-16 bg-primary rounded-full flex items-center justify-center relative -top-1">
            <Globe className="w-8 h-8 text-primary-foreground" />
          </div>
        )}
        <div>
          <div className="flex items-center gap-2">
            <div className="font-bold text-lg text-foreground">
              {channel.nome || (
                channel.tipo === 'whatsapp_session' ? 'WhatsApp QR code' :
                  channel.tipo === 'telegram' ? 'Telegram' :
                    channel.tipo === 'whatsapp_oficial' ? 'WhatsApp Oficial' :
                      channel.tipo === 'instagram' ? 'Instagram' :
                        channel.tipo === 'app_mobile' ? 'App Mobile' :
                        channel.tipo
              )}
            </div>
            <button
              onClick={() => onEditName(channel)}
              className="p-1 hover:bg-muted rounded transition text-muted-foreground hover:text-foreground"
              title="Editar nome"
            >
              <Edit2 className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="text-xs text-muted-foreground capitalize">
            {channel.tipo === 'whatsapp_session' ? 'WhatsApp QR code' :
              channel.tipo === 'telegram' ? 'Telegram' :
                channel.tipo === 'whatsapp_oficial' ? 'WhatsApp Oficial' :
                  channel.tipo === 'instagram' ? 'Instagram' :
                    channel.tipo === 'app_mobile' ? 'App Mobile' :
                    channel.tipo}
          </div>
          {/* Mostrar número do WhatsApp Oficial quando conectado */}
          {isWhatsappOficial && (
            <div className="mt-1 space-y-0.5">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                Número: <span className="text-foreground font-medium">{channel.phone_number || channel.display_phone_number || 'Não definido'}</span>
              </p>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1 flex-wrap">
                <span>
                  ID do canal:{' '}
                  <span className="text-primary font-mono font-semibold">{channel.id}</span>
                </span>
                <button
                  type="button"
                  onClick={copyCanalId}
                  className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-semibold normal-case tracking-normal text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                >
                  {canalIdCopied ? (
                    <>
                      <Check className="w-3 h-3 text-green-500" />
                      Copiado
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      Copiar
                    </>
                  )}
                </button>
              </p>
              {isConnected && onVoiceCallsSetup && (
                <div className="mt-2 pt-2 border-t border-border/60 space-y-2 normal-case tracking-normal">
                  <div className="flex flex-wrap items-center gap-2">
                    <Phone className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span className="text-[11px] text-muted-foreground">Ligações no NioHub</span>
                    {voiceCallsConnected ? (
                      <span className="rounded-full bg-green-500/15 px-2 py-0.5 text-[10px] font-semibold text-green-400">
                        Voz conectada
                      </span>
                    ) : voiceCallsPairing ? (
                      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                        Aguardando QR
                      </span>
                    ) : null}
                  </div>
                  <p className="text-[9px] text-muted-foreground leading-snug">
                    O QR abaixo é só para ligações.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {!voiceCallsConnected && (
                      <button
                        type="button"
                        disabled={voiceCallsBusy || isProcessingState}
                        onClick={() => onVoiceCallsSetup(channel.id, voiceCallsPairing ? 'repair' : 'setup')}
                        className="rounded-md bg-primary/90 px-2.5 py-1 text-[11px] font-semibold text-primary-foreground hover:bg-primary disabled:opacity-50"
                      >
                        {voiceCallsBusy
                          ? 'Aguarde...'
                          : voiceCallsPairing
                            ? 'Ver QR novamente'
                            : 'Ativar ligações'}
                      </button>
                    )}
                    {(voiceCallsConnected || voiceCallsPairing || voiceCalls.enabled) && onVoiceCallsDisable && (
                      <button
                        type="button"
                        disabled={voiceCallsBusy || isProcessingState}
                        onClick={() => onVoiceCallsDisable(channel.id)}
                        className="rounded-md border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
                      >
                        Desativar ligações
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
          {/* Mostrar informações do usuário do Telegram se disponível */}
          {channel.tipo === 'telegram' && telegramInfo && (
            <div className="text-xs text-gray-400">
              {telegramInfo.username && <span className="text-blue-300">@{telegramInfo.username}</span>}
              {telegramInfo.username && telegramInfo.telegram_id && <span className="mx-1">•</span>}
              {telegramInfo.telegram_id && <span>ID: {telegramInfo.telegram_id}</span>}
            </div>
          )}
          {channel.tipo === 'instagram' && (channel.dados_extras?.instagram_username || channel.dados_extras?.instagram_user_id) && (
            <div className="text-xs text-gray-400 mt-1">
              {channel.dados_extras?.instagram_username && (
                <span className="text-pink-300">@{channel.dados_extras.instagram_username}</span>
              )}
              {channel.dados_extras?.instagram_username && channel.dados_extras?.instagram_user_id && (
                <span className="mx-1">•</span>
              )}
              {channel.dados_extras?.instagram_user_id && (
                <span>ID: {channel.dados_extras.instagram_user_id}</span>
              )}
            </div>
          )}
          {channel.tipo === 'app_mobile' && (channel.token_suffix || channel.dados_extras?.app_token_suffix) && (
            <div className="text-xs text-muted-foreground mt-1 font-mono">
              Token: sk_live_…{channel.token_suffix || channel.dados_extras?.app_token_suffix}
            </div>
          )}
          {channel.tipo === 'app_mobile' && (channel.app_default_team_id || channel.dados_extras?.app_default_team_id) && (
            <div className="text-xs text-muted-foreground mt-1">
              Fila:{' '}
              <span className="text-foreground font-medium">
                {channel.app_default_team_name
                  || channel.dados_extras?.app_default_team_name
                  || 'Equipe'}{' '}
                (#{channel.app_default_team_id || channel.dados_extras?.app_default_team_id})
              </span>
            </div>
          )}
        </div>
      </div>
      {/* Toggle IA + lixeira no canto direito absoluto */}
      <div className="absolute top-2 right-2 flex items-center gap-2">
        {isConnected && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">{providerConfig?.chatbot_mode ? 'Automação' : 'IA'}:</span>
            <Switch
              checked={channel.ia_ativa !== false}
              onCheckedChange={(checked) => onToggleIA(channel.id, checked)}
              disabled={isProcessingState}
            />
          </div>
        )}
        <button
          onClick={() => onDeleteInstance(channel)}
          disabled={deletingChannelId === channel.id}
          className="bg-gradient-to-r from-gray-700 to-gray-900 hover:from-red-600 hover:to-red-800 text-white p-1 rounded-full text-xs font-semibold shadow disabled:opacity-50 disabled:cursor-not-allowed"
          title={deletingChannelId === channel.id ? 'Deletando...' : t('deletar_instancia')}
        >
          {deletingChannelId === channel.id ? (
            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>
          )}
        </button>
      </div>
      <div className="flex items-center gap-2">
        {/* Badge de status */}
        {isProcessingState ? (
          <div className="flex items-center gap-2">
            <StatusBadge status="processing" t={t} />
            {/* Spinner */}
            <svg className="animate-spin h-4 w-4 text-yellow-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        ) : (
          <StatusBadge status={isConnected ? 'Conectado' : 'Desconectado'} t={t} />
        )}

        {/* Texto informativo quando em processing */}
        {isProcessingState && (
          <span className="text-xs text-muted-foreground ml-2">Aguardando confirmação da Meta</span>
        )}
        {perdeuConexaoMeta && (
          <span className="text-xs text-orange-400 ml-1">Conexão com a Meta perdida</span>
        )}

        {/* Botões para WhatsApp */}
        {isWhatsapp && isConnected && (
          <button
            onClick={() => onDisconnect(channel.id)}
            className="bg-gradient-to-r from-red-500 to-red-700 hover:from-red-600 hover:to-red-800 text-white px-4 py-1 rounded-full text-xs font-semibold shadow transition ml-2"
          >
            {t('desconectar')}
          </button>
        )}
        {/* Botão Conectar - desabilitado quando em processing */}
        {(isWhatsapp || isWhatsappOficial) && !isConnected && !isProcessingState && (
          <button
            onClick={() => onConnect(channel.id)}
            className={`text-white px-4 py-1 rounded-full text-xs font-semibold shadow ml-2 bg-gradient-to-r ${
              perdeuConexaoMeta
                ? 'from-orange-500 to-orange-700 hover:from-orange-600 hover:to-orange-800'
                : 'from-blue-500 to-blue-700 hover:from-blue-600 hover:to-blue-800'
            }`}
            title={perdeuConexaoMeta ? 'A Meta não reconhece mais esta conexão. Reconecte para voltar a receber e enviar mensagens.' : undefined}
          >
            {perdeuConexaoMeta ? 'Reconectar' : t('conectar')}
          </button>
        )}
        {/* Botão para Telegram */}
        {channel.tipo === 'telegram' && !isConnected && (
          <button
            onClick={() => onConnect(channel.id)}
            className="bg-gradient-to-r from-blue-500 to-blue-700 hover:from-blue-600 hover:to-blue-800 text-white px-4 py-1 rounded-full text-xs font-semibold shadow ml-2"
          >
            {t('conectar')}
          </button>
        )}
        {channel.tipo === 'instagram' && !isConnected && (
          <button
            onClick={() => onConnect(channel.id)}
            className="bg-gradient-to-r from-blue-500 to-blue-700 hover:from-blue-600 hover:to-blue-800 text-white px-4 py-1 rounded-full text-xs font-semibold shadow ml-2"
          >
            {t('conectar')}
          </button>
        )}
        {channel.tipo === 'app_mobile' && !isConnected && (
          <button
            onClick={() => onConnect(channel.id)}
            className="bg-gradient-to-r from-blue-500 to-blue-700 hover:from-blue-600 hover:to-blue-800 text-white px-4 py-1 rounded-full text-xs font-semibold shadow ml-2"
          >
            {t('conectar')}
          </button>
        )}
      </div>
    </div>
  );
}

const ALL_CHANNEL_TYPES = [
  { tipo: 'whatsapp_oficial', label: 'WhatsApp Oficial' },
  { tipo: 'whatsapp', label: 'WhatsApp' },
  { tipo: 'whatsapp_session', label: 'WhatsApp QR code' },
  { tipo: 'telegram', label: 'Telegram' },
  { tipo: 'email', label: 'E-mail' },
  { tipo: 'instagram', label: 'Instagram' },
  { tipo: 'app_mobile', label: 'App Mobile' },
];

// Constantes para Meta Embedded Signup
const FACEBOOK_APP_ID = '713538217881661';
const META_EMBEDDED_SIGNUP_CONFIG_ID = '1888449245359692';

const INSTAGRAM_OAUTH_ERROR_MESSAGES = {
  access_denied: 'Autorização cancelada. Tente conectar novamente.',
  no_code: 'Código de autorização não recebido. Tente novamente.',
  token_exchange_error: 'Erro ao concluir login do Instagram. Tente novamente.',
  instagram_api_error: 'Instagram recusou a troca do token. Verifique App ID/Secret no superadmin.',
  tenant_finalize_error:
    'Login OK, mas falha ao salvar o canal no provedor. Verifique ADMIN_WEBHOOK_SECRET e redeploy do backend.',
  config_error:
    'Credenciais Instagram ou ADMIN_WEBHOOK_SECRET ausentes no superadmin (Portainer).',
};

function instagramOAuthErrorMessage(code, detail) {
  const base = INSTAGRAM_OAUTH_ERROR_MESSAGES[code] || 'Erro ao conectar Instagram. Tente novamente.';
  if (detail && import.meta.env.DEV) {
    return `${base} (${detail})`;
  }
  return base;
}

function canalErrorMessage(err, fallback) {
  const data = err?.response?.data;
  if (typeof data === 'string' && data.trim() && !data.trim().startsWith('<')) return data;
  const msg = data?.detail || data?.error;
  if (Array.isArray(msg)) return msg[0] || fallback;
  return (typeof msg === 'string' && msg) || fallback;
}

export default function Integrations({ provedorId, mode = 'full' }) {
  const [providerConfig, setProviderConfig] = useState(null);
  const [supportNotifyPhone, setSupportNotifyPhone] = useState('');
  const [savingSupportNotify, setSavingSupportNotify] = useState(false);
  const [supportNotifyMsg, setSupportNotifyMsg] = useState('');
  const [asaasToken, setAsaasToken] = useState('');
  const [asaasSandbox, setAsaasSandbox] = useState(true);
  const [showAsaasToken, setShowAsaasToken] = useState(false);
  const [savingAsaas, setSavingAsaas] = useState(false);

  useEffect(() => {
    const fetchProviderConfig = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (token) {
          const response = await axios.get('/api/provider/config/', {
            headers: { Authorization: `Token ${token}` }
          });
          setProviderConfig(response.data);
          setSupportNotifyPhone(response.data?.support_transfer_notify_phone || '');
          setAsaasToken(response.data?.asaas_access_token || '');
          setAsaasSandbox(response.data?.asaas_sandbox !== false);
        }
      } catch (error) {
      }
    };
    fetchProviderConfig();
  }, []);

  const saveSupportNotifyPhone = async () => {
    setSavingSupportNotify(true);
    setSupportNotifyMsg('');
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.patch(
        '/api/provider/config/',
        { support_transfer_notify_phone: supportNotifyPhone },
        { headers: { Authorization: `Token ${token}` } }
      );
      setProviderConfig((prev) => ({ ...(prev || {}), ...response.data }));
      setSupportNotifyPhone(response.data?.support_transfer_notify_phone || '');
      setSupportNotifyMsg('Número salvo. A IA notificará este WhatsApp em cada transferência.');
    } catch (err) {
      setSupportNotifyMsg(err.response?.data?.error || 'Erro ao salvar número.');
    } finally {
      setSavingSupportNotify(false);
    }
  };

  const saveAsaasConfig = async (e) => {
    e?.preventDefault?.();
    setSavingAsaas(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.patch(
        '/api/provider/config/',
        {
          asaas_access_token: asaasToken,
          asaas_sandbox: asaasSandbox,
        },
        { headers: { Authorization: `Token ${token}` } }
      );
      setProviderConfig((prev) => ({ ...(prev || {}), ...response.data }));
      setAsaasToken(response.data?.asaas_access_token || '');
      setAsaasSandbox(response.data?.asaas_sandbox !== false);
      toast.success('Configurações do Asaas salvas com sucesso!');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Erro ao salvar Asaas!');
    } finally {
      setSavingAsaas(false);
    }
  };

  // Função helper para buscar canais com provedor_id quando necessário
  const fetchCanais = async (token) => {
    const params = {};
    if (provedorId) {
      params.provedor_id = provedorId;
    }
    return axios.get('/api/canais/', {
      headers: { Authorization: `Token ${token}` },
      params
    });
  };

  const withProviderContext = useCallback((data = {}) => {
    if (!provedorId) return data;
    return {
      ...data,
      provedor_id: Number(provedorId),
    };
  }, [provedorId]);

  const { t } = useLanguage();
  const navigate = useNavigate();

  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Trocar o estado inicial e uso dos campos do SGP para os novos nomes:
  const [sgp, setSgp] = useState({
    erp_system: 'sgp',
    sgp_url: '',
    sgp_token: '',
    sgp_app: '',
    sgp_viabilidade_gateway: '',
    sgp_viabilidade_raio: '',
    sgp_viabilidade_ativa: true,
  });
  const [acs, setAcs] = useState({
    acs_url: '',
    acs_token: '',
  });
  const [savingAcs, setSavingAcs] = useState(false);
  const ERP_SYSTEM_OPTIONS = [
    { value: 'sgp', label: 'SGP' },
    { value: 'mk_auth', label: 'MK AUTH' },
    { value: 'ixc', label: 'IXC Soft' },
    { value: 'beesweb', label: 'Beesweb' },
  ];
  const AI_PROVIDER_OPTIONS = {
    openai: {
      label: 'OpenAI',
      models: [
        { value: 'gpt-4o-mini', label: 'gpt-4o-mini (recomendado)' },
        { value: 'gpt-4o', label: 'gpt-4o' },
        { value: 'gpt-4.1-mini', label: 'gpt-4.1-mini' },
        { value: 'gpt-4.1', label: 'gpt-4.1' },
      ],
      defaultModel: 'gpt-4o-mini',
      keyHint: 'sk-...',
      docsUrl: 'https://platform.openai.com/api-keys',
      docsLabel: 'platform.openai.com/api-keys',
    },
    gemini: {
      label: 'Gemini (Google)',
      models: [
        { value: 'gemini-2.0-flash', label: 'gemini-2.0-flash (recomendado)' },
        { value: 'gemini-2.5-flash', label: 'gemini-2.5-flash' },
        { value: 'gemini-2.5-pro', label: 'gemini-2.5-pro' },
      ],
      defaultModel: 'gemini-2.0-flash',
      keyHint: 'AIza... ou AQ....',
      docsUrl: 'https://aistudio.google.com/apikey',
      docsLabel: 'aistudio.google.com/apikey',
    },
    deepseek: {
      label: 'DeepSeek',
      models: [
        { value: 'deepseek-chat', label: 'deepseek-chat (recomendado)' },
        { value: 'deepseek-reasoner', label: 'deepseek-reasoner' },
      ],
      defaultModel: 'deepseek-chat',
      keyHint: 'sk-...',
      docsUrl: 'https://platform.deepseek.com/api_keys',
      docsLabel: 'platform.deepseek.com/api_keys',
    },
  };
  const [openaiConfig, setOpenaiConfig] = useState({
    ai_provider: 'openai',
    openai_api_key: '',
    openai_model: 'gpt-4o-mini',
    openai_configured: false,
  });
  const [openaiKeyDirty, setOpenaiKeyDirty] = useState(false);
  const [savingOpenai, setSavingOpenai] = useState(false);
  const [webhookDispatchToken, setWebhookDispatchToken] = useState('');
  const [generatingWebhookToken, setGeneratingWebhookToken] = useState(false);
  const [webhookTokenCopied, setWebhookTokenCopied] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [selectedChannelForTemplates, setSelectedChannelForTemplates] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [showCreateTemplate, setShowCreateTemplate] = useState(false);
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [templateForm, setTemplateForm] = useState({
    name: '',
    category: 'UTILITY',
    language: 'pt_BR',
    variable_type: 'number', // 'nome' ou 'number'
    body: { text: '', has_variables: false },
    header: { type: 'none', text: '', media_id: '', media_link: '', has_variables: false },
    footer: { text: '', has_variables: false },
    buttons: []
  });
  // Amostras de variáveis: { [varNumber]: { type: 'nome'|'number', example: string } }
  const [variableSamples, setVariableSamples] = useState({});
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [availableTypes, setAvailableTypes] = useState([]);
  const [adding, setAdding] = useState(false);
  const [selectedType, setSelectedType] = useState(null);
  const [instanceName, setInstanceName] = useState('');
  const [qrCode, setQrCode] = useState('');
  const [qrLoading, setQrLoading] = useState(false);
  const [formData, setFormData] = useState({ nome: '', email: '', url: '', app_token: '', app_default_team_id: '' });
  const [appMobileTeams, setAppMobileTeams] = useState([]);
  const [connectingId, setConnectingId] = useState(null);
  const [qrCard, setQrCard] = useState('');
  const [qrCardLoading, setQrCardLoading] = useState(false);
  const [showAddChannelSuccess, setShowAddChannelSuccess] = useState(false);
  const pushToast = useCallback((payload) => {
    if (payload?.show === false) return;
    const message = typeof payload === 'string' ? payload : payload?.message;
    if (!message) return;
    const type = payload?.type || 'success';
    if (type === 'error') toast.error(message);
    else if (type === 'deleted') toast.deleted(message);
    else if (type === 'info' || type === 'warning') toast.info(message);
    else toast.success(message);
  }, []);

  // Estados para edição de nome do canal
  const [isEditingName, setIsEditingName] = useState(false);
  const [channelToEdit, setChannelToEdit] = useState(null);
  const [newName, setNewName] = useState('');
  const [savingName, setSavingName] = useState(false);
  // Adicionar estados:
  const [showPairingMenu, setShowPairingMenu] = useState(false);
  const [pairingMethod, setPairingMethod] = useState(''); // 'qrcode' ou 'paircode'
  const [pendingConnectId, setPendingConnectId] = useState(null);
  const [pairingPhone, setPairingPhone] = useState('');
  const [showPhoneInput, setShowPhoneInput] = useState(false);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairingResult, setPairingResult] = useState(null);
  // Estados para verificação de código Telegram
  const [showTelegramCodeModal, setShowTelegramCodeModal] = useState(false);
  const [telegramCode, setTelegramCode] = useState('');
  const [telegramChannelData, setTelegramChannelData] = useState(null);
  const [verifyingCode, setVerifyingCode] = useState(false);
  // Estado para rastrear canais WhatsApp Oficial em processamento
  const [processingChannels, setProcessingChannels] = useState(new Set());
  const [deletingChannelId, setDeletingChannelId] = useState(null);
  const [showPairingModal, setShowPairingModal] = useState(false);
  const [selectedMethod, setSelectedMethod] = useState('');
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [statusData, setStatusData] = useState(null);
  const [whatsappSessionStatus, setWhatsappSessionStatus] = useState({});
  const [statusPolling, setStatusPolling] = useState({});
  const [provedor, setProvedor] = useState(null);
  const connectingIdRef = useRef(null);
  const voiceCallsPollRef = useRef(null);
  const [voiceCallsBusyId, setVoiceCallsBusyId] = useState(null);
  const [voiceCallsModal, setVoiceCallsModal] = useState(null);

  // Listener dedicado abaixo cobre o fluxo FINISH da Meta.
  // O hook adicional foi removido para evitar conflito/duplicidade de hooks em runtime.

  // Função para parar polling - deve ser declarada antes dos useEffect que a usam
  const stopStatusPolling = useCallback((canalId) => {
    if (statusPolling[canalId]) {
      clearInterval(statusPolling[canalId]);
      setStatusPolling(prev => {
        const newPolling = { ...prev };
        delete newPolling[canalId];
        return newPolling;
      });
    }
  }, [statusPolling]);

  // Função para iniciar polling - também deve ser declarada antes dos useEffect
  const startStatusPolling = useCallback((canalId) => {
    if (statusPolling[canalId]) return; // Já está monitorando
    let lastStatus = null;
    const pollStatus = async () => {
      try {
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        const response = await axios.post(buildApiPath(`/api/whatsapp/session/status/${canalId}/`), {}, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (response.data.success) {
          const status = response.data;
          // Atualizar foto de perfil nos canais quando disponível
          const profilePicUrl = status.instance?.profilePicUrl || status.profilePicUrl;
          const isConnected = status.status === 'connected' && status.loggedIn;
          const isDisconnected = status.status === 'disconnected' || !status.loggedIn;

          setChannels(prevChannels => prevChannels.map(c => {
            if (c.id === canalId && c.tipo === 'whatsapp_session') {
              // CORREÇÃO: Determinar foto final baseado APENAS no status de conexão
              // Se desconectado: SEMPRE null (GIF será mostrado)
              // Se conectado: usar nova foto se disponível, senão preservar existente
              let finalProfilePic = null;
              if (isDisconnected) {
                // Desconectou, SEMPRE limpar foto (GIF será mostrado)
                finalProfilePic = null;
              } else if (isConnected) {
                // Conectado: priorizar nova foto, senão preservar existente
                finalProfilePic = profilePicUrl ||
                  c.profile_pic ||
                  c.sessionStatus?.instance?.profilePicUrl ||
                  c.sessionStatus?.profilePicUrl ||
                  c.dados_extras?.profilePicUrl ||
                  null;
              } else {
                // Status intermediário, preservar foto existente
                finalProfilePic = c.profile_pic ||
                  c.sessionStatus?.instance?.profilePicUrl ||
                  c.sessionStatus?.profilePicUrl ||
                  c.dados_extras?.profilePicUrl ||
                  null;
              }

              return {
                ...c,
                profile_pic: finalProfilePic,
                sessionStatus: {
                  ...c.sessionStatus,
                  ...status,
                  instance: {
                    ...c.sessionStatus?.instance,
                    ...status.instance,
                    profilePicUrl: finalProfilePic || c.sessionStatus?.instance?.profilePicUrl
                  },
                  profilePicUrl: finalProfilePic || c.sessionStatus?.profilePicUrl
                }
              };
            }
            return c;
          }));

          setWhatsappSessionStatus(prev => ({
            ...prev,
            [canalId]: status
          }));
          // Se conectou, salva status
          if (status.status === 'connected' && status.loggedIn) {
            lastStatus = 'connected';
          }
          // Se desconectou após estar conectado, exibe alerta
          if (lastStatus === 'connected' && (status.status === 'disconnected' || !status.loggedIn)) {
            // setWhatsappDisconnected(true); // Removido
            // setTimeout(() => setWhatsappDisconnected(false), 8000); // Removido
            lastStatus = 'disconnected';
          }
        }
      } catch (error) {
        // Se der 401, parar polling para evitar flood
        if (error?.response?.status === 401) {
          stopStatusPolling(canalId);
        }
      }
    };
    // Primeira verificação
    pollStatus();
    // Configurar polling a cada 30 segundos
    const interval = setInterval(pollStatus, 30000);
    setStatusPolling(prev => ({
      ...prev,
      [canalId]: interval
    }));
  }, [statusPolling, stopStatusPolling]);

  const verificarConexoesOficiais = useCallback(async (lista) => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    const oficiais = (Array.isArray(lista) ? lista : []).filter(
      (c) => c.tipo === 'whatsapp_oficial' && c.phone_number_id
    );
    if (!token || !oficiais.length) return;
    await Promise.all(
      oficiais.map(async (c) => {
        try {
          const vr = await axios.post(
            `/api/canais/${c.id}/verificar-conexao/`,
            {},
            { headers: { Authorization: `Token ${token}` } }
          );
          const updated = vr.data?.canal;
          if (updated) {
            setChannels((prev) =>
              prev.map((ch) => (ch.id === updated.id ? { ...ch, ...updated } : ch))
            );
          }
        } catch {
          /* verificação best-effort */
        }
      })
    );
  }, []);

  const channelsRef = useRef([]);
  useEffect(() => {
    channelsRef.current = channels;
  }, [channels]);

  useEffect(() => {
    const id = setInterval(() => verificarConexoesOficiais(channelsRef.current), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [verificarConexoesOficiais]);

  useEffect(() => {
    setLoading(true);
    setError('');
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    // Se não há token, mostrar erro
    if (!token) {
      setError(t('usuario_nao_autenticado'));
      setLoading(false);
      return;
    }

    fetchCanais(token)
      .then(async (res) => {
        const list = res.data.results || res.data;
        setChannels(list);
        setLoading(false);
        await verificarConexoesOficiais(list);
      })
      .catch((error) => {
        setError(t('erro_carregar_canais'));
        setLoading(false);
      });

    if (provedorId) {
      axios.get(`/api/provedores/${provedorId}/`, {
        headers: { Authorization: `Token ${token}` }
      })
        .then(res => {
          // Armazenar provedor completo
          setProvedor(res.data);

          setSgp(prev => {
            if (!prev.sgp_url && !prev.sgp_token && !prev.sgp_app) {
              return {
                erp_system: res.data.erp_system || 'sgp',
                sgp_url: res.data.sgp_url || '',
                sgp_token: res.data.sgp_token || '',
                sgp_app: res.data.sgp_app || '',
                sgp_viabilidade_gateway: res.data.sgp_viabilidade_gateway || '',
                sgp_viabilidade_raio: res.data.sgp_viabilidade_raio || '',
                sgp_viabilidade_ativa: res.data.sgp_viabilidade_ativa ?? true,
              };
            }
            return {
              ...prev,
              erp_system: res.data.erp_system || prev.erp_system || 'sgp',
              sgp_viabilidade_gateway:
                res.data.sgp_viabilidade_gateway ?? prev.sgp_viabilidade_gateway ?? '',
              sgp_viabilidade_raio:
                res.data.sgp_viabilidade_raio ?? prev.sgp_viabilidade_raio ?? '',
              sgp_viabilidade_ativa:
                res.data.sgp_viabilidade_ativa ?? prev.sgp_viabilidade_ativa ?? true,
            };
          });
          setOpenaiConfig({
            ai_provider: res.data.ai_provider || 'openai',
            openai_api_key: res.data.openai_api_key || '',
            openai_model: res.data.openai_model || 'gpt-4o-mini',
            openai_configured: Boolean(res.data.openai_configured),
          });
          setAcs({
            acs_url: res.data.acs_url || '',
            acs_token: res.data.acs_token || '',
          });
          setOpenaiKeyDirty(false);
          if (res.data.webhook_dispatch_token) {
            setWebhookDispatchToken(res.data.webhook_dispatch_token);
          }
        })
        .catch(() => { });
    }
  }, [provedorId]);

  // Detectar retorno do OAuth e colocar canal em estado "processing"
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const oauthError = urlParams.get('oauth_error');
    const code = urlParams.get('code');
    const state = urlParams.get('state');

    // Se há code na URL, significa que o usuário retornou do OAuth
    // O callback OAuth NÃO significa sucesso - apenas retorno
    // O card deve entrar em estado "processing" e aguardar o evento FINISH
    if (code && state) {
      // Extrair provider_id do state
      let providerIdFromState = null;
      if (state && state.startsWith('provider_')) {
        try {
          providerIdFromState = parseInt(state.replace('provider_', ''));
        } catch (e) {
        }
      }

      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (token) {
        // Recarregar canais para encontrar o canal WhatsApp Oficial
        fetchCanais(token).then(res => {
          const channelsList = Array.isArray(res.data) ? res.data : res.data.results || [];
          setChannels(channelsList);

          // Encontrar canal WhatsApp Oficial do provedor
          const whatsappOficial = channelsList.find(c =>
            c.tipo === 'whatsapp_oficial' &&
            (!providerIdFromState || c.provedor?.id === providerIdFromState)
          );

          if (whatsappOficial) {
            // Colocar canal em estado "processing"
            setProcessingChannels(prev => new Set(prev).add(whatsappOficial.id));

            pushToast({
              show: true,
              message: 'Aguardando confirmação da Meta...',
              type: 'info'
            });
            setTimeout(() => pushToast({ show: false, message: '', type: 'info' }), 5000);
          }
        });
      }

      // NÃO limpar code e state imediatamente - manter na URL temporariamente
      // O listener do postMessage pode precisar deles
      // Limpar apenas após o evento FINISH ser processado
      // window.history.replaceState({}, '', window.location.pathname);
      return;
    }

    // Tratar erros do OAuth
    if (oauthError) {
      const errorMessages = {
        'token_exchange_error': 'Erro ao trocar código de autorização. Tente novamente.',
        'waba_fetch_error': 'Erro ao buscar conta WhatsApp Business. Verifique as permissões.',
        'phone_fetch_error': 'Erro ao buscar número de telefone. Tente novamente.',
        'no_phone_number_id': 'Número de telefone não encontrado. Verifique a configuração.',
        'permission_error': 'Permissões insuficientes. Conceda todas as permissões necessárias.',
        'no_code': 'Código de autorização não recebido. Tente novamente.',
        'backend_url_not_configured': 'Erro de configuração do servidor. Contate o suporte.',
        'provider_not_found': 'Provedor não encontrado. Tente novamente.'
      };

      pushToast({
        show: true,
        message: errorMessages[oauthError] || 'Erro ao conectar WhatsApp Oficial. Tente novamente.',
        type: 'error'
      });
      setTimeout(() => pushToast({ show: false, message: '', type: 'error' }), 5000);

      // Limpar parâmetro da URL
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [provedorId, fetchCanais]);

  // Popup OAuth Instagram — apenas na tela Configurar Canais (mode channels)
  useEffect(() => {
    if (mode !== 'channels') return undefined;

    const handleInstagramOAuthMessage = (event) => {
      const payload = event.data;
      if (!payload || typeof payload !== 'object') return;

      if (payload.type === 'INSTAGRAM_OAUTH_SUCCESS') {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (token) {
          fetchCanais(token).then(res => {
            setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
          });
        }
        pushToast({
          show: true,
          message: 'Instagram conectado com sucesso!',
          type: 'success',
        });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 5000);
        return;
      }

      if (payload.type === 'INSTAGRAM_OAUTH_ERROR') {
        pushToast({
          show: true,
          message: instagramOAuthErrorMessage(payload.error, payload.error_detail),
          type: 'error',
        });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 8000);
      }
    };

    window.addEventListener('message', handleInstagramOAuthMessage);
    return () => window.removeEventListener('message', handleInstagramOAuthMessage);
  }, [fetchCanais, mode]);

  useEffect(() => {
    if (!showModal || selectedType !== 'app_mobile') return undefined;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return undefined;
    let cancelled = false;
    axios
      .get('/api/teams/', { headers: { Authorization: `Token ${token}` } })
      .then((res) => {
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data : res.data?.results || [];
        setAppMobileTeams(list);
      })
      .catch(() => {
        if (!cancelled) setAppMobileTeams([]);
      });
    return () => {
      cancelled = true;
    };
  }, [showModal, selectedType]);

  // Retorno do OAuth Instagram Business Login (fallback redirect na mesma aba)
  useEffect(() => {
    if (mode !== 'channels') return undefined;

    const urlParams = new URLSearchParams(window.location.search);
    const igSuccess = urlParams.get('instagram_oauth_success');
    const igError = urlParams.get('instagram_oauth_error');

    if (!igSuccess && !igError) return;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;

    if (igSuccess === '1') {
      fetchCanais(token).then(res => {
        setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
        pushToast({
          show: true,
          message: 'Instagram conectado com sucesso!',
          type: 'success',
        });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 5000);
      });
    } else if (igError) {
      pushToast({
        show: true,
        message: instagramOAuthErrorMessage(igError),
        type: 'error',
      });
      setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 8000);
    }

    window.history.replaceState({}, '', window.location.pathname);
  }, [fetchCanais, mode]);

  // Redireciona parâmetros Instagram OAuth que caírem em /integracoes (callback antigo)
  useEffect(() => {
    if (mode !== 'settings') return undefined;

    const params = new URLSearchParams(window.location.search);
    if (!params.get('instagram_oauth_success') && !params.get('instagram_oauth_error')) {
      return undefined;
    }

    const pid = provedorId || '1';
    navigate(`/app/accounts/${pid}/canais/configurar?${params.toString()}`, { replace: true });
    return undefined;
  }, [mode, navigate, provedorId]);

  // Listener para evento FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING do Meta
  // Conforme documentação: https://developers.facebook.com/docs/whatsapp/embedded-signup/custom-flows/onboarding-business-app-users
  // O Meta envia este evento via postMessage quando o usuário clica em "Concluir"
  useEffect(() => {
    const handleMessage = (event) => {
      // IMPORTANTE: Validar origem do evento por segurança
      // O evento deve vir de um domínio do Facebook/Meta
      const allowedOrigins = [
        'https://www.facebook.com',
        'https://facebook.com',
        'https://business.facebook.com',
        'https://meta.com'
      ];

      // Em desenvolvimento, também aceitar localhost (para testes)
      const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

      if (!isLocalhost && !allowedOrigins.some(origin => event.origin.startsWith(origin))) {
        // Ignorar eventos de origens não confiáveis
        return;
      }

      // Verificar se é o evento de conclusão do onboarding
      // IMPORTANTE: Verificar tanto 'event' quanto 'evento' (português) para compatibilidade
      const eventType = event.data?.type || event.data?.tipo;
      const eventName = event.data?.event || event.data?.evento;
      const eventData = event.data?.data || event.data?.dados;

      if (eventType === 'WA_EMBEDDED_SIGNUP' && eventName === 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING') {

        const wabaId = eventData?.waba_id;

        if (!wabaId) {
          pushToast({
            show: true,
            message: 'Erro: WABA ID não encontrado no evento',
            type: 'error'
          });
          setTimeout(() => pushToast({ show: false, message: '', type: 'error' }), 5000);
          return;
        }

        // Enviar waba_id para o backend
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) {
          return;
        }

        // Obter provider_id do contexto atual
        const currentProviderId = provedorId || 1;

        // Encontrar o canal WhatsApp Oficial específico e colocá-lo em processing
        // (caso ainda não esteja)
        if (token) {
          fetchCanais(token).then(res => {
            const channelsList = Array.isArray(res.data) ? res.data : res.data.results || [];
            
            // Tentar encontrar pelo waba_id se já estiver vinculado, ou usar o canal que originou o evento
            // Mas aqui no listener global, o mais seguro é buscar pelo waba_id recebido
            const whatsappOficial = channelsList.find(c => c.tipo === 'whatsapp_oficial' && (c.waba_id === wabaId || !c.waba_id));
            
            if (whatsappOficial) {
              setProcessingChannels(prev => new Set(prev).add(whatsappOficial.id));
            }
          });
        }

        pushToast({
          show: true,
          message: 'Finalizando conexão...',
          type: 'info'
        });

        // Chamar endpoint do backend para processar o finish
        axios.post('/api/canais/whatsapp_embedded_signup_finish/', {
          waba_id: wabaId,
          phone_number_id: eventData?.phone_number_id,
          business_id: eventData?.business_id,
          provider_id: currentProviderId
        }, {
          headers: { Authorization: `Token ${token}` }
        }).then(response => {
          if (response.data.success) {

            // Remover do estado "processing" e recarregar canais
            const canalId = response.data.canal?.id;
            if (canalId) {
              setProcessingChannels(prev => {
                const newSet = new Set(prev);
                newSet.delete(canalId);
                return newSet;
              });
            }

            // Recarregar canais para atualizar status
            fetchCanais(token).then(res => {
              const channelsList = Array.isArray(res.data) ? res.data : res.data.results || [];
              setChannels(channelsList);

              // Limpar parâmetros da URL após sucesso
              window.history.replaceState({}, '', window.location.pathname);

              pushToast({
                show: true,
                message: 'WhatsApp Oficial conectado com sucesso! Sincronizações iniciadas.',
                type: 'success'
              });
              setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 5000);
            }).catch(error => {
            });
          } else {
            throw new Error(response.data.error || 'Erro ao processar finish');
          }
        }).catch(error => {
          const errorMessage = error.response?.data?.error || error.message || 'Erro ao finalizar conexão';

          // Remover do estado "processing" em caso de erro
          const whatsappOficial = channels.find(c => c.tipo === 'whatsapp_oficial');
          if (whatsappOficial) {
            setProcessingChannels(prev => {
              const newSet = new Set(prev);
              newSet.delete(whatsappOficial.id);
              return newSet;
            });
          }

          pushToast({
            show: true,
            message: `Erro: ${errorMessage}`,
            type: 'error'
          });
          setTimeout(() => pushToast({ show: false, message: '', type: 'error' }), 5000);
        });
      }
    };

    // Adicionar listener
    window.addEventListener('message', handleMessage);

    // Cleanup: remover listener quando componente desmontar
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [fetchCanais, provedorId, channels, setProcessingChannels, setChannels, pushToast]);

  // Polling para verificar status do WhatsApp Oficial após OAuth
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const oauthSuccess = urlParams.get('oauth_success');

    if (oauthSuccess === '1') {
      // Iniciar polling para verificar se o canal foi criado
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      let attempts = 0;
      const maxAttempts = 30; // 30 tentativas = 1 minuto (2s cada)

      const checkChannel = setInterval(async () => {
        attempts++;

        try {
          const res = await fetchCanais(token);
          const channelsList = Array.isArray(res.data) ? res.data : res.data.results || [];

          // Buscar canal WhatsApp Oficial
          const whatsappOficial = channelsList.find(c => c.tipo === 'whatsapp_oficial');

          if (whatsappOficial) {
            // Canal encontrado - verificar status
            const isConnected = whatsappOficial.status === 'connected' && whatsappOficial.ativo;

            if (isConnected) {
              // Canal conectado - atualizar lista e parar polling
              setChannels(channelsList);
              clearInterval(checkChannel);

              pushToast({
                show: true,
                message: 'WhatsApp Oficial conectado com sucesso!',
                type: 'success'
              });
              setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 5000);
            } else if (attempts >= maxAttempts) {
              // Timeout - parar polling
              clearInterval(checkChannel);
              pushToast({
                show: true,
                message: 'Canal criado, mas aguardando conexão. Verifique os logs do servidor.',
                type: 'warning'
              });
              setTimeout(() => pushToast({ show: false, message: '', type: 'warning' }), 5000);
            } else {
              // Canal existe mas não está conectado - continuar verificando
              setChannels(channelsList);
            }
          } else if (attempts >= maxAttempts) {
            // Timeout - canal não foi criado
            clearInterval(checkChannel);
            pushToast({
              show: true,
              message: 'Canal não foi criado. Verifique os logs do servidor ou tente novamente.',
              type: 'error'
            });
            setTimeout(() => pushToast({ show: false, message: '', type: 'error' }), 5000);
          }
        } catch (error) {
          if (attempts >= maxAttempts) {
            clearInterval(checkChannel);
          }
        }
      }, 2000); // Verificar a cada 2 segundos

      return () => clearInterval(checkChannel);
    }
  }, [provedorId]);

  useEffect(() => {
    if (!provedorId) return;

    let ws = null;
    let cancelled = false;

    (async () => {
      try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      const wsUrl = await buildAuthenticatedWebSocketUrl(buildPainelWebSocketEndpoint(provedorId), { token });
      if (cancelled) return;
      ws = new window.WebSocket(wsUrl);

      ws.onopen = () => {

      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'channel_status_update') {
            const canalId = data.canal_id;
            if (!canalId) return;
            setChannels((prev) =>
              prev.map((c) => {
                if (c.id !== canalId) return c;
                return {
                  ...c,
                  status: data.status_novo || c.status,
                  state: data.status_novo || c.state,
                  ativo: typeof data.ativo === 'boolean' ? data.ativo : c.ativo,
                };
              })
            );
            if (data.status_novo && data.status_novo !== 'connected') {
              pushToast({
                show: true,
                message: 'WhatsApp Oficial desconectado da Meta. Clique em Reconectar para voltar a funcionar sem perder o ID do canal.',
                type: 'warning',
              });
              setTimeout(() => pushToast({ show: false, message: '', type: 'info' }), 6000);
            }
            return;
          }
          if (data.type === 'whatsapp_session_status') {
            const canalId = data.canal_id;
            const status = data.status;
            const connected = data.connected;
            const loggedIn = data.loggedIn;

            // Considerar conectado se: status é 'connected' OU (connected=true E loggedIn=true)
            const isConnected = status === 'connected' || status === 'open' || (connected === true && loggedIn === true);

            // Atualizar estado do canal
            setChannels(prevChannels => prevChannels.map(c => {
              if (canalId && c.id === canalId) {
                // CORREÇÃO: Verificar se está desconectado ou conectado
                const isDisconnected = (status === 'disconnected' || status === 'Disconectado') &&
                  (connected === false && loggedIn === false);
                const isNowConnected = status === 'connected' || status === 'open' || (connected === true && loggedIn === true);

                // Obter nova foto se disponível
                const newProfilePic = data.instance?.profilePicUrl || data.profilePicUrl;

                // CORREÇÃO: Determinar foto final baseado APENAS no status de conexão
                // Se desconectado: SEMPRE null (GIF será mostrado)
                // Se conectado: usar nova foto se disponível, senão preservar existente
                let finalProfilePic = null;
                if (isDisconnected) {
                  // Desconectou, SEMPRE limpar foto (GIF será mostrado)
                  finalProfilePic = null;
                } else if (isNowConnected) {
                  // Conectado: priorizar nova foto, senão preservar existente
                  finalProfilePic = newProfilePic ||
                    c.profile_pic ||
                    c.sessionStatus?.instance?.profilePicUrl ||
                    c.sessionStatus?.profilePicUrl ||
                    c.dados_extras?.profilePicUrl ||
                    null;
                } else {
                  // Status intermediário, preservar foto existente
                  finalProfilePic = c.profile_pic ||
                    c.sessionStatus?.instance?.profilePicUrl ||
                    c.sessionStatus?.profilePicUrl ||
                    c.dados_extras?.profilePicUrl ||
                    null;
                }

                return {
                  ...c,
                  state: status,
                  profile_pic: finalProfilePic,
                  sessionStatus: {
                    ...c.sessionStatus,
                    status: status,
                    instance: {
                      ...c.sessionStatus?.instance,
                      ...data.instance,
                      profilePicUrl: finalProfilePic || c.sessionStatus?.instance?.profilePicUrl
                    },
                    connected: connected,
                    loggedIn: loggedIn,
                    profilePicUrl: finalProfilePic || c.sessionStatus?.profilePicUrl
                  }
                };
              }
              return c;
            }));

            // Se o canal que está conectando recebeu status de conectado, fechar modal
            if (canalId && connectingIdRef.current === canalId && isConnected) {
              setConnectingId(null);
              setQrCard('');
              setQrCardLoading(false);
              setShowAddChannelSuccess(true);
              setTimeout(() => setShowAddChannelSuccess(false), 3000);
            }
          }
        } catch (e) {
        }
      };

      ws.onclose = (event) => {

      };

      ws.onerror = (error) => {
        // CORREÇÃO DE SEGURANÇA: Não expor token em logs
        // O erro pode conter a URL com token, mas não vamos logá-la
      };

    } catch (error) {
      // CORREÇÃO DE SEGURANÇA: Não expor detalhes do erro que podem conter token
      // Silenciar erro para não expor informações sensíveis
    }
    })();

    return () => {
      cancelled = true;
      if (ws && ws.readyState === WebSocket.OPEN) {

        ws.close(1000, 'Component unmounting');
      }
    };
  }, [provedorId]);

  // Limpar polling quando componente for desmontado
  useEffect(() => {
    return () => {
      Object.keys(statusPolling).forEach(canalId => {
        stopStatusPolling(canalId);
      });
    };
  }, [statusPolling, stopStatusPolling]);

  // Atualizar ref quando connectingId mudar
  useEffect(() => {
    connectingIdRef.current = connectingId;
  }, [connectingId]);

  // useEffect para fechar o QR Code automaticamente quando o canal conectar
  useEffect(() => {
    if (connectingId) {
      const canal = channels.find(c => c.id === connectingId);
      if (!canal) return;

      // Verificar se o canal está conectado
      const channelState = canal?.state || canal?.status;
      const sessionStatus = canal?.sessionStatus;
      const isConnected =
        channelState === 'open' ||
        channelState === 'connected' ||
        channelState === 'Conectado' ||
        (sessionStatus?.connected === true && sessionStatus?.loggedIn === true);

      if (isConnected) {
        // Fechar modal e mostrar sucesso
        setConnectingId(null);
        setQrCard('');
        setQrCardLoading(false);
        setShowAddChannelSuccess(true);
        setTimeout(() => setShowAddChannelSuccess(false), 3000);
      }
    }
  }, [channels, connectingId]);

  // useEffect para fechar o modal de código de pareamento automaticamente quando o canal conectar
  useEffect(() => {
    if (showPhoneInput && pendingConnectId) {
      const canal = channels.find(c => c.id === pendingConnectId);
      if (!canal) return;

      // Verificar se o canal está conectado
      const channelState = canal?.state || canal?.status;
      const sessionStatus = canal?.sessionStatus;
      const isConnected =
        channelState === 'open' ||
        channelState === 'connected' ||
        channelState === 'Conectado' ||
        (sessionStatus?.connected === true && sessionStatus?.loggedIn === true);

      if (isConnected) {
        // Fechar modal de código de pareamento e mostrar sucesso
        setShowPhoneInput(false);
        setPendingConnectId(null);
        setPairingPhone('');
        setPairingResult(null);
        setShowAddChannelSuccess(true);
        setTimeout(() => setShowAddChannelSuccess(false), 3000);
      }
    }
  }, [channels, showPhoneInput, pendingConnectId]);

  // useEffect para iniciar polling automático para canais de sessão WhatsApp (Uazapi)
  // whatsapp_session é o valor do banco de dados para sessões Uazapi
  useEffect(() => {
    channels.forEach(channel => {
      if (channel.tipo === 'whatsapp_session' && channel.dados_extras?.instance_id) {
        // Iniciar polling apenas se não estiver já ativo
        if (!statusPolling[channel.id]) {
          startStatusPolling(channel.id);
        }
      }
    });
  }, [channels, statusPolling, startStatusPolling]);

  // Polling mais agressivo quando modal está aberto para detectar conexão rapidamente
  useEffect(() => {
    let interval;
    if (connectingId) {
      const canal = channels.find(c => c.id === connectingId);

      // Se for sessão WhatsApp (Uazapi), verificar status diretamente via API
      // whatsapp_session é o valor do banco de dados para sessões Uazapi
      if (canal && canal.tipo === 'whatsapp_session' && canal.dados_extras?.instance_id) {
        interval = setInterval(async () => {
          try {
            // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
            const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
            const response = await axios.post(buildApiPath(`/api/whatsapp/session/status/${canal.id}/`), {}, {
              headers: { Authorization: `Bearer ${token}` }
            });

            if (response.data.success) {
              const status = response.data.status;
              const connected = response.data.connected;
              const loggedIn = response.data.loggedIn;

              // Considerar conectado se: status é 'connected' OU (connected=true E loggedIn=true)
              const isConnected = status === 'connected' || status === 'open' || (connected === true && loggedIn === true);

              if (isConnected) {
                // Atualizar canais e fechar modal
                const channelsRes = await fetchCanais(token);
                setChannels(Array.isArray(channelsRes.data) ? channelsRes.data : channelsRes.data.results || []);

                // Fechar modal
                setConnectingId(null);
                setQrCard('');
                setQrCardLoading(false);
                setShowAddChannelSuccess(true);
                setTimeout(() => setShowAddChannelSuccess(false), 3000);
              }
            }
          } catch (error) {
          }
        }, 2000); // Verificar a cada 2 segundos
      } else {
        // Para WhatsApp normal (Evolution), usar polling de canais
        interval = setInterval(() => {
          // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
          const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
          fetchCanais(token).then(res => {
            setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
          });
        }, 2000);
      }
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [connectingId, channels]);

  const redirectToInstagramOAuth = async (channelId) => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      pushToast({ show: true, message: 'Token não encontrado. Faça login novamente.', type: 'error' });
      return;
    }

    const response = await axios.post(
      `/api/canais/${channelId}/connect-instagram/`,
      { frontend_origin: window.location.origin },
      { headers: { Authorization: `Token ${token}` } }
    );

    if (response.data?.success && response.data.oauth_url) {
      const popup = window.open(
        response.data.oauth_url,
        'instagram_oauth',
        'width=520,height=720,scrollbars=yes'
      );
      if (!popup) {
        pushToast({
          show: true,
          message: 'Permita pop-ups para conectar o Instagram ou tente novamente.',
          type: 'warning',
        });
      }
      return;
    }

    throw new Error(response.data?.error || 'Não foi possível iniciar a conexão com o Instagram');
  };

  const handleConnect = async (id) => {
    const canal = channels.find(c => c.id === id);
    if (!canal) return;

    if (canal.tipo === 'instagram') {
      const status = canal.state || canal.status;
      if (status === 'connected' && (canal.dados_extras || {}).instagram_user_id) {
        pushToast({ show: true, message: 'Instagram já está conectado!', type: 'info' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'info' }), 3000);
        return;
      }

      let finalProviderId = provedorId;
      if (!finalProviderId || String(finalProviderId) === 'null') {
        const userStr = localStorage.getItem('user');
        if (userStr) {
          try {
            const userObj = JSON.parse(userStr);
            finalProviderId = userObj.provedor_id || userObj.provedor?.id;
          } catch (e) {
          }
        }
      }
      if (!finalProviderId || String(finalProviderId) === 'null') {
        finalProviderId = '1';
      }

      navigate(`/app/instagram/finalizando?provider_id=${finalProviderId}&channel_id=${id}`);
      return;
    }

    // Tratamento específico para WhatsApp Oficial - Navegar diretamente para tela de espera/onboarding
    if (canal.tipo === 'whatsapp_oficial') {
      const status = canal.state || canal.status;
      if (canal.ativo && (status === 'connected' || status === 'open' || status === 'Conectado')) {
        pushToast({ show: true, message: 'WhatsApp Oficial já está conectado!', type: 'info' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'info' }), 3000);
        return;
      }

      // Garantir que temos um ID de provedor válido (não string "null" ou undefined)
      let finalProviderId = provedorId;
      if (!finalProviderId || String(finalProviderId) === 'null') {
        const userStr = localStorage.getItem('user');
        if (userStr) {
          try {
            const userObj = JSON.parse(userStr);
            finalProviderId = userObj.provedor_id || userObj.provedor?.id;
          } catch (e) {
          }
        }
      }
      
      // Se ainda for nulo, usar '1' como último recurso ou falhar silenciosamente
      if (!finalProviderId || String(finalProviderId) === 'null') {
        finalProviderId = '1'; 
      }

      // IMEDIATO: Ir para a tela que gerencia o fluxo automático da Meta, passando o ID do canal
      navigate(`/app/meta/finalizando?provider_id=${finalProviderId}&channel_id=${id}`);
      return;
    }

    if (canal.tipo === 'app_mobile') {
      setSelectedType('app_mobile');
      setFormData({
        nome: canal.nome || 'App Mobile',
        email: '',
        url: '',
        app_token: '',
        app_default_team_id: String(
          canal.app_default_team_id
            || canal.dados_extras?.app_default_team_id
            || '',
        ),
      });
      setShowModal(true);
      return;
    }

    // Tratamento específico para Telegram - abrir modal de configuração
    if (canal.tipo === 'telegram') {
      setSelectedType('telegram');
      setFormData({
        nome: canal.nome,
        api_id: canal.api_id || '',
        api_hash: canal.api_hash || '',
        app_title: canal.app_title || '',
        phone_number: canal.phone_number || ''
      });
      setShowModal(true);
      return;
    }

    // Validação para WhatsApp
    if (canal.tipo !== 'whatsapp' && canal.tipo !== 'whatsapp_session') return;

    // Só bloquear se realmente estiver conectado
    const status = canal.state || canal.status;
    if (status === 'connected' || status === 'open' || status === 'Conectado') {
      pushToast({ show: true, message: t('whatsapp_ja_conectado'), type: 'error' });
      setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
      return;
    }
    if (canal.tipo === 'whatsapp_session') {
      setShowPairingMenu(true);
      setPendingConnectId(id);
      return;
    }
    // WhatsApp normal
    setConnectingId(id);
    setQrCard('');
    setQrCardLoading(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios.post('/api/canais/get_evolution_qr/', { instance_name: canal.nome }, {
      headers: { Authorization: `Token ${token}` }
    }).then(res => {
      const qr = res.data.base64 || res.data.qrcode || res.data.qrcode_url || '';
      setQrCard(qr);
      setQrCardLoading(false);
    }).catch(() => {
      setQrCardLoading(false);
      pushToast({ show: true, message: t('erro_gerar_qr_code'), type: 'error' });
      setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
    });
  };

  // Nova função para buscar o método escolhido
  const handlePairingMethod = (method) => {
    setPairingMethod(method);
    setShowPairingMenu(false);
    if (method === 'paircode') {
      setShowPhoneInput(true);
      setPairingPhone('');
      setPairingResult(null);
    } else {
      setConnectingId(pendingConnectId);
      setQrCard('');
      setQrCardLoading(true);
      setShowPhoneInput(false);
      setPairingResult(null);
      // QR Code fluxo normal
      const canal = channels.find(c => c.id === pendingConnectId);
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      axios.post(buildApiPath('/api/whatsapp/session/qr/'), { instance_name: canal.nome, method: 'qrcode' }, {
        headers: { Authorization: `Token ${token}` }
      }).then(res => {
        setQrCard(res.data.qrcode || '');
        setQrCardLoading(false);
      }).catch(() => {
        setQrCardLoading(false);
        pushToast({ show: true, message: t('erro_gerar_qr_code'), type: 'error' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
      });
    }
  };

  // Função para enviar o número e obter o código de pareamento
  const handlePairingPhoneSubmit = () => {
    if (!pairingPhone) return;
    setPairingLoading(true);
    setPairingResult(null);
    const canal = channels.find(c => c.id === pendingConnectId);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios.post(buildApiPath('/api/whatsapp/session/qr/'), { instance_name: canal.nome, method: 'paircode', phone: pairingPhone }, {
      headers: { Authorization: `Token ${token}` }
    }).then(res => {
      // Extrair paircode da resposta (pode estar em res.data.paircode ou res.data.instance.paircode)
      const paircode = res.data.paircode || (res.data.instance && res.data.instance.paircode) || null;
      if (paircode) {
        setPairingResult(paircode);
      } else {
        setPairingResult(res.data.message || 'Erro ao obter código de pareamento');
      }
      setPairingLoading(false);
    }).catch((error) => {
      setPairingResult('Erro ao obter código de pareamento');
      setPairingLoading(false);
    });
  };

  const handleDisconnect = (id) => {
    const canal = channels.find(c => c.id === id);
    if (!canal) return;
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (canal.tipo === 'whatsapp_session') {
      // Desconectar via endpoint especial
      axios.post(buildApiPath(`/api/whatsapp/session/disconnect/${id}/`), {}, {
        headers: { Authorization: `Token ${token}` }
      })
        .then(() => {
          // Atualizar canais do backend após desconectar
          fetchCanais(token).then(res2 => {
            setChannels(Array.isArray(res2.data) ? res2.data : res2.data.results || []);
          });
          pushToast({ show: true, message: t('whatsapp_session_desconectado'), type: 'success' });
          setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
        })
        .catch(() => {
          pushToast({ show: true, message: t('erro_desconectar_session'), type: 'error' });
        });
      return;
    }
    // WhatsApp normal (Evolution)
    setConnectingId(id);
    setQrCard('');
    setQrCardLoading(true);
    axios.post(buildApiPath('/api/whatsapp/evolution/logout/'), { instance_name: canal.nome }, {
      headers: { Authorization: `Token ${token}` }
    })
      .then(() => {
        fetchCanais(token).then(res2 => {
          setChannels(Array.isArray(res2.data) ? res2.data : res2.data.results || []);
        });
        setQrCardLoading(false);
        pushToast({ show: true, message: t('whatsapp_desconectado'), type: 'success' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
      })
      .catch(() => {
        setQrCardLoading(false);
        pushToast({ show: true, message: t('erro_desconectar_whatsapp'), type: 'error' });
      });
  };

  const handleDelete = (id) => {
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios.delete(`/api/canais/${id}/`, {
      headers: { Authorization: `Token ${token}` }
    }).then(() => {
      setChannels(channels => channels.filter(c => c.id !== id));
    }).catch(() => {
      toast.error(t('erro_excluir_canal'));
    });
  };

  const handleEdit = (channel) => {
    if (channel.tipo === 'whatsapp_oficial') {
      setSelectedChannelForTemplates(channel);
      setShowTemplateModal(true);
      loadTemplates(channel);
    } else {
      // Para outros tipos de canal, funcionalidade ainda não implementada
      toast.error('Funcionalidade de edição para este tipo de canal ainda não está disponível');
    }
  };

  const handleEditName = (channel) => {
    setChannelToEdit(channel);
    setNewName(channel.nome || '');
    setIsEditingName(true);
  };

  const handleSaveName = async () => {
    if (!channelToEdit || !newName.trim()) return;

    setSavingName(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.patch(`/api/canais/${channelToEdit.id}/`, {
        nome: newName.trim()
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.status === 200) {
        setChannels(prev => prev.map(c => c.id === channelToEdit.id ? { ...c, nome: response.data.nome } : c));
        setIsEditingName(false);
        setChannelToEdit(null);
        setNewName('');
        pushToast({ show: true, message: 'Nome do canal atualizado com sucesso!', type: 'success' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
      }
    } catch (error) {
      toast.error('Erro ao salvar nome do canal. Tente novamente.');
    } finally {
      setSavingName(false);
    }
  };

  const stopVoiceCallsPolling = () => {
    if (voiceCallsPollRef.current) {
      clearInterval(voiceCallsPollRef.current);
      voiceCallsPollRef.current = null;
    }
  };

  const applyVoiceCallsState = (channelId, voiceCalls) => {
    if (!voiceCalls) return;
    setChannels((prev) =>
      prev.map((ch) =>
        ch.id === channelId
          ? { ...ch, dados_extras: { ...(ch.dados_extras || {}), voice_calls: voiceCalls } }
          : ch
      )
    );
  };

  const startVoiceCallsPolling = (channelId) => {
    stopVoiceCallsPolling();
    voiceCallsPollRef.current = setInterval(async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) return;
        const res = await axios.get(`/api/canais/${channelId}/voice-calls/status/`, {
          headers: { Authorization: `Token ${token}` },
        });
        const vc = res.data?.voice_calls;
        if (vc) {
          applyVoiceCallsState(channelId, vc);
          if (vc.status === 'connected') {
            stopVoiceCallsPolling();
            setVoiceCallsModal(null);
            pushToast({
              show: true,
              message: 'Ligações ativadas! Você já pode atender chamadas pelo NioHub.',
              type: 'success',
            });
            setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 4000);
          } else if (res.data?.qrcode) {
            setVoiceCallsModal((prev) =>
              prev && prev.channelId === channelId
                ? { ...prev, qrcode: res.data.qrcode }
                : prev
            );
          }
        }
      } catch {
        /* polling silencioso */
      }
    }, 3000);
  };

  const handleVoiceCallsSetup = async (channelId, mode = 'setup') => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      pushToast({ show: true, message: 'Token não encontrado. Faça login novamente.', type: 'error' });
      return;
    }
    setVoiceCallsBusyId(channelId);
    try {
      const path =
        mode === 'repair'
          ? `/api/canais/${channelId}/voice-calls/repair/`
          : `/api/canais/${channelId}/voice-calls/setup/`;
      const res = await axios.post(path, {}, { headers: { Authorization: `Token ${token}` } });
      const vc = res.data?.voice_calls;
      if (vc) applyVoiceCallsState(channelId, vc);
      if (vc?.status === 'connected') {
        pushToast({
          show: true,
          message: 'Ligações já estão conectadas neste canal.',
          type: 'success',
        });
        return;
      }
      setVoiceCallsModal({
        channelId,
        qrcode: res.data?.qrcode || '',
      });
      startVoiceCallsPolling(channelId);
    } catch (error) {
      const msg =
        error?.response?.data?.error ||
        'Não foi possível iniciar ligações. Verifique se o serviço NioHub Calls está configurado.';
      pushToast({ show: true, message: msg, type: 'error' });
    } finally {
      setVoiceCallsBusyId(null);
    }
  };

  const handleVoiceCallsDisable = async (channelId) => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      toast.error('Token não encontrado. Faça login novamente.');
      return;
    }
    if (!window.confirm('Desativar ligações por voz neste canal? As mensagens pela API oficial não serão afetadas.')) {
      return;
    }
    stopVoiceCallsPolling();
    setVoiceCallsModal(null);
    setVoiceCallsBusyId(channelId);
    try {
      await axios.delete(`/api/canais/${channelId}/voice-calls/`, {
        headers: { Authorization: `Token ${token}` },
        timeout: 20000,
      });
      applyVoiceCallsState(channelId, { status: 'disabled', enabled: false });
      toast.success('Ligações desativadas.');
    } catch (error) {
      const msg =
        error?.response?.data?.error ||
        (error?.code === 'ECONNABORTED' ? 'Tempo esgotado ao desativar ligações.' : null) ||
        error?.message ||
        'Erro ao desativar ligações.';
      toast.error(msg);
    } finally {
      setVoiceCallsBusyId(null);
    }
  };

  useEffect(() => () => stopVoiceCallsPolling(), []);

  const handleToggleIA = async (channelId, iaAtiva) => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        pushToast({ show: true, message: 'Token não encontrado. Faça login novamente.', type: 'error' });
        return;
      }

      const response = await axios.patch(
        `/api/canais/${channelId}/`,
        { ia_ativa: iaAtiva },
        {
          headers: { Authorization: `Token ${token}` }
        }
      );

      // Atualizar o canal na lista local
      setChannels(prevChannels =>
        prevChannels.map(ch =>
          ch.id === channelId ? { ...ch, ia_ativa: iaAtiva } : ch
        )
      );

      pushToast({
        show: true,
        message: iaAtiva ? 'ChatBot ativado com sucesso!' : 'ChatBot desativado com sucesso!',
        type: 'success'
      });
    } catch (error) {
      pushToast({
        show: true,
        message: 'Erro ao atualizar status do ChatBot. Tente novamente.',
        type: 'error'
      });
    }
  };

  // Funções de tradução
  const translateCategory = (category) => {
    const translations = {
      'UTILITY': 'Utilidade',
      'MARKETING': 'Marketing',
      'AUTHENTICATION': 'Autenticação'
    };
    return translations[category] || category;
  };

  const translateStatus = (status) => {
    const translations = {
      'APPROVED': 'Aprovado',
      'REJECTED': 'Rejeitado',
      'PENDING': 'Em análise',
      'PAUSED': 'Pausado',
      'DISABLED': 'Desabilitado'
    };
    return translations[status] || status;
  };

  const translateQuality = (quality) => {
    if (!quality) return null;

    // Se for objeto, extrair o score
    let qualityValue = quality;
    if (typeof quality === 'object') {
      qualityValue = quality.score || quality.quality || quality;
    }

    // Se for UNKNOWN ou vazio, não exibir
    if (!qualityValue || qualityValue === 'UNKNOWN' || qualityValue === '') {
      return null;
    }

    const translations = {
      'GREEN': 'Alta',
      'YELLOW': 'Média',
      'RED': 'Baixa',
      'UNKNOWN': null // Não exibir
    };

    return translations[qualityValue] || qualityValue;
  };

  const translateLanguage = (language) => {
    const translations = {
      'pt_BR': 'Português (Brasil)',
      'en_US': 'Inglês (EUA)',
      'es_ES': 'Espanhol (Espanha)',
      'es_MX': 'Espanhol (México)',
      'fr_FR': 'Francês',
      'de_DE': 'Alemão',
      'it_IT': 'Italiano',
      'ja_JP': 'Japonês',
      'ko_KR': 'Coreano',
      'zh_CN': 'Chinês (Simplificado)',
      'zh_TW': 'Chinês (Tradicional)'
    };
    return translations[language] || language;
  };

  const translateComponentType = (type) => {
    const translations = {
      'HEADER': 'Cabeçalho',
      'BODY': 'Corpo',
      'FOOTER': 'Rodapé',
      'BUTTONS': 'Botões',
      'GREETING': 'Saudação',
      'CAROUSEL': 'Carrossel',
      'ALBUM': 'Álbum'
    };
    return translations[type] || type;
  };

  const translateRejectionReason = (reason) => {
    if (!reason) return null;

    // Se for objeto, extrair a mensagem
    let reasonValue = reason;
    if (typeof reason === 'object') {
      reasonValue = reason.message || reason.reason || reason;
    }

    // Se for string vazia ou "NONE", não exibir
    if (!reasonValue || reasonValue === 'NONE' || reasonValue === '') {
      return null;
    }

    const translations = {
      'INVALID_FORMAT': 'Formato inválido',
      'MISLEADING_CONTENT': 'Conteúdo enganoso',
      'UNAUTHORIZED_USE_OF_OTHER_ENTITY': 'Uso não autorizado de outra entidade',
      'INCORRECT_CATEGORY': 'Categoria incorreta',
      'POLICY_VIOLATION': 'Violação de política',
      'SPAM': 'Spam',
      'FREQUENCY_CAP_EXCEEDED': 'Limite de frequência excedido',
      'TEMPLATE_NAME_ALREADY_EXISTS': 'Nome do modelo já existe',
      'TEMPLATE_NAME_TOO_LONG': 'Nome do modelo muito longo',
      'TEMPLATE_NAME_INVALID': 'Nome do modelo inválido',
      'BODY_TEXT_TOO_LONG': 'Texto do corpo muito longo',
      'BODY_TEXT_EMPTY': 'Texto do corpo vazio',
      'HEADER_TEXT_TOO_LONG': 'Texto do cabeçalho muito longo',
      'FOOTER_TEXT_TOO_LONG': 'Texto do rodapé muito longo',
      'BUTTON_TITLE_TOO_LONG': 'Título do botão muito longo',
      'BUTTON_TITLE_EMPTY': 'Título do botão vazio',
      'BUTTON_URL_INVALID': 'URL do botão inválida',
      'BUTTON_PHONE_NUMBER_INVALID': 'Número de telefone do botão inválido',
      'MEDIA_NOT_FOUND': 'Mídia não encontrada',
      'MEDIA_TYPE_INVALID': 'Tipo de mídia inválido',
      'VARIABLE_FORMAT_INVALID': 'Formato de variável inválido',
      'VARIABLE_EXAMPLE_MISSING': 'Exemplo de variável ausente',
      'COMPONENT_TYPE_INVALID': 'Tipo de componente inválido',
      'COMPONENT_MISSING': 'Componente ausente',
      'LANGUAGE_NOT_SUPPORTED': 'Idioma não suportado',
      'CATEGORY_INVALID': 'Categoria inválida'
    };

    return translations[reasonValue] || reasonValue;
  };

  const loadTemplates = async (channel) => {
    if (!channel || channel.tipo !== 'whatsapp_oficial') return;

    setLoadingTemplates(true);
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`/api/canais/${channel.id}/message-templates/`, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        setTemplates(response.data.templates || []);
      } else {
      }
    } catch (error) {
    } finally {
      setLoadingTemplates(false);
    }
  };

  const handleDeleteTemplate = async (template) => {
    if (!window.confirm(`Tem certeza que deseja deletar o modelo "${template.name}"?`)) {
      return;
    }

    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const templateId = template.id || `${template.name}:${template.language}`;
      const response = await axios.delete(
        `/api/canais/${selectedChannelForTemplates.id}/message-templates/${templateId}/`,
        { headers: { Authorization: `Token ${token}` } }
      );

      if (response.data.success) {
        await loadTemplates(selectedChannelForTemplates);
        toast.deleted('Modelo excluído com sucesso.');
      } else {
        toast.error('Erro ao deletar modelo: ' + (response.data.error || 'Erro desconhecido'));
      }
    } catch (error) {
      toast.apiError(error, 'Erro ao deletar modelo.');
    }
  };

  // Função para extrair variáveis de um texto (ex: {{1}}, {{2}}, etc.)
  const extractVariables = (text) => {
    if (!text) return [];
    const matches = text.match(/\{\{(\d+)\}\}/g);
    if (!matches) return [];
    const uniqueVars = [...new Set(matches)];
    return uniqueVars
      .map(match => {
        const num = match.match(/\{?\{?(\d+)\}?\}?/)?.[1];
        return num ? parseInt(num) : null;
      })
      .filter(Boolean)
      .sort((a, b) => a - b);
  };

  // Função para validar incompatibilidade entre tipo de variável e formato usado
  const validateVariableFormat = () => {
    if (templateForm.variable_type === 'nome') {
      // Se tipo é "nome", não pode usar variáveis numéricas {{1}}, {{2}}, etc.
      const bodyVars = extractVariables(templateForm.body.text);
      const headerVars = templateForm.header.type === 'text' ? extractVariables(templateForm.header.text) : [];
      const footerVars = extractVariables(templateForm.footer.text);
      const allVars = [...new Set([...bodyVars, ...headerVars, ...footerVars])];

      if (allVars.length > 0) {
        // Verifica se está usando formato numérico ({{1}}, {{2}})
        const hasNumericVars = templateForm.body.text.match(/\{\{\d+\}\}/) ||
          (templateForm.header.type === 'text' && templateForm.header.text.match(/\{\{\d+\}\}/)) ||
          templateForm.footer.text.match(/\{\{\d+\}\}/);

        if (hasNumericVars) {
          return {
            hasError: true,
            message: "Este modelo contém parâmetros de variáveis com formato incorreto. Os parâmetros variáveis devem ser caracteres em letra minúscula, sublinhados e números inteiros com dois conjuntos de chaves (por exemplo, {{customer_name}}, {{order_id}})."
          };
        }
      }
    }
    return { hasError: false, message: '' };
  };

  // Função para atualizar amostras quando o texto mudar
  const updateVariableSamples = (bodyText, headerText, footerText) => {
    const bodyVars = extractVariables(bodyText);
    const headerVars = templateForm.header.type === 'text' ? extractVariables(headerText) : [];
    const footerVars = extractVariables(footerText);

    const allVars = [...new Set([...bodyVars, ...headerVars, ...footerVars])];
    const newSamples = { ...variableSamples };

    // Manter apenas variáveis que ainda existem
    Object.keys(newSamples).forEach(varNum => {
      if (!allVars.includes(parseInt(varNum))) {
        delete newSamples[varNum];
      }
    });

    // Adicionar novas variáveis com valores padrão usando o tipo global
    allVars.forEach(varNum => {
      if (!newSamples[varNum]) {
        newSamples[varNum] = { type: templateForm.variable_type || 'number', example: '' };
      }
    });

    setVariableSamples(newSamples);
  };

  // Função para substituir variáveis pelos valores de exemplo no preview
  const replaceVariablesWithExamples = (text) => {
    if (!text) return '';
    return text.replace(/\{\{(\d+)\}\}/g, (match, varNum) => {
      const sample = variableSamples[parseInt(varNum)];
      if (sample && sample.example) {
        return sample.example;
      }
      return match; // Se não tiver exemplo, mantém a variável
    });
  };

  // Função para converter todas as variáveis numéricas para formato nomeado
  const convertToNamedFormat = (text, varNumbers) => {
    if (!text) return text;
    let convertedText = text;
    // Converter todas as variáveis: {{1}} -> {{var_1}}, {{2}} -> {{var_2}}, etc.
    varNumbers.forEach(varNum => {
      const regex = new RegExp(`\\{\\{${varNum}\\}\\}`, 'g');
      convertedText = convertedText.replace(regex, `{{var_${varNum}}}`);
    });
    return convertedText;
  };

  const buildTemplateComponents = () => {
    const components = [];

    // Header
    if (templateForm.header.type !== 'none') {
      const header = { type: 'HEADER' }; // Tipo sempre HEADER (maiúscula)
      let shouldAddHeader = true;

      if (templateForm.header.type === 'text') {
        header.format = 'TEXT'; // Formato do header
        if (!templateForm.header.text) {
          shouldAddHeader = false;
        } else {
          header.text = templateForm.header.text;
          if (templateForm.header.has_variables) {
            const headerVars = extractVariables(templateForm.header.text);
            if (headerVars.length > 0) {
              // Usar o tipo global para determinar o formato
              const useNamedFormat = templateForm.variable_type === 'nome';

              if (useNamedFormat) {
                // Usar formato nomeado para header
                const namedParams = headerVars.map(varNum => {
                  const sample = variableSamples[varNum];
                  return {
                    param_name: `var_${varNum}`,
                    example: sample?.example || ''
                  };
                }).filter(param => param.example !== '');
                if (namedParams.length > 0) {
                  header.example = { header_text_named_params: namedParams };
                  header.text = convertToNamedFormat(templateForm.header.text, headerVars);
                }
              } else {
                // Usar formato posicional
                const exampleValues = headerVars.map(varNum => {
                  const sample = variableSamples[varNum];
                  return sample?.example || '';
                }).filter(val => val !== '');
                if (exampleValues.length > 0) {
                  header.example = { header_text: [exampleValues] };
                }
              }
            }
          }
        }
      } else if (templateForm.header.type === 'image') {
        header.format = 'IMAGE';
        // Para headers de mídia, o exemplo é obrigatório
        if (templateForm.header.media_id) {
          header.example = {
            header_handle: [templateForm.header.media_id]
          };
        } else if (templateForm.header.media_link) {
          // Para links, usar header_handle com o link
          header.example = {
            header_handle: [templateForm.header.media_link]
          };
        } else {
          // Se não há mídia, não deve adicionar o header
          shouldAddHeader = false;
        }
      } else if (templateForm.header.type === 'video') {
        header.format = 'VIDEO';
        if (templateForm.header.media_id) {
          header.example = {
            header_handle: [templateForm.header.media_id]
          };
        } else if (templateForm.header.media_link) {
          header.example = {
            header_handle: [templateForm.header.media_link]
          };
        } else {
          shouldAddHeader = false;
        }
      } else if (templateForm.header.type === 'document') {
        header.format = 'DOCUMENT';
        if (templateForm.header.media_id) {
          header.example = {
            header_handle: [templateForm.header.media_id]
          };
        } else if (templateForm.header.media_link) {
          header.example = {
            header_handle: [templateForm.header.media_link]
          };
        } else {
          shouldAddHeader = false;
        }
      }

      if (shouldAddHeader) {
        components.push(header);
      }
    }

    // Body (obrigatório)
    if (templateForm.body.text) {
      const body = {
        type: 'BODY', // Tipo sempre BODY (maiúscula)
        text: templateForm.body.text
      };
      if (templateForm.body.has_variables) {
        const bodyVars = extractVariables(templateForm.body.text);
        if (bodyVars.length > 0) {
          // Usar o tipo global para determinar o formato
          const useNamedFormat = templateForm.variable_type === 'nome';

          if (useNamedFormat) {
            // Usar formato nomeado
            const namedParams = bodyVars.map(varNum => {
              const sample = variableSamples[varNum];
              return {
                param_name: `var_${varNum}`,
                example: sample?.example || ''
              };
            }).filter(param => param.example !== '');
            if (namedParams.length > 0) {
              body.example = { body_text_named_params: namedParams };
              // Converter o texto para usar nomes: {{1}} -> {{var_1}}
              body.text = convertToNamedFormat(templateForm.body.text, bodyVars);
            }
          } else {
            // Usar formato posicional
            const exampleValues = bodyVars.map(varNum => {
              const sample = variableSamples[varNum];
              return sample?.example || '';
            }).filter(val => val !== '');
            if (exampleValues.length > 0) {
              body.example = { body_text: [exampleValues] };
            }
          }
        }
      }
      components.push(body);
    }

    // Footer
    if (templateForm.footer.text) {
      const footer = {
        type: 'FOOTER', // Tipo sempre FOOTER (maiúscula)
        text: templateForm.footer.text
      };
      // Converter para formato nomeado se necessário
      const footerVars = extractVariables(templateForm.footer.text);
      const useNamedFormat = templateForm.variable_type === 'nome';

      if (useNamedFormat && footerVars.length > 0) {
        footer.text = convertToNamedFormat(templateForm.footer.text, footerVars);
      }
      components.push(footer);
    }

    // Buttons
    if (templateForm.buttons.length > 0) {
      const buttonComponents = templateForm.buttons
        .filter(btn => btn.type && btn.title)
        .map((btn, idx) => {
          // Determinar o tipo do botão conforme a Meta
          let buttonType = 'QUICK_REPLY';
          if (btn.type === 'URL') {
            buttonType = 'URL';
          } else if (btn.type === 'PHONE_NUMBER' || btn.type === 'PHONE_NUMBER_WHATSAPP') {
            buttonType = 'PHONE_NUMBER';
          } else {
            // QUICK_REPLY ou COPY_CODE
            buttonType = 'QUICK_REPLY';
          }

          const button = {
            type: buttonType, // type em vez de sub_type
            text: btn.title || `Button ${idx + 1}` // Texto do botão (obrigatório)
          };

          if (btn.type === 'QUICK_REPLY' || btn.type === 'COPY_CODE') {
            const payload = btn.type === 'COPY_CODE' ? (btn.offer_code || `offer_${idx}`) : (btn.payload || `btn_${idx}`);
            if (payload) {
              button.payload = payload;
            }
          } else if (btn.type === 'URL') {
            if (btn.url) {
              button.url = btn.url;
            } else {
              // Se não tem URL, não deve adicionar o botão
              return null;
            }
          } else if (btn.type === 'PHONE_NUMBER' || btn.type === 'PHONE_NUMBER_WHATSAPP') {
            if (btn.phone_number) {
              button.phone_number = btn.phone_number;
            } else {
              // Se não tem número, não deve adicionar o botão
              return null;
            }
          }

          return button;
        })
        .filter(Boolean);

      if (buttonComponents.length > 0) {
        components.push({
          type: 'BUTTONS', // Tipo sempre BUTTONS (maiúscula)
          buttons: buttonComponents
        });
      }
    }

    return components;
  };

  const handleCreateTemplate = async () => {
    if (!templateForm.name || !templateForm.body.text) {
      toast.error('Nome e corpo da mensagem são obrigatórios');
      return;
    }

    if (!/^[a-z0-9_]+$/.test(templateForm.name)) {
      toast.error('O nome do modelo deve conter apenas letras minúsculas, números e sublinhados');
      return;
    }

    if (templateForm.name.length > 512) {
      toast.error('O nome do modelo não pode ter mais de 512 caracteres');
      return;
    }

    setCreatingTemplate(true);
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const components = buildTemplateComponents();

      // Usar o tipo global para determinar o formato
      const parameterFormat = templateForm.variable_type === 'nome' ? 'named' : 'positional';

      const response = await axios.post(
        `/api/canais/${selectedChannelForTemplates.id}/message-templates/`,
        {
          name: templateForm.name,
          category: templateForm.category,
          language: templateForm.language,
          parameter_format: parameterFormat,
          components: components
        },
        { headers: { Authorization: `Token ${token}` } }
      );

      if (response.data.success) {
        toast.success('Modelo criado com sucesso! Ele será analisado pela Meta e pode levar até 24 horas para ser aprovado.');
        setShowCreateTemplate(false);
        resetTemplateForm();
        await loadTemplates(selectedChannelForTemplates);
      } else {
        toast.error('Erro ao criar modelo: ' + (response.data.error || 'Erro desconhecido'));
      }
    } catch (error) {
      toast.apiError(error, 'Erro ao criar modelo.');
    } finally {
      setCreatingTemplate(false);
    }
  };

  const resetTemplateForm = () => {
    setTemplateForm({
      name: '',
      category: 'UTILITY',
      language: 'pt_BR',
      variable_type: 'number',
      body: { text: '', has_variables: false },
      header: { type: 'none', text: '', media_id: '', media_link: '', has_variables: false },
      footer: { text: '', has_variables: false },
      buttons: []
    });
    setVariableSamples({});
  };

  const handleAdd = () => {
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios.get('/api/canais/disponiveis/', {
      headers: { Authorization: `Token ${token}` }
    }).then(res => {
      const list = Array.isArray(res.data) ? res.data : [];
      const hasAppMobile = channels.some((c) => c.tipo === 'app_mobile');
      const filtered = list.filter((opt) => opt.tipo !== 'whatsapp' && (opt.tipo !== 'app_mobile' || !hasAppMobile));
      setAvailableTypes(filtered);
      setShowModal(true);
      setSelectedType(null);
      setInstanceName('');
      setQrCode('');
      setFormData({ nome: '', email: '', url: '', app_token: '' });
    }).catch(error => {
      // Se falhar ao buscar, usar lista padrão
      const hasAppMobile = channels.some((c) => c.tipo === 'app_mobile');
      const defaultTypes = ALL_CHANNEL_TYPES.filter((opt) => opt.tipo !== 'whatsapp' && (opt.tipo !== 'app_mobile' || !hasAppMobile));
      setAvailableTypes(defaultTypes);
      setShowModal(true);
      setSelectedType(null);
      setInstanceName('');
      setQrCode('');
      setFormData({ nome: '', email: '', url: '', app_token: '' });
    });
  };

  const handleSelectType = (tipo) => {
    setSelectedType(tipo);
    setInstanceName('');
    setQrCode('');
    setFormData({ nome: '', email: '', url: '', app_token: '' });
  };

  const handleGenerateQr = () => {
    setQrLoading(true);
    const token = localStorage.getItem('token');
    axios.post('/api/canais/create_evolution_instance/', { instance_name: instanceName }, {
      headers: { Authorization: `Token ${token}` }
    }).then(() => {
      // Agora busca o QR Code
      axios.post('/api/canais/get_evolution_qr/', { instance_name: instanceName }, {
        headers: { Authorization: `Token ${token}` }
      }).then(res => {

        // Aceita base64, qrcode ou qrcode_url
        const qr = res.data.base64 || res.data.qrcode || res.data.qrcode_url || '';
        setQrCode(qr);
        setQrLoading(false);
      }).catch(() => {
        setQrLoading(false);
        toast.error(t('erro_gerar_qr_code'));
      });
    }).catch(() => {
      setQrLoading(false);
      toast.error(t('erro_criar_instancia'));
    });
  };

  const handleSaveWhatsapp = () => {
    setAdding(true);
    const token = localStorage.getItem('token');
    axios.post('/api/canais/', withProviderContext({ tipo: selectedType, nome: instanceName }), {
      headers: { Authorization: `Token ${token}` }
    }).then(() => {
      setShowModal(false);
      setAdding(false);
      setSelectedType(null);
      // Atualiza canais
      setLoading(true);
      axios.get('/api/canais/', {
        headers: { Authorization: `Token ${token}` }
      }).then(res => {
        setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
        setLoading(false);
      });
    }).catch((err) => {
      setAdding(false);
      toast.error(canalErrorMessage(err, t('erro_adicionar_canal')));
    });
  };

  const handleAddOtherChannel = () => {
    setAdding(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    if (selectedType === 'instagram') {
      const canalData = withProviderContext({
        tipo: 'instagram',
        nome: (formData.nome || '').trim() || 'Instagram',
      });

      axios.post('/api/canais/', canalData, {
        headers: { Authorization: `Token ${token}` },
      }).then(() => {
        setAdding(false);
        setShowModal(false);
        setSelectedType(null);
        setFormData({ nome: '', email: '', url: '', app_token: '' });
        fetchCanais(token).then((res) => {
          setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
        });
      }).catch((err) => {
        setAdding(false);
        toast.error(canalErrorMessage(err, t('erro_adicionar_canal')));
      });
      return;
    }

    if (selectedType === 'app_mobile') {
      const appToken = (formData.app_token || '').trim();
      const existing = channels.find((c) => c.tipo === 'app_mobile');
      if (!existing && !appToken) {
        setAdding(false);
        toast.error('Informe o token sk_live_ gerado no painel do app.');
        return;
      }
      const teamIdRaw = (formData.app_default_team_id || '').trim();
      const dadosExtras = {
        ...(existing?.dados_extras || {}),
        ...(teamIdRaw
          ? { app_default_team_id: Number(teamIdRaw) }
          : { app_default_team_id: null }),
      };
      const canalData = withProviderContext({
        tipo: 'app_mobile',
        nome: (formData.nome || '').trim() || 'App Mobile',
        dados_extras: dadosExtras,
        ...(appToken ? { token: appToken } : {}),
      });
      const req = existing
        ? axios.patch(`/api/canais/${existing.id}/`, canalData, {
            headers: { Authorization: `Token ${token}` },
          })
        : axios.post('/api/canais/', canalData, {
            headers: { Authorization: `Token ${token}` },
          });

      req.then(() => {
        setAdding(false);
        setShowModal(false);
        setSelectedType(null);
        setFormData({ nome: '', email: '', url: '', app_token: '', app_default_team_id: '' });
        fetchCanais(token).then((res) => {
          setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
        });
        toast.success(
          existing
            ? 'Canal App Mobile atualizado. Novos atendimentos do app vão para a equipe configurada.'
            : 'Canal App Mobile conectado. Mensagens do app entram na fila Espera.',
        );
      }).catch((err) => {
        setAdding(false);
        const data = err?.response?.data || {};
        const msg =
          data.app_default_team_id
          || data.token
          || data.error
          || t('erro_adicionar_canal');
        toast.error(Array.isArray(msg) ? msg[0] : msg);
      });
      return;
    }

    // Preparar dados do canal
    const canalData = withProviderContext({
      tipo: selectedType,
      ...formData
    });

    // Para Telegram, verificar se estamos atualizando um canal existente
    if (selectedType === 'telegram') {
      // Buscar o canal existente pelo nome
      const existingChannel = channels.find(c => c.tipo === 'telegram' && c.nome === formData.nome);

      if (existingChannel) {
        // Atualizar canal existente com PATCH
        axios.patch(`/api/canais/${existingChannel.id}/`, canalData, {
          headers: { Authorization: `Token ${token}` }
        }).then((response) => {
          handleTelegramResponse(response, token);
        }).catch((err) => {
          setAdding(false);
          toast.error(canalErrorMessage(err, t('erro_adicionar_canal')));
        });
        return;
      } else {
        // Se não encontrou, gerar nome automaticamente
        canalData.nome = formData.app_title || `telegram_${Date.now()}`;
      }
    }

    // Criar novo canal (POST)
    axios.post('/api/canais/', canalData, {
      headers: { Authorization: `Token ${token}` }
    }).then((response) => {
      handleTelegramResponse(response, token);
    }).catch((err) => {
      setAdding(false);
      toast.error(canalErrorMessage(err, t('erro_adicionar_canal')));
    });
  };

  const handleTelegramResponse = (response, token) => {
    setAdding(false);

    // Se for Telegram e código foi enviado, mostrar modal de verificação
    if (selectedType === 'telegram') {

      // Verificar se o código foi enviado com sucesso
      if (response.data.telegram_code_sent) {
        const codeResult = response.data.telegram_code_sent;

        // Verificar se houve erro primeiro
        if (!codeResult.success) {

          const errorMsg = codeResult.error || 'Erro ao enviar código de verificação. Tente novamente.';

          // Verificar se é FloodWaitError e mostrar mensagem mais amigável
          if (errorMsg.includes('bloqueou temporariamente') || errorMsg.includes('Aguarde') || errorMsg.includes('wait of')) {
            toast.info(`⚠️ ${errorMsg}\n\nO Telegram limita o número de códigos que podem ser enviados em um período. Por favor, aguarde o tempo indicado antes de tentar novamente.`);
          } else {
            toast.error(`Erro ao enviar código de verificação:\n\n${errorMsg}`);
          }
          // Fechar modal e limpar estado
          setShowModal(false);
          setSelectedType(null);
          setFormData({ nome: '', email: '', url: '', api_id: '', api_hash: '', app_title: '', phone_number: '' });
          setInstanceName('');
          return;
        }

        // Se já estava autorizado, não precisa do modal
        if (codeResult.already_authorized) {

          setShowModal(false);
          setSelectedType(null);
          setFormData({ nome: '', email: '', url: '', api_id: '', api_hash: '', app_title: '', phone_number: '' });
          setInstanceName('');
          setShowAddChannelSuccess(true);
          // Atualizar lista de canais
          setLoading(true);
          fetchCanais(token).then(res => {
            setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
            setLoading(false);
          });
        } else if (codeResult.success) {
          // Código foi enviado, mostrar modal

          setTelegramChannelData(response.data);
          setShowModal(false);
          setShowTelegramCodeModal(true);
          setSelectedType(null);
          setFormData({ nome: '', email: '', url: '', api_id: '', api_hash: '', app_title: '', phone_number: '' });
          setInstanceName('');
        }
      } else {

        toast.error('Erro ao enviar código de verificação. O resultado não foi retornado pelo servidor.');
      }
    } else {
      // Para outros canais, fechar modal e atualizar lista

      setShowModal(false);
      setSelectedType(null);
      setFormData({ nome: '', email: '', url: '', api_id: '', api_hash: '', app_title: '', phone_number: '' });
      setInstanceName('');
      // Atualiza canais
      setLoading(true);
      fetchCanais(token).then(res => {
        setChannels(Array.isArray(res.data) ? res.data : res.data.results || []);
        setLoading(false);
      });
    }
  };

  const handleVerifyTelegramCode = () => {

    if (!telegramCode || telegramCode.length < 5) {
      toast.error('Código inválido. Deve ter 5 dígitos.');
      return;
    }

    if (!telegramChannelData || (!telegramChannelData.id && !telegramChannelData.nome)) {
      toast.error('Erro: Dados do canal não encontrados. Tente novamente.');
      setShowTelegramCodeModal(false);
      return;
    }

    setVerifyingCode(true);
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    const cleanCode = String(telegramCode || '').replace(/\D/g, '');

    axios.post('/api/canais/verify-telegram-code/', {
      channel_id: telegramChannelData.id,
      instance_name: telegramChannelData.nome,
      code: cleanCode
    }, {
      headers: { Authorization: `Token ${token}` }
    }).then((response) => {

      setVerifyingCode(false);

      if (response.data.success) {

        // Fechar modal e limpar estado
        setShowTelegramCodeModal(false);
        setTelegramCode('');
        const channelName = telegramChannelData?.nome;
        setTelegramChannelData(null);
        setShowAddChannelSuccess(true);

        // Se a resposta contém dados atualizados do canal, usar eles diretamente
        if (response.data.channel) {

          const updatedChannel = response.data.channel;

          // Atualizar o canal na lista
          setChannels(prevChannels => {
            const updatedChannels = prevChannels.map(ch =>
              ch.id === updatedChannel.id ? updatedChannel : ch
            );
            return updatedChannels;
          });
          setLoading(false);
        } else {
          // Fallback: buscar lista atualizada se não vier na resposta

          setTimeout(() => {
            setLoading(true);
            fetchCanais(token).then(res => {
              const channelsList = Array.isArray(res.data) ? res.data : res.data.results || [];
              setChannels(channelsList);
              setLoading(false);

              const telegramChannel = channelsList.find(c => c.tipo === 'telegram' && c.nome === channelName);
              if (telegramChannel) {

              } else {
              }
            }).catch(err => {
              setLoading(false);
            });
          }, 500);
        }
      } else if (response.data.requires_2fa || response.data.needs_password) {
        toast.error(response.data.error || 'Conta com 2FA: use a senha do Telegram nesta etapa.');
      } else {

        toast.error(response.data.error || 'Erro ao verificar código');
      }
    }).catch((error) => {
      setVerifyingCode(false);
      const errorMsg = error.response?.data?.error || error.response?.data?.detail || 'Erro ao verificar código';
      toast.error(errorMsg);
    });
  };

  const handleSgpChange = (e) => {
    const { name, value } = e.target;
    setSgp(prev => ({ ...prev, [name]: value }));
  };

  const handleSgpToggleChange = (e) => {
    const { name, checked } = e.target;
    setSgp(prev => ({ ...prev, [name]: checked }));
  };

  const handleOpenaiChange = (e) => {
    const { name, value } = e.target;
    if (name === 'ai_provider') {
      const providerCfg = AI_PROVIDER_OPTIONS[value] || AI_PROVIDER_OPTIONS.openai;
      setOpenaiConfig((prev) => {
        const models = providerCfg.models.map((m) => m.value);
        const model = models.includes(prev.openai_model)
          ? prev.openai_model
          : providerCfg.defaultModel;
        return { ...prev, ai_provider: value, openai_model: model };
      });
      return;
    }
    setOpenaiConfig((prev) => ({ ...prev, [name]: value }));
    if (name === 'openai_api_key') setOpenaiKeyDirty(true);
  };

  const handleOpenaiSave = (e) => {
    e.preventDefault();
    setSavingOpenai(true);
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    const provider = openaiConfig.ai_provider || 'openai';
    const providerCfg = AI_PROVIDER_OPTIONS[provider] || AI_PROVIDER_OPTIONS.openai;
    const typedKey = (openaiConfig.openai_api_key || '').trim();
    const payload = {
      ai_provider: provider,
      openai_model: openaiConfig.openai_model || providerCfg.defaultModel,
    };
    // Envia a chave sempre que houver valor no campo (mantém visível após salvar/F5).
    if (typedKey) {
      payload.openai_api_key = typedKey;
    }
    axios
      .patch(`/api/provedores/${provedorId}/`, payload, {
        headers: { Authorization: `Token ${token}` },
      })
      .then((res) => {
        setSavingOpenai(false);
        setOpenaiConfig({
          ai_provider: res.data?.ai_provider || provider,
          openai_api_key: res.data?.openai_api_key || typedKey,
          openai_model: res.data?.openai_model || payload.openai_model,
          openai_configured: Boolean(
            res.data?.openai_configured
            ?? (openaiConfig.openai_configured || Boolean(typedKey))
          ),
        });
        setOpenaiKeyDirty(false);
        toast.success('Configuração do agente de IA salva. A cobrança usa a sua chave.');
      })
      .catch(() => {
        setSavingOpenai(false);
        toast.error('Erro ao salvar configuração do agente de IA.');
      });
  };

  const handleOpenaiClearKey = () => {
    if (!openaiConfig.openai_configured && !openaiKeyDirty) return;
    const typedKey = (openaiConfig.openai_api_key || '').trim();
    const provider = openaiConfig.ai_provider || 'openai';
    const providerCfg = AI_PROVIDER_OPTIONS[provider] || AI_PROVIDER_OPTIONS.openai;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    // Se o usuário já digitou uma chave nova no campo, substitui a salva em vez de apagar tudo.
    if (openaiKeyDirty && typedKey) {
      if (!window.confirm('Substituir a chave salva pela chave do campo?')) {
        return;
      }
      setSavingOpenai(true);
      axios
        .patch(
          `/api/provedores/${provedorId}/`,
          {
            ai_provider: provider,
            openai_model: openaiConfig.openai_model || providerCfg.defaultModel,
            openai_api_key: typedKey,
            clear_openai_api_key: true,
          },
          { headers: { Authorization: `Token ${token}` } }
        )
        .then((res) => {
          setSavingOpenai(false);
          setOpenaiConfig({
            ai_provider: res.data?.ai_provider || provider,
            openai_api_key: res.data?.openai_api_key || typedKey,
            openai_model: res.data?.openai_model || openaiConfig.openai_model,
            openai_configured: Boolean(
              res.data?.openai_configured ?? Boolean(typedKey)
            ),
          });
          setOpenaiKeyDirty(false);
          toast.success('Chave antiga removida e nova chave salva.');
        })
        .catch(() => {
          setSavingOpenai(false);
          toast.error('Erro ao substituir a chave.');
        });
      return;
    }

    if (!window.confirm('Remover a chave de API salva? O agente de IA parará de responder.')) {
      return;
    }
    setSavingOpenai(true);
    axios
      .patch(
        `/api/provedores/${provedorId}/`,
        {
          ai_provider: provider,
          openai_model: openaiConfig.openai_model || providerCfg.defaultModel,
          clear_openai_api_key: true,
        },
        { headers: { Authorization: `Token ${token}` } }
      )
      .then((res) => {
        setSavingOpenai(false);
        setOpenaiConfig({
          ai_provider: res.data?.ai_provider || provider,
          openai_api_key: '',
          openai_model: res.data?.openai_model || openaiConfig.openai_model,
          openai_configured: Boolean(res.data?.openai_configured),
        });
        setOpenaiKeyDirty(false);
        toast.success('Chave removida.');
      })
      .catch(() => {
        setSavingOpenai(false);
        toast.error('Erro ao remover a chave.');
      });
  };

  const handleGenerateWebhookToken = () => {
    if (!provedorId) return;
    const msg = webhookDispatchToken
      ? 'Gerar um novo token invalida o anterior. Continuar?'
      : null;
    if (msg && !window.confirm(msg)) return;

    setGeneratingWebhookToken(true);
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios
      .post(`/api/provedores/${provedorId}/generate-webhook-dispatch-token/`, {}, {
        headers: { Authorization: `Token ${token}` },
      })
      .then((res) => {
        if (res.data?.success) {
          setWebhookDispatchToken(res.data.webhook_dispatch_token || '');
          toast.success('Token de webhook gerado com sucesso.');
        }
      })
      .catch((err) => {
        toast.apiError(err, 'Erro ao gerar token de webhook.');
      })
      .finally(() => setGeneratingWebhookToken(false));
  };

  const handleCopyWebhookToken = async () => {
    if (!webhookDispatchToken) return;
    try {
      await navigator.clipboard.writeText(webhookDispatchToken);
    } catch {
      const el = document.createElement('textarea');
      el.value = webhookDispatchToken;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setWebhookTokenCopied(true);
    setTimeout(() => setWebhookTokenCopied(false), 2500);
  };

  const handleSgpSave = (e) => {
    e.preventDefault();
    setSaving(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios.patch(`/api/provedores/${provedorId}/`, sgp, {
      headers: { Authorization: `Token ${token}` }
    })
      .then(() => {
        setSaving(false);
        toast.success('Configurações salvas com sucesso!');
      })
      .catch(() => {
        setSaving(false);
        toast.error('Erro ao salvar configurações!');
      });
  };

  const handleAcsChange = (e) => {
    const { name, value } = e.target;
    setAcs((prev) => ({ ...prev, [name]: value }));
  };

  const handleAcsSave = (e) => {
    e.preventDefault();
    setSavingAcs(true);
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    axios
      .patch(`/api/provedores/${provedorId}/`, acs, {
        headers: { Authorization: `Token ${token}` },
      })
      .then((res) => {
        setSavingAcs(false);
        setAcs({
          acs_url: res.data?.acs_url || acs.acs_url || '',
          acs_token: res.data?.acs_token || acs.acs_token || '',
        });
        toast.success('Configurações do ACS salvas com sucesso!');
      })
      .catch(() => {
        setSavingAcs(false);
        toast.error('Erro ao salvar configurações do ACS!');
      });
  };

  const handleCheckStatus = async (canalId) => {
    try {
      setLoading(true);
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.post(buildApiPath(`/api/whatsapp/session/status/${canalId}/`), {}, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.data.success) {
        setStatusData(response.data);
        setShowStatusModal(true);
      } else {
        pushToast({ show: true, message: response.data.error || 'Erro ao verificar status', type: 'error' });
      }
    } catch (error) {
      pushToast({ show: true, message: 'Erro ao verificar status da sessão WhatsApp (Uazapi)', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteInstance = (channel) => {
    // Evitar múltiplas deleções
    if (deletingChannelId === channel.id) {
      return;
    }

    if (!confirm(t('confirmar_deletar_canal') || `Tem certeza que deseja deletar o canal ${channel.nome || channel.tipo}?`)) {
      return;
    }

    setDeletingChannelId(channel.id);
    const token = localStorage.getItem('token');

    axios.delete(`/api/canais/${channel.id}/`, {
      headers: { Authorization: `Token ${token}` }
    })
      .then(() => {
        setChannels(channels => channels.filter(c => c.id !== channel.id));
        pushToast({ show: true, message: t('canal_deletado_sucesso') || 'Canal deletado com sucesso', type: 'deleted' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'success' }), 3000);
        setDeletingChannelId(null);
      })
      .catch((error) => {
        setDeletingChannelId(null);
        const errorMsg = error.response?.status === 404
          ? 'Canal já foi deletado'
          : (t('erro_deletar_canal') || 'Erro ao deletar canal');
        pushToast({ show: true, message: errorMsg, type: 'error' });
        setTimeout(() => pushToast({ show: false, message: '', type: 'error' }), 3000);
      });
  };

  const tiposConfigurados = channels.map(c => c.tipo);

  const showChannels = mode === 'channels' || mode === 'full';
  const showOpenai = mode === 'ai' || mode === 'settings' || mode === 'full';
  const showErp = mode === 'erp' || mode === 'settings' || mode === 'full';
  const showAcs = mode === 'acs' || mode === 'settings' || mode === 'full';
  const showAsaas =
    (mode === 'asaas' || mode === 'settings' || mode === 'full') &&
    providerConfig?.agent_mode === 'support';

  return (
    <div className={mode === 'channels' || mode === 'ai' || mode === 'erp' || mode === 'acs' || mode === 'asaas' ? 'p-0' : 'p-8'}>
      {/* LISTAGEM DE CANAIS CONFIGURADOS */}
      {showChannels && (
        <>
          {providerConfig?.agent_mode === 'support' && (
            <div className="mb-8 rounded-xl border border-violet-500/30 bg-violet-500/10 p-5">
              <h3 className="text-base font-semibold text-foreground mb-1">
                Notificação de transferências (Modo Suporte)
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                Quando a IA transferir um cliente para qualquer equipe (suporte, vendas, financeiro, etc.),
                ela envia um resumo para este WhatsApp. Use DDI + DDD + número (ex.: 5599999999999).
              </p>
              <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-end">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Número WhatsApp para notificar
                  </label>
                  <input
                    type="tel"
                    value={supportNotifyPhone}
                    onChange={(e) => setSupportNotifyPhone(e.target.value)}
                    placeholder="5599999999999"
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground"
                  />
                </div>
                <button
                  type="button"
                  onClick={saveSupportNotifyPhone}
                  disabled={savingSupportNotify}
                  className="bg-primary text-primary-foreground px-5 py-2 rounded-lg text-sm font-semibold disabled:opacity-60"
                >
                  {savingSupportNotify ? 'Salvando...' : 'Salvar número'}
                </button>
              </div>
              {supportNotifyMsg && (
                <p className="text-xs text-muted-foreground mt-2">{supportNotifyMsg}</p>
              )}
            </div>
          )}
          <div className={`flex items-center ${mode === 'channels' ? 'justify-end' : 'justify-between'} mb-10`}>
            {mode !== 'channels' && <h2 className="text-3xl font-bold text-foreground ml-2">{t('canais_configurados')}</h2>}
            <button
              onClick={handleAdd}
              className="bg-primary text-primary-foreground px-4 py-2 rounded-full text-sm font-bold flex items-center gap-2 shadow"
            >
              <Plus className="w-5 h-5" /> {t('adicionar_canal')}
            </button>
          </div>
          {loading && <div className="text-muted-foreground">{t('carregando_canais')}</div>}
          {error && <div className="text-destructive">{error}</div>}
          {!loading && !error && channels.length === 0 && (
            <div className="text-muted-foreground">{t('nenhum_canal_configurado')}</div>
          )}
          {/* GRID DOS CANAIS */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mb-10">
            {channels.map(channel => (
              <div key={channel.id} className="relative">
                <ChannelCard
                  channel={channel}
                  onConnect={handleConnect}
                  onDelete={handleDelete}
                  onDisconnect={handleDisconnect}
                  onCheckStatus={handleCheckStatus}
                  onDeleteInstance={handleDeleteInstance}
                  onToggleIA={handleToggleIA}
                  onVoiceCallsSetup={handleVoiceCallsSetup}
                  onVoiceCallsDisable={handleVoiceCallsDisable}
                  voiceCallsBusyId={voiceCallsBusyId}
                  deletingChannelId={deletingChannelId}
                  isProcessing={processingChannels.has(channel.id)}
                  providerConfig={providerConfig}
                  onEditName={handleEditName}
                  t={t}
                />
                {/* QR Code para WhatsApp */}
                {connectingId === channel.id && qrCardLoading && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/70 rounded-xl z-10">
                    <span className="text-white">{t('gerando_qr_code')}</span>
                  </div>
                )}
                {connectingId === channel.id && qrCard && (
                  <div className="fixed inset-0 flex items-center justify-center z-50 bg-black/80">
                    <div className="flex flex-col items-center w-full max-w-md bg-[#23243a] rounded-xl shadow-2xl p-6">
                      <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-4 mb-4 text-yellow-900 shadow-lg w-80 text-sm text-left">
                        <b className="block mb-1">{t('antes_conectar_whatsapp')}</b>
                        {t('evitar_bloqueios')}<br />
                        {t('comece_mensagens_manuais')}<br /><br />
                        <span className="inline-block mb-1">📌 <b>{t('dica')}</b></span>
                        <span>
                          {t('use_whatsapp_organico')}
                        </span>
                      </div>
                      {/* QR Code ou Código de Pareamento */}
                      {typeof qrCard === 'object' && (qrCard.qrcode || qrCard.paircode) ? (
                        <>
                          {qrCard.qrcode && (
                            <img src={qrCard.qrcode} alt="QR Code" className="w-48 h-48 mx-auto" />
                          )}
                          {qrCard.paircode && (
                            <div className="text-center mt-4">
                              <div className="bg-green-50 border border-green-300 rounded-lg p-6 mb-2 text-green-900 shadow-lg w-80 mx-auto">
                                <div className="text-2xl font-bold mb-2">{qrCard.paircode}</div>
                                <div className="text-sm">
                                  {t('digite_codigo_whatsapp')}<br />
                                  {t('configuracoes_aparelhos_conectados')}
                                </div>
                              </div>
                            </div>
                          )}
                        </>
                      ) : qrCard.startsWith('data:image') || qrCard.startsWith('http') ? (
                        <img src={qrCard} alt="QR Code" className="w-48 h-48" />
                      ) : (
                        <img src={`data:image/png;base64,${qrCard}`} alt="QR Code" className="w-48 h-48" />
                      )}
                      <span className="text-green-400 mt-2">
                        {typeof qrCard === 'object' && qrCard.paircode ? t('digite_codigo_ou_escaneie') : t('escanear_qr_code')}
                      </span>
                      <button onClick={() => setConnectingId(null)} className="mt-4 px-4 py-2 rounded bg-gray-700 text-white">{t('fechar')}</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {voiceCallsModal && (
            <div className="fixed inset-0 z-[120] flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
              <div className="flex w-full max-w-md flex-col items-center rounded-xl border border-border bg-card p-6 text-foreground shadow-2xl">
                <h3 className="mb-1 text-base font-semibold text-foreground">Conectar ligações</h3>
                <p className="mb-4 text-center text-xs text-muted-foreground">
                  No celular: WhatsApp → Aparelhos conectados → Conectar aparelho.
                  As mensagens continuam pela API oficial.
                </p>
                {voiceCallsModal.qrcode ? (
                  voiceCallsModal.qrcode.startsWith('data:') || voiceCallsModal.qrcode.startsWith('http') ? (
                    <img src={voiceCallsModal.qrcode} alt="QR Code ligações" className="h-52 w-52 rounded-lg border border-border bg-white p-2" />
                  ) : (
                    <img
                      src={`data:image/png;base64,${voiceCallsModal.qrcode}`}
                      alt="QR Code ligações"
                      className="h-52 w-52 rounded-lg border border-border bg-white p-2"
                    />
                  )
                ) : (
                  <div className="flex h-52 w-52 items-center justify-center rounded-lg border border-dashed border-border bg-muted/40 text-sm text-muted-foreground">
                    Gerando QR Code...
                  </div>
                )}
                <p className="mt-3 text-xs font-medium text-primary">Aguardando pareamento...</p>
                <button
                  type="button"
                  onClick={() => {
                    stopVoiceCallsPolling();
                    setVoiceCallsModal(null);
                  }}
                  className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow transition hover:bg-primary/90"
                >
                  Fechar
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* MODAL DE ADICIONAR CANAL */}
      {showModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className={`bg-card rounded-xl shadow-lg border border-border w-full relative ${selectedType === 'telegram' ? 'max-w-lg p-6' : 'max-w-md p-8'}`}>
            {/* Botão fechar no topo direito */}
            <button onClick={() => setShowModal(false)} className="absolute top-4 right-4 p-2 rounded hover:bg-muted transition" title="Fechar">
              <XCircle className="w-5 h-5 text-destructive" />
            </button>
            <h3 className="text-xl font-bold text-foreground mb-6">{t('adicionar_canal')}</h3>
            {!selectedType ? (
              <div className="flex flex-col gap-2.5">
                <p className="text-sm text-muted-foreground mb-1">
                  Selecione o tipo de canal que deseja conectar:
                </p>
                {availableTypes.map((opt) => (
                  <button
                    key={opt.tipo}
                    type="button"
                    disabled={adding}
                    onClick={() => handleSelectType(opt.tipo)}
                    className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border border-border bg-[#1a1b2e] text-white hover:bg-[#2d2e4a] hover:border-primary/30 transition ${adding ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <div className="w-9 h-9 rounded-lg bg-muted border border-border flex items-center justify-center shrink-0">
                      {opt.tipo === 'app_mobile' ? (
                        <Smartphone className="w-5 h-5 text-orange-500" />
                      ) : CHANNEL_TYPE_ICONS[opt.tipo] ? (
                        <img
                          src={CHANNEL_TYPE_ICONS[opt.tipo]}
                          alt=""
                          className="w-5 h-5 object-contain"
                        />
                      ) : (
                        <Globe className="w-5 h-5 text-primary" />
                      )}
                    </div>
                    <span className="flex-1 text-left font-semibold">{opt.label}</span>
                    <span className="text-xs text-muted-foreground bg-muted px-2.5 py-0.5 rounded-full shrink-0">
                      {t('disponivel')}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-5">
                <button
                  type="button"
                  onClick={() => setSelectedType(null)}
                  className="text-xs text-muted-foreground hover:text-foreground self-start -mt-2 transition"
                >
                  ← Voltar aos canais
                </button>
                {selectedType === 'whatsapp' || selectedType === 'whatsapp_session' || selectedType === 'whatsapp_oficial' ? (
                  <div className="flex flex-col gap-5">
                    <AddChannelModalHeader
                      image={whatsappIcon}
                      title={WHATSAPP_TYPE_META[selectedType]?.title || 'WhatsApp'}
                      subtitle={WHATSAPP_TYPE_META[selectedType]?.subtitle}
                    />
                    <AddChannelInfoBox
                      description={WHATSAPP_TYPE_META[selectedType]?.description}
                      bullets={WHATSAPP_TYPE_META[selectedType]?.bullets || []}
                    />
                    <AddChannelField label={t('nome_instancia')}>
                      <input
                        type="text"
                        id="instanceName"
                        value={instanceName}
                        onChange={(e) => setInstanceName(e.target.value)}
                        className={MODAL_INPUT_CLASS}
                        placeholder="Ex: Meu WhatsApp"
                        required
                      />
                    </AddChannelField>
                    <AddChannelFooter
                      cancelLabel={t('cancelar')}
                      onCancel={() => setShowModal(false)}
                      submitLabel={t('adicionar_canal_btn')}
                      loadingLabel={t('adicionando')}
                      onSubmit={handleSaveWhatsapp}
                      disabled={!instanceName}
                      loading={adding}
                    />
                  </div>
                ) : selectedType === 'telegram' ? (
                  <div className="flex flex-col gap-3">
                    <AddChannelModalHeader
                      image={telegramIcon}
                      title="Telegram"
                      subtitle="API oficial"
                      compact
                    />
                    <AddChannelInfoBox
                      compact
                      description={
                        <>
                          Credenciais em{' '}
                          <a
                            href="https://my.telegram.org/auth"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline underline-offset-2"
                          >
                            my.telegram.org
                          </a>
                          {' '}→ API development tools.
                        </>
                      }
                    />
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-3">
                      <AddChannelField label="App API ID *" compact>
                        <input
                          type="text"
                          id="api_id"
                          value={formData.api_id || ''}
                          onChange={(e) => setFormData((prev) => ({ ...prev, api_id: e.target.value }))}
                          className={MODAL_INPUT_COMPACT_CLASS}
                          placeholder="28698952"
                        />
                      </AddChannelField>
                      <AddChannelField label="App Title *" compact>
                        <input
                          type="text"
                          id="app_title"
                          value={formData.app_title || ''}
                          onChange={(e) => setFormData((prev) => ({ ...prev, app_title: e.target.value }))}
                          className={MODAL_INPUT_COMPACT_CLASS}
                          placeholder="app_niochat"
                        />
                      </AddChannelField>
                      <div className="sm:col-span-2">
                        <AddChannelField label="App API Hash *" compact>
                          <input
                            type="text"
                            id="api_hash"
                            value={formData.api_hash || ''}
                            onChange={(e) => setFormData((prev) => ({ ...prev, api_hash: e.target.value }))}
                            className={MODAL_INPUT_COMPACT_CLASS}
                            placeholder="aca543fd24a822a09b90c2226328411d"
                          />
                        </AddChannelField>
                      </div>
                      <div className="sm:col-span-2">
                        <AddChannelField
                          label="Phone Number *"
                          compact
                          hint={<>Formato internacional: +5511999999999</>}
                        >
                          <input
                            type="tel"
                            id="phone_number"
                            value={formData.phone_number || ''}
                            onChange={(e) => setFormData((prev) => ({ ...prev, phone_number: e.target.value }))}
                            className={MODAL_INPUT_COMPACT_CLASS}
                            placeholder="+5511999999999"
                          />
                        </AddChannelField>
                      </div>
                    </div>
                    <AddChannelFooter
                      cancelLabel={t('cancelar')}
                      onCancel={() => setShowModal(false)}
                      submitLabel="Adicionar Canal"
                      loadingLabel="Enviando código..."
                      onSubmit={handleAddOtherChannel}
                      disabled={
                        !formData.api_id ||
                        !formData.api_hash ||
                        !formData.app_title ||
                        !formData.phone_number
                      }
                      loading={adding}
                    />
                  </div>
                ) : selectedType === 'instagram' ? (
                  <div className="flex flex-col gap-5">
                    <AddChannelModalHeader
                      image={instagramIcon}
                      title="Instagram Business Login"
                      subtitle="Mensagens diretas no painel"
                    />
                    <AddChannelInfoBox
                      description="Conecte uma conta profissional do Instagram para receber e responder mensagens diretas. Após adicionar o canal, use o botão Conectar na lista."
                      bullets={[
                        'Conta Instagram Business ou Creator vinculada à Meta',
                        'Login seguro — o token é salvo automaticamente',
                      ]}
                    />
                    <AddChannelField label={t('nome_canal')}>
                      <input
                        type="text"
                        id="instagram_nome"
                        value={formData.nome}
                        onChange={(e) => setFormData((prev) => ({ ...prev, nome: e.target.value }))}
                        className={MODAL_INPUT_CLASS}
                        placeholder="Ex: Instagram Suporte"
                      />
                    </AddChannelField>
                    <AddChannelFooter
                      cancelLabel={t('cancelar')}
                      onCancel={() => setShowModal(false)}
                      submitLabel="Adicionar Canal"
                      loadingLabel="Adicionando..."
                      onSubmit={handleAddOtherChannel}
                      loading={adding}
                    />
                  </div>
                ) : selectedType === 'app_mobile' ? (
                  <div className="flex flex-col gap-5">
                    <AddChannelModalHeader
                      icon={Smartphone}
                      iconClassName="text-orange-500"
                      title="App Mobile"
                      subtitle="Chat do app do cliente no painel"
                    />
                    <AddChannelInfoBox
                      compact
                      description="Cole o token sk_live_ e escolha a equipe que receberá os atendimentos do app na aba Espera."
                    />
                    <AddChannelField label={t('nome_canal')}>
                      <input
                        type="text"
                        id="app_mobile_nome"
                        value={formData.nome}
                        onChange={(e) => setFormData((prev) => ({ ...prev, nome: e.target.value }))}
                        className={MODAL_INPUT_CLASS}
                        placeholder="Ex: App Mobile"
                      />
                    </AddChannelField>
                    <AddChannelField label="Token do app (sk_live_)">
                      <input
                        type="password"
                        id="app_mobile_token"
                        autoComplete="off"
                        value={formData.app_token || ''}
                        onChange={(e) => setFormData((prev) => ({ ...prev, app_token: e.target.value }))}
                        className={MODAL_INPUT_CLASS}
                        placeholder="sk_live_..."
                      />
                      {channels.some((c) => c.tipo === 'app_mobile') && (
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Deixe em branco para manter o token atual ao alterar só a equipe.
                        </p>
                      )}
                    </AddChannelField>
                    <AddChannelField label="Equipe na fila Espera (ID)">
                      <select
                        id="app_mobile_team"
                        value={formData.app_default_team_id || ''}
                        onChange={(e) =>
                          setFormData((prev) => ({ ...prev, app_default_team_id: e.target.value }))
                        }
                        className={MODAL_INPUT_CLASS}
                      >
                        <option value="">Fila geral (todas as equipes)</option>
                        {appMobileTeams.map((team) => (
                          <option key={team.id} value={String(team.id)}>
                            #{team.id} — {team.name}
                          </option>
                        ))}
                      </select>
                      <p className="text-[11px] text-muted-foreground mt-1">
                        Os IDs das equipes aparecem em Configurações → Equipes (ex.: #20 ATENDIMENTO).
                      </p>
                    </AddChannelField>
                    <AddChannelFooter
                      cancelLabel={t('cancelar')}
                      onCancel={() => setShowModal(false)}
                      submitLabel={
                        channels.some((c) => c.tipo === 'app_mobile')
                          ? 'Salvar'
                          : 'Conectar App Mobile'
                      }
                      loadingLabel="Validando..."
                      onSubmit={handleAddOtherChannel}
                      disabled={
                        !channels.some((c) => c.tipo === 'app_mobile')
                        && !(formData.app_token || '').trim()
                      }
                      loading={adding}
                    />
                  </div>
                ) : selectedType === 'email' ? (
                  <div className="flex flex-col gap-5">
                    <AddChannelModalHeader
                      image={gmailIcon}
                      title="E-mail"
                      subtitle="Canal de atendimento por e-mail"
                    />
                    <AddChannelInfoBox
                      description="Cadastre um canal de e-mail para centralizar conversas. Nome é obrigatório; endereço e URL são opcionais."
                      bullets={[
                        'Use um nome claro para a equipe identificar o canal',
                        'E-mail e URL podem ser preenchidos depois, se preferir',
                      ]}
                    />
                    <AddChannelField label={t('nome_canal')}>
                      <input
                        type="text"
                        id="nome"
                        value={formData.nome}
                        onChange={(e) => setFormData((prev) => ({ ...prev, nome: e.target.value }))}
                        className={MODAL_INPUT_CLASS}
                        placeholder="Ex: E-mail Suporte"
                        required
                      />
                    </AddChannelField>
                    <AddChannelField label={t('email_opcional')}>
                      <input
                        type="email"
                        id="email"
                        value={formData.email}
                        onChange={(e) => setFormData((prev) => ({ ...prev, email: e.target.value }))}
                        className={MODAL_INPUT_CLASS}
                        placeholder="exemplo@email.com"
                      />
                    </AddChannelField>
                    <AddChannelField label={t('url_opcional')}>
                      <input
                        type="url"
                        id="url"
                        value={formData.url}
                        onChange={(e) => setFormData((prev) => ({ ...prev, url: e.target.value }))}
                        className={MODAL_INPUT_CLASS}
                        placeholder="https://exemplo.com"
                      />
                    </AddChannelField>
                    <AddChannelFooter
                      cancelLabel={t('cancelar')}
                      onCancel={() => setShowModal(false)}
                      submitLabel={t('adicionar_canal_btn')}
                      loadingLabel={t('adicionando')}
                      onSubmit={handleAddOtherChannel}
                      loading={adding}
                    />
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODAL DE EDIÇÃO DE NOME DO CANAL */}
      {isEditingName && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-card p-8 rounded-xl shadow-lg border border-border w-full max-w-md relative">
            <button onClick={() => { setIsEditingName(false); setChannelToEdit(null); }} className="absolute top-4 right-4 p-2 rounded hover:bg-muted transition" title="Fechar">
              <XCircle className="w-5 h-5 text-destructive" />
            </button>
            <h3 className="text-xl font-bold text-foreground mb-6">Editar Nome do Canal</h3>
            <div className="flex flex-col gap-5">
              <AddChannelModalHeader
                icon={Edit2}
                title="Renomear canal"
                subtitle="Nome exibido no painel e relatórios"
              />
              <AddChannelField label="Novo Nome">
                <input
                  type="text"
                  id="editChannelName"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className={MODAL_INPUT_CLASS}
                  placeholder="Ex: WhatsApp Suporte"
                  required
                />
              </AddChannelField>
              <AddChannelFooter
                cancelLabel={t('cancelar')}
                onCancel={() => { setIsEditingName(false); setChannelToEdit(null); }}
                submitLabel="Salvar Alteração"
                loadingLabel="Salvando..."
                onSubmit={handleSaveName}
                disabled={!newName.trim()}
                loading={savingName}
              />
            </div>
          </div>
        </div>
      )}

      {/* MODAL "COMO DESEJA CONECTAR?" */}
      {showPairingMenu && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-card p-8 rounded-xl shadow-lg border border-border w-full max-w-md relative">
            {/* Botão fechar no topo direito */}
            <button onClick={() => setShowPairingMenu(false)} className="absolute top-4 right-4 p-2 rounded hover:bg-muted transition" title="Fechar">
              <XCircle className="w-5 h-5 text-destructive" />
            </button>
            <h3 className="text-xl font-bold text-foreground mb-6">{t('como_deseja_conectar')}</h3>
            <AddChannelInfoBox
              description="Escolha como deseja parear o WhatsApp com o painel."
              bullets={[
                'QR Code: escaneie com o celular em poucos segundos',
                'Código de pareamento: digite o código nas configurações do WhatsApp',
              ]}
            />
            <div className="flex flex-col gap-2.5 mt-5">
              <button
                type="button"
                onClick={() => handlePairingMethod('qrcode')}
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-3 rounded-lg text-base font-semibold shadow transition w-full"
              >
                QR Code
              </button>
              <button
                type="button"
                onClick={() => handlePairingMethod('paircode')}
                className="bg-gray-600 hover:bg-gray-700 text-white px-6 py-3 rounded-lg text-base font-semibold shadow transition w-full"
              >
                {t('codigo_pareamento')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL DE INPUT DE TELEFONE PARA PAREAMENTO */}
      {showPhoneInput && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-card p-8 rounded-xl shadow-lg border border-border w-full max-w-md relative">
            {/* Botão fechar no topo direito */}
            <button onClick={() => { setShowPhoneInput(false); setPairingResult(null); }} className="absolute top-4 right-4 p-2 rounded hover:bg-muted transition" title="Fechar">
              <XCircle className="w-5 h-5 text-destructive" />
            </button>
            <h3 className="text-xl font-bold text-foreground mb-6">{t('digite_numero_telefone')}</h3>
            <input
              type="text"
              value={pairingPhone}
              onChange={e => setPairingPhone(e.target.value.replace(/\D/g, ''))}
              placeholder="Ex: 11999999999"
              className="w-full px-4 py-2 rounded bg-background text-foreground focus:outline-none border border-border mb-4"
              maxLength={13}
            />
            <button
              onClick={handlePairingPhoneSubmit}
              className="bg-gradient-to-r from-green-500 to-green-700 hover:from-green-600 hover:to-green-800 text-white px-6 py-3 rounded-lg text-lg font-semibold shadow transition w-full mb-2"
              disabled={!pairingPhone || pairingLoading}
            >
              {pairingLoading ? t('enviando') : t('obter_codigo_pareamento')}
            </button>
            {pairingResult && (
              <div className="mt-4">
                <div className="bg-green-50 border-2 border-green-300 rounded-lg p-6 mb-2 text-green-900 shadow-lg">
                  <div className="text-3xl font-bold mb-2 tracking-wider">{pairingResult}</div>
                  <div className="text-sm text-green-700">
                    {t('digite_codigo_whatsapp')}<br />
                    {t('configuracoes_aparelhos_conectados')}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODAL DE SUCESSO */}
      {showAddChannelSuccess && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-card p-8 rounded-xl shadow-lg border border-border w-full max-w-md text-center">
            <h3 className="text-xl font-bold text-foreground mb-4">{t('sucesso')}</h3>
            <p className="text-muted-foreground mb-6">{t('canal_adicionado_sucesso')}</p>
            <button
              onClick={() => setShowAddChannelSuccess(false)}
              className="bg-gradient-to-r from-orange-500 to-yellow-500 hover:from-orange-600 hover:to-yellow-600 text-white px-4 py-2 rounded-lg text-sm font-semibold shadow-lg hover:shadow-xl transition-all duration-200"
            >
              {t('fechar')}
            </button>
          </div>
        </div>
      )}

      {/* MODAL DE VERIFICAÇÃO DE CÓDIGO TELEGRAM */}
      {showTelegramCodeModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-card p-8 rounded-xl shadow-lg border border-border w-full max-w-md">
            <h3 className="text-xl font-bold text-foreground mb-4">Código de Verificação Telegram</h3>
            <p className="text-muted-foreground mb-2">
              Um código de verificação foi enviado para o seu número do Telegram:
            </p>
            <p className="text-blue-500 font-bold mb-4">
              {telegramChannelData?.telegram_code_sent?.phone || telegramChannelData?.phone_number}
            </p>
            <p className="text-muted-foreground mb-4">
              Abra o Telegram e copie o código que você recebeu. Digite-o abaixo para completar a autenticação:
            </p>

            <div className="flex flex-col mb-6">
              <label htmlFor="telegramCode" className="text-sm font-semibold text-white mb-2">
                Código de Verificação (5 dígitos)
              </label>
              <input
                type="text"
                id="telegramCode"
                value={telegramCode}
                onChange={(e) => {
                  const value = e.target.value.replace(/\D/g, '');
                  setTelegramCode(value);
                }}
                className="bg-[#1a1b2e] border border-[#35365a] text-white px-4 py-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-center text-2xl tracking-wider font-mono"
                placeholder="●●●●●"
                maxLength={5}
                autoFocus
                onKeyPress={(e) => {
                  if (e.key === 'Enter' && telegramCode.length === 5) {
                    handleVerifyTelegramCode();
                  }
                }}
              />
              <p className="text-xs text-gray-400 mt-2 text-center">
                Pressione Enter para verificar
              </p>
            </div>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowTelegramCodeModal(false);
                  setTelegramCode('');
                  setTelegramChannelData(null);
                }}
                disabled={verifyingCode}
                className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-semibold shadow transition disabled:opacity-50"
              >
                {t('cancelar')}
              </button>
              <button
                onClick={handleVerifyTelegramCode}
                disabled={verifyingCode || !telegramCode}
                className="bg-gradient-to-r from-blue-500 to-blue-700 hover:from-blue-600 hover:to-blue-800 text-white px-4 py-2 rounded-lg text-sm font-semibold shadow transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {verifyingCode ? 'Verificando...' : 'Verificar Código'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Agente de IA — provedor e chave próprios */}
      {showOpenai && (() => {
        const providerKey = openaiConfig.ai_provider || 'openai';
        const providerCfg = AI_PROVIDER_OPTIONS[providerKey] || AI_PROVIDER_OPTIONS.openai;
        const modelOptions = providerCfg.models;
        const selectedModel = modelOptions.some((m) => m.value === openaiConfig.openai_model)
          ? openaiConfig.openai_model
          : providerCfg.defaultModel;

        return (
        <div className={`${mode === 'ai' ? 'mt-0' : 'mt-10'} p-8 bg-card rounded-xl shadow-lg border border-border`}>
          {mode !== 'ai' && (
            <h3 className="text-xl font-bold text-foreground mb-2">Agente de IA</h3>
          )}
          <p className="text-sm text-muted-foreground mb-6">
            Escolha o provedor de IA e use a sua própria chave. O uso é cobrado na sua conta —
            o NioHub não compartilha chave global.
          </p>
          <form onSubmit={handleOpenaiSave} className="flex flex-col gap-4">
            <div className="flex flex-col">
              <label htmlFor="aiProvider" className="text-sm font-semibold text-foreground mb-1">
                Provedor de IA
              </label>
              <select
                id="aiProvider"
                name="ai_provider"
                value={providerKey}
                onChange={handleOpenaiChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="openai">OpenAI</option>
                <option value="gemini">Gemini (Google)</option>
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>
            <div className="flex flex-col">
              <label htmlFor="openaiApiKey" className="text-sm font-semibold text-foreground mb-1">
                Chave da API ({providerCfg.label})
              </label>
              <input
                type="text"
                id="openaiApiKey"
                name="openai_api_key"
                value={openaiConfig.openai_api_key}
                onChange={handleOpenaiChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                placeholder={providerCfg.keyHint}
                autoComplete="off"
                spellCheck={false}
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Obtenha em{' '}
                <a
                  href={providerCfg.docsUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline"
                >
                  {providerCfg.docsLabel}
                </a>
                .
                {providerKey === 'gemini' && (
                  <> Aceita chaves AIza… ou AQ… do AI Studio.</>
                )}
                {providerKey !== 'openai' && (
                  <> Transcrição de áudio funciona apenas com OpenAI.</>
                )}
              </p>
              {(openaiConfig.openai_configured || openaiKeyDirty) ? (
                <button
                  type="button"
                  onClick={handleOpenaiClearKey}
                  disabled={savingOpenai}
                  className="mt-2 self-start text-xs font-semibold text-red-400 hover:text-red-300 disabled:opacity-50"
                >
                  {openaiKeyDirty && (openaiConfig.openai_api_key || '').trim()
                    ? 'Substituir chave salva'
                    : 'Remover chave salva'}
                </button>
              ) : null}
            </div>
            <div className="flex flex-col">
              <label htmlFor="openaiModel" className="text-sm font-semibold text-foreground mb-1">
                Modelo
              </label>
              <select
                id="openaiModel"
                name="openai_model"
                value={selectedModel}
                onChange={handleOpenaiChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {modelOptions.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span
                className={`inline-flex h-2.5 w-2.5 rounded-full ${
                  openaiConfig.openai_configured ? 'bg-emerald-500' : 'bg-amber-500'
                }`}
              />
              <span className="text-muted-foreground">
                {openaiConfig.openai_configured
                  ? `Agente ativo com ${providerCfg.label}`
                  : 'Sem chave — o agente de IA não responde até configurar'}
              </span>
            </div>
            <button
              type="submit"
              disabled={savingOpenai}
              className="w-full bg-[#10b981] hover:bg-[#059669] text-white py-2.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg"
            >
              {savingOpenai ? 'Salvando…' : 'Salvar agente de IA'}
            </button>
          </form>
        </div>
        );
      })()}

      {/* Integração externa + webhook de disparos */}
      {showErp && (
        <div className={`${mode === 'erp' ? 'mt-0' : 'mt-10'} p-8 bg-card rounded-xl shadow-lg border border-border`}>
          {mode !== 'erp' && (
            <h3 className="text-xl font-bold text-foreground mb-6">Configurações de integração</h3>
          )}
          {mode === 'erp' && (
            <h3 className="text-xl font-bold text-foreground mb-6">Dados de conexão</h3>
          )}
          <form onSubmit={handleSgpSave} className="flex flex-col gap-4">
            <div className="flex flex-col">
              <label htmlFor="erpSystem" className="text-sm font-semibold text-foreground mb-1">
                Sistema ERP
              </label>
              <select
                id="erpSystem"
                name="erp_system"
                value={sgp.erp_system || 'sgp'}
                onChange={handleSgpChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {ERP_SYSTEM_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col">
              <label htmlFor="sgpUrl" className="text-sm font-semibold text-foreground mb-1">URL</label>
              <input
                type="url"
                id="sgpUrl"
                name="sgp_url"
                value={sgp.sgp_url}
                onChange={handleSgpChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="https://api.exemplo.com.br"
                required
              />
            </div>
            <div className="flex flex-col">
              <label htmlFor="sgpToken" className="text-sm font-semibold text-foreground mb-1">Token</label>
              <input
                type="text"
                id="sgpToken"
                name="sgp_token"
                value={sgp.sgp_token}
                onChange={handleSgpChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Seu token de acesso"
                required
              />
            </div>
            <div className="flex flex-col">
              <label htmlFor="sgpApp" className="text-sm font-semibold text-foreground mb-1">App</label>
              <input
                type="text"
                id="sgpApp"
                name="sgp_app"
                value={sgp.sgp_app}
                onChange={handleSgpChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="Ex: my-app-name"
                required
              />
            </div>
            {(sgp.erp_system || 'sgp') === 'sgp' && (
              <>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm font-semibold text-foreground">
                    Consulta de viabilidade pela IA
                  </span>
                  <label className="relative inline-flex items-center cursor-pointer shrink-0">
                    <input
                      type="checkbox"
                      name="sgp_viabilidade_ativa"
                      checked={sgp.sgp_viabilidade_ativa ?? true}
                      onChange={handleSgpToggleChange}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-red-500 peer-checked:bg-[#10b981] rounded-full transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-5"></div>
                  </label>
                </div>
                {(sgp.sgp_viabilidade_ativa ?? true) && (
                  <div className="flex flex-col sm:flex-row gap-4">
                    <div className="flex flex-col flex-1">
                      <label htmlFor="sgpViabilidadeGateway" className="text-sm font-semibold text-foreground mb-1">
                        ID do Gateway (mapas)
                      </label>
                      <input
                        type="number"
                        id="sgpViabilidadeGateway"
                        name="sgp_viabilidade_gateway"
                        value={sgp.sgp_viabilidade_gateway ?? ''}
                        onChange={handleSgpChange}
                        className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                        placeholder="Ex: 1"
                        min="1"
                        step="1"
                      />
                      <span className="text-xs text-muted-foreground mt-1">
                        ID da gateway de mapas para consulta por coordenadas
                      </span>
                    </div>
                    <div className="flex flex-col flex-1">
                      <label htmlFor="sgpViabilidadeRaio" className="text-sm font-semibold text-foreground mb-1">
                        Raio máximo (metros)
                      </label>
                      <input
                        type="number"
                        id="sgpViabilidadeRaio"
                        name="sgp_viabilidade_raio"
                        value={sgp.sgp_viabilidade_raio ?? ''}
                        onChange={handleSgpChange}
                        className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                        placeholder="Ex: 300"
                        min="1"
                        step="1"
                      />
                      <span className="text-xs text-muted-foreground mt-1">
                        Distância máxima aceita para instalação (ex.: 300)
                      </span>
                    </div>
                  </div>
                )}
              </>
            )}
            <button
              type="submit"
              disabled={saving}
              className="w-full bg-[#10b981] hover:bg-[#059669] text-white py-2.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg"
            >
              {saving ? t('salvando') : t('salvar')}
            </button>
          </form>

          <div className="mt-8 border-t border-border pt-6">
            <h4 className="text-base font-bold text-foreground mb-4">Webhook de disparos</h4>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col">
                <label className="text-sm font-semibold text-foreground mb-1">Seu Token</label>
                <input
                  type="text"
                  readOnly
                  value={webhookDispatchToken}
                  placeholder="Clique em Gerar token"
                  className="bg-background border border-border text-foreground px-3 py-2 rounded-lg font-mono text-xs opacity-90"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleGenerateWebhookToken}
                  disabled={generatingWebhookToken}
                  className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50"
                >
                  {generatingWebhookToken
                    ? 'Gerando…'
                    : webhookDispatchToken
                      ? 'Renovar token'
                      : 'Gerar token'}
                </button>
                <button
                  type="button"
                  onClick={handleCopyWebhookToken}
                  disabled={!webhookDispatchToken}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50"
                >
                  {webhookTokenCopied ? 'Copiado!' : 'Copiar token'}
                </button>
              </div>
            </div>
          </div>

        </div>
      )}

      {showAcs && (
        <div className={`${mode === 'acs' ? 'mt-0' : 'mt-10'} p-8 bg-card rounded-xl shadow-lg border border-border`}>
          <h3 className="text-xl font-bold text-foreground mb-2">Dados de conexão</h3>
          <p className="text-sm text-muted-foreground mb-6">
            Informe a URL base e o token Bearer gerados na tela de Integração do painel NIO HUB - ACS.
            Todas as rotas usam o header Authorization: Bearer token.
          </p>
          <form onSubmit={handleAcsSave} className="flex flex-col gap-4">
            <div className="flex flex-col">
              <label htmlFor="acsUrl" className="text-sm font-semibold text-foreground mb-1">
                URL
              </label>
              <input
                type="url"
                id="acsUrl"
                name="acs_url"
                value={acs.acs_url}
                onChange={handleAcsChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="https://acs.exemplo.com.br"
                required
              />
              <span className="text-xs text-muted-foreground mt-1">
                URL base da API (sem barra no final). Rotas: /api/integration/devices/.../wifi/ (com barra no final).
              </span>
            </div>
            <div className="flex flex-col">
              <label htmlFor="acsToken" className="text-sm font-semibold text-foreground mb-1">
                Token
              </label>
              <input
                type="password"
                id="acsToken"
                name="acs_token"
                value={acs.acs_token}
                onChange={handleAcsChange}
                className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                placeholder="Token Bearer da API"
                required
                autoComplete="off"
              />
            </div>
            <button
              type="submit"
              disabled={savingAcs}
              className="w-full bg-[#10b981] hover:bg-[#059669] text-white py-2.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg"
            >
              {savingAcs ? t('salvando') : t('salvar')}
            </button>
          </form>
        </div>
      )}

      {showAsaas && (
        <div className={`${mode === 'asaas' ? 'mt-0' : 'mt-10'} p-8 bg-card rounded-xl shadow-lg border border-border`}>
          <h3 className="text-xl font-bold text-foreground mb-2">API Asaas</h3>
          <p className="text-sm text-muted-foreground mb-6">
            Token usado pelo agente de suporte da plataforma para buscar e enviar faturas dos provedores
            (assinatura NioHub). Use o Access Token da conta Asaas de cobrança.
          </p>
          <form onSubmit={saveAsaasConfig} className="flex flex-col gap-4">
            <div className="flex flex-col">
              <label htmlFor="asaasAccessToken" className="text-sm font-semibold text-foreground mb-1">
                Token de API do Asaas
              </label>
              <div className="relative">
                <input
                  type={showAsaasToken ? 'text' : 'password'}
                  id="asaasAccessToken"
                  value={asaasToken}
                  onChange={(e) => setAsaasToken(e.target.value)}
                  className="w-full bg-background border border-border text-foreground px-3 py-2 pr-12 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                  placeholder="Cole o access_token da API Asaas"
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowAsaasToken((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs font-medium"
                >
                  {showAsaasToken ? 'Ocultar' : 'Mostrar'}
                </button>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={asaasSandbox}
                onChange={(e) => setAsaasSandbox(e.target.checked)}
                className="rounded border-border"
              />
              Ambiente sandbox (desmarque para produção)
            </label>
            <button
              type="submit"
              disabled={savingAsaas}
              className="w-full bg-[#10b981] hover:bg-[#059669] text-white py-2.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg"
            >
              {savingAsaas ? t('salvando') : t('salvar')}
            </button>
          </form>
        </div>
      )}

      {/* MODAL DE GERENCIAR MODELOS (WhatsApp Oficial) */}
      {showTemplateModal && selectedChannelForTemplates && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 md:pl-48">
          <div className={`bg-card border border-border p-8 rounded-xl shadow-lg w-full ${showCreateTemplate ? 'max-w-7xl' : 'max-w-4xl'} max-h-[90vh] overflow-y-auto relative`}>
            {/* Botão fechar */}
            <button
              onClick={() => {
                setShowTemplateModal(false);
                setSelectedChannelForTemplates(null);
                setShowCreateTemplate(false);
                setTemplates([]);
              }}
              className="absolute top-4 right-4 p-2 rounded hover:bg-accent transition"
              title="Fechar"
            >
              <XCircle className="w-5 h-5 text-red-400" />
            </button>

            <h3 className="text-xl font-bold text-foreground mb-6">Gerenciar Modelos de Mensagem</h3>

            {!showCreateTemplate ? (
              <div>
                {/* Botões de ação */}
                <div className="flex gap-4 mb-6">
                  <button
                    onClick={() => setShowCreateTemplate(true)}
                    className="bg-gradient-to-r from-green-500 to-green-700 hover:from-green-600 hover:to-green-800 text-white px-6 py-2 rounded-lg text-sm font-semibold shadow transition"
                  >
                    + Criar Modelo
                  </button>
                  <button
                    onClick={() => loadTemplates(selectedChannelForTemplates)}
                    disabled={loadingTemplates}
                    className="bg-secondary hover:bg-accent text-secondary-foreground px-6 py-2 rounded-lg text-sm font-semibold shadow border border-border transition disabled:opacity-50"
                  >
                    {loadingTemplates ? 'Carregando...' : 'Atualizar Lista'}
                  </button>
                </div>

                {/* Lista de modelos */}
                {loadingTemplates ? (
                  <div className="text-center py-8 text-muted-foreground">Carregando modelos...</div>
                ) : templates.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">Nenhum modelo encontrado</div>
                ) : (
                  <div className="space-y-3">
                    {templates.map((template) => (
                      <div
                        key={template.id || template.name}
                        className="bg-muted border border-border rounded-lg p-4"
                      >
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <h4 className="text-foreground font-semibold mb-1">{template.name}</h4>
                            <div className="text-sm text-muted-foreground space-y-1">
                              <p>Categoria: <span className="text-foreground/90">{translateCategory(template.category)}</span>
                                {template.sub_category && (
                                  <span className="text-muted-foreground ml-2">
                                    ({typeof template.sub_category === 'object'
                                      ? JSON.stringify(template.sub_category)
                                      : template.sub_category})
                                  </span>
                                )}
                              </p>
                              <p>Idioma: <span className="text-foreground/90">{translateLanguage(template.language)}</span></p>
                              <p>Status: <span className={`font-semibold ${template.status === 'APPROVED' ? 'text-green-400' :
                                template.status === 'PENDING' ? 'text-yellow-400' :
                                  template.status === 'REJECTED' ? 'text-red-400' :
                                    template.status === 'PAUSED' ? 'text-orange-400' :
                                      template.status === 'DISABLED' ? 'text-red-500' :
                                        'text-gray-400'
                                }`}>{translateStatus(template.status)}</span></p>
                              {(() => {
                                const translatedQuality = translateQuality(template.quality_score);
                                return translatedQuality ? (
                                  <p>Qualidade: <span className="text-foreground/90">{translatedQuality}</span></p>
                                ) : null;
                              })()}
                              {template.last_updated_time && (
                                <p>Última atualização: <span className="text-foreground/90">
                                  {new Date(template.last_updated_time).toLocaleString('pt-BR')}
                                </span></p>
                              )}
                              {template.status === 'REJECTED' && (() => {
                                const translatedReason = translateRejectionReason(template.rejected_reason);
                                return translatedReason ? (
                                  <div className="mt-2 p-2 bg-red-900/20 border border-red-500 rounded">
                                    <p className="text-xs text-red-400 font-semibold">Motivo da rejeição:</p>
                                    <p className="text-xs text-red-300 mt-1">{translatedReason}</p>
                                  </div>
                                ) : null;
                              })()}
                              {template.components && (
                                <div className="mt-2 pt-2 border-t border-border">
                                  <p className="text-xs text-muted-foreground">Componentes:</p>
                                  {template.components.map((comp, idx) => (
                                    <span key={idx} className="text-xs text-foreground/90 mr-2">
                                      {translateComponentType(comp.type)}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-2 ml-4">
                            <button
                              onClick={() => handleDeleteTemplate(template)}
                              className="text-red-400 hover:text-red-300 text-sm px-3 py-1 rounded hover:bg-red-900/20 transition"
                              title="Deletar modelo"
                            >
                              Deletar
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex justify-between items-center">
                  <h4 className="text-lg font-bold text-foreground">Criar Novo Modelo</h4>
                  <button
                    onClick={() => {
                      setShowCreateTemplate(false);
                      resetTemplateForm();
                    }}
                    className="bg-secondary hover:bg-accent text-secondary-foreground px-4 py-2 rounded-lg text-sm font-semibold shadow transition border border-border"
                  >
                    ← Voltar
                  </button>
                </div>

                {/* Layout com formulário à esquerda e preview à direita */}
                <div className="grid grid-cols-2 gap-6 items-start">
                  {/* Formulário */}
                  <div className="space-y-4 pr-2" style={{ maxHeight: '90vh', overflowY: 'auto' }}>

                    <div className="bg-muted border border-border rounded-lg p-4">
                      <p className="text-xs text-foreground">
                        <strong>Informação:</strong> Os modelos de mensagem permitem enviar mensagens fora da janela de atendimento ao cliente (24 horas).
                        Após criar, o modelo será analisado pela Meta e pode levar até 24 horas para ser aprovado.
                      </p>
                    </div>

                    <div className="space-y-4">
                      {/* Nome do Modelo */}
                      <div>
                        <label className="block text-sm font-semibold text-white mb-2">
                          Nome do Modelo <span className="text-red-400">*</span>
                        </label>
                        <input
                          type="text"
                          value={templateForm.name}
                          onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })}
                          placeholder="exemplo: confirmacao_pedido"
                          className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          maxLength={512}
                        />
                        <p className="text-xs text-gray-400 mt-1">Apenas letras minúsculas, números e sublinhados</p>
                      </div>

                      {/* Categoria, Idioma e Tipo de variável */}
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <label className="block text-sm font-semibold text-white mb-2">
                            Categoria <span className="text-red-400">*</span>
                          </label>
                          <select
                            value={templateForm.category}
                            onChange={(e) => setTemplateForm({ ...templateForm, category: e.target.value })}
                            className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="UTILITY">Utilidade</option>
                            <option value="MARKETING">Marketing</option>
                            <option value="AUTHENTICATION">Autenticação</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-sm font-semibold text-white mb-2">
                            Idioma <span className="text-red-400">*</span>
                          </label>
                          <select
                            value={templateForm.language}
                            onChange={(e) => setTemplateForm({ ...templateForm, language: e.target.value })}
                            className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="pt_BR">Português (Brasil)</option>
                            <option value="en_US">English (US)</option>
                            <option value="es_ES">Español</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-sm font-semibold text-white mb-2">
                            Tipo de variável
                          </label>
                          <select
                            value={templateForm.variable_type}
                            onChange={(e) => {
                              const newType = e.target.value;
                              setTemplateForm({ ...templateForm, variable_type: newType });
                              // Atualizar todas as variáveis existentes para o novo tipo
                              const updatedSamples = {};
                              Object.keys(variableSamples).forEach(varNum => {
                                updatedSamples[varNum] = {
                                  ...variableSamples[varNum],
                                  type: newType
                                };
                              });
                              setVariableSamples(updatedSamples);
                            }}
                            className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="number">Número</option>
                            <option value="nome">Nome</option>
                          </select>
                        </div>
                      </div>

                      {/* Header */}
                      <div>
                        <label className="block text-sm font-semibold text-white mb-2">Cabeçalho (Opcional)</label>
                        <select
                          value={templateForm.header.type}
                          onChange={(e) => setTemplateForm({
                            ...templateForm,
                            header: { ...templateForm.header, type: e.target.value, text: '', media_id: '', media_link: '' }
                          })}
                          className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 mb-2"
                        >
                          <option value="none">Sem cabeçalho</option>
                          <option value="text">Texto</option>
                          <option value="image">Imagem</option>
                          <option value="video">Vídeo</option>
                          <option value="document">Documento</option>
                        </select>
                        {templateForm.header.type === 'text' && (
                          <textarea
                            value={templateForm.header.text}
                            onChange={(e) => {
                              const newHeaderText = e.target.value;
                              setTemplateForm({ ...templateForm, header: { ...templateForm.header, text: newHeaderText } });
                              updateVariableSamples(templateForm.body.text, newHeaderText, templateForm.footer.text);
                            }}
                            placeholder="Texto do cabeçalho (máx. 60 caracteres)"
                            className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            maxLength={60}
                            rows={2}
                          />
                        )}
                        {['image', 'video', 'document'].includes(templateForm.header.type) && (
                          <div className="space-y-2">
                            <input
                              type="text"
                              value={templateForm.header.media_id}
                              onChange={(e) => setTemplateForm({ ...templateForm, header: { ...templateForm.header, media_id: e.target.value } })}
                              placeholder="Media ID (recomendado)"
                              className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            <span className="text-xs text-gray-400">ou</span>
                            <input
                              type="url"
                              value={templateForm.header.media_link}
                              onChange={(e) => setTemplateForm({ ...templateForm, header: { ...templateForm.header, media_link: e.target.value } })}
                              placeholder="URL da mídia (não recomendado)"
                              className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                          </div>
                        )}
                      </div>

                      {/* Body */}
                      <div>
                        <label className="block text-sm font-semibold text-white mb-2">
                          Corpo da Mensagem <span className="text-red-400">*</span>
                        </label>
                        {(() => {
                          const validation = validateVariableFormat();
                          return (
                            <>
                              <textarea
                                value={templateForm.body.text}
                                onChange={(e) => {
                                  const newBodyText = e.target.value;
                                  setTemplateForm({ ...templateForm, body: { ...templateForm.body, text: newBodyText } });
                                  updateVariableSamples(newBodyText, templateForm.header.text, templateForm.footer.text);
                                }}
                                placeholder="Digite o texto da mensagem. Use variáveis como {{1}}, {{2}}, etc."
                                className={`w-full bg-[#1a1b2e] border text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 ${validation.hasError
                                  ? 'border-red-500 focus:ring-red-500'
                                  : 'border-[#35365a] focus:ring-blue-500'
                                  }`}
                                rows={4}
                                required
                              />
                              {validation.hasError && (
                                <div className="mt-2 p-3 bg-red-900/20 border border-red-500 rounded-lg">
                                  <div className="flex items-start gap-2">
                                    <span className="text-red-500 text-lg">⚠</span>
                                    <p className="text-sm text-red-400">{validation.message}</p>
                                  </div>
                                </div>
                              )}
                            </>
                          );
                        })()}
                        <div className="mt-2 flex items-center gap-2">
                          <input
                            type="checkbox"
                            id="bodyVariables"
                            checked={templateForm.body.has_variables}
                            onChange={(e) => setTemplateForm({ ...templateForm, body: { ...templateForm.body, has_variables: e.target.checked } })}
                            className="w-4 h-4"
                          />
                          <label htmlFor="bodyVariables" className="text-sm text-gray-300">
                            Contém variáveis (use {`{{1}}`}, {`{{2}}`}, etc. no texto)
                          </label>
                        </div>
                        <p className="text-xs text-gray-400 mt-1">Máximo 1024 caracteres</p>
                      </div>

                      {/* Amostras de Variáveis */}
                      {(() => {
                        const bodyVars = extractVariables(templateForm.body.text);
                        const headerVars = templateForm.header.type === 'text' ? extractVariables(templateForm.header.text) : [];
                        const footerVars = extractVariables(templateForm.footer.text);
                        const allVars = [...new Set([...bodyVars, ...headerVars, ...footerVars])].sort((a, b) => a - b);

                        if (allVars.length === 0) return null;

                        return (
                          <div>
                            <div className="mb-3">
                              <label className="block text-sm font-semibold text-white mb-2">
                                Amostras de variáveis
                              </label>
                              <p className="text-xs text-gray-400 mb-3">
                                Inclua amostras de todas as variáveis na sua mensagem para ajudar a Meta a analisar seu modelo.
                                Para fins de proteção de privacidade, lembre-se de não incluir informações do cliente.
                              </p>
                            </div>

                            <div className="space-y-4">
                              {allVars.map(varNum => {
                                const sample = variableSamples[varNum] || { type: templateForm.variable_type || 'number', example: '' };
                                const varLabel = `{{${varNum}}}`;
                                const isInBody = bodyVars.includes(varNum);
                                const isInHeader = headerVars.includes(varNum);
                                const isInFooter = footerVars.includes(varNum);

                                let locationText = '';
                                if (isInHeader) locationText += 'Cabeçalho';
                                if (isInBody) locationText += (locationText ? ', ' : '') + 'Corpo';
                                if (isInFooter) locationText += (locationText ? ', ' : '') + 'Rodapé';

                                return (
                                  <div key={varNum} className="bg-[#1a1b2e] border border-[#35365a] rounded-lg p-4">
                                    <div className="mb-3">
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className="text-sm font-semibold text-white">{varLabel}</span>
                                        <span className="text-xs text-gray-400">({locationText})</span>
                                      </div>
                                    </div>

                                    <div>
                                      <label className="block text-xs font-medium text-gray-300 mb-2">
                                        Exemplo
                                      </label>
                                      <input
                                        type="text"
                                        value={sample.example}
                                        onChange={(e) => {
                                          setVariableSamples({
                                            ...variableSamples,
                                            [varNum]: { ...sample, type: templateForm.variable_type || 'number', example: e.target.value }
                                          });
                                        }}
                                        placeholder={`Exemplo para ${varLabel}`}
                                        className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                      />
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })()}

                      {/* Footer */}
                      <div>
                        <label className="block text-sm font-semibold text-white mb-2">Rodapé (Opcional)</label>
                        <input
                          type="text"
                          value={templateForm.footer.text}
                          onChange={(e) => {
                            setTemplateForm({ ...templateForm, footer: { ...templateForm.footer, text: e.target.value } });
                            updateVariableSamples(templateForm.body.text, templateForm.header.text, e.target.value);
                          }}
                          placeholder="Texto do rodapé (máx. 60 caracteres)"
                          className="w-full bg-[#1a1b2e] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                          maxLength={60}
                        />
                      </div>

                      {/* Botões */}
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <label className="block text-sm font-semibold text-white">Botões • Opcional</label>
                          {templateForm.buttons.length < 3 && (
                            <button
                              type="button"
                              onClick={() => {
                                const newButtons = [...templateForm.buttons, { type: 'QUICK_REPLY', title: '', payload: '', quick_reply_type: 'custom' }];
                                setTemplateForm({ ...templateForm, buttons: newButtons });
                              }}
                              className="text-blue-400 hover:text-blue-300 text-sm"
                            >
                              + Adicionar botão
                            </button>
                          )}
                        </div>
                        <p className="text-xs text-gray-400 mb-3">
                          Crie botões que permitam que os clientes interajam com seu modelo. Você pode adicionar até 3 botões. Apenas 1 botão pode ser do tipo "Ligar no WhatsApp".
                        </p>
                        {templateForm.buttons.map((btn, index) => (
                          <div key={index} className="bg-[#1a1b2e] border border-[#35365a] rounded-lg p-4 mb-2">
                            <div className="flex justify-between items-center mb-2">
                              <span className="text-sm text-gray-300">Botão {index + 1}</span>
                              <button
                                type="button"
                                onClick={() => {
                                  const newButtons = templateForm.buttons.filter((_, i) => i !== index);
                                  setTemplateForm({ ...templateForm, buttons: newButtons });
                                }}
                                className="text-red-400 hover:text-red-300 text-sm"
                              >
                                Remover
                              </button>
                            </div>
                            <div className="grid grid-cols-2 gap-4 mb-2">
                              <div>
                                <label className="block text-xs font-medium text-gray-300 mb-2">Tipo de ação</label>
                                <select
                                  value={btn.type}
                                  onChange={(e) => {
                                    const newButtons = [...templateForm.buttons];
                                    newButtons[index] = { ...newButtons[index], type: e.target.value, url_type: '', offer_code: '' };
                                    setTemplateForm({ ...templateForm, buttons: newButtons });
                                  }}
                                  className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                >
                                  <option value="QUICK_REPLY">Personalizado</option>
                                  <option value="URL">Acessar o site</option>
                                  <option
                                    value="PHONE_NUMBER_WHATSAPP"
                                    disabled={templateForm.buttons.some((b, i) => i !== index && b.type === 'PHONE_NUMBER_WHATSAPP')}
                                  >
                                    Ligar no WhatsApp
                                  </option>
                                  <option value="PHONE_NUMBER">Ligar</option>
                                  <option value="COPY_CODE">Copiar código da oferta</option>
                                </select>
                                {templateForm.buttons.some((b, i) => i !== index && b.type === 'PHONE_NUMBER_WHATSAPP') && (
                                  <p className="text-xs text-yellow-400 mt-1">Apenas 1 botão pode ser "Ligar no WhatsApp"</p>
                                )}
                              </div>
                              <div>
                                <label className="block text-xs font-medium text-gray-300 mb-2">Texto do botão</label>
                                <input
                                  type="text"
                                  value={btn.title}
                                  onChange={(e) => {
                                    const newButtons = [...templateForm.buttons];
                                    newButtons[index] = { ...newButtons[index], title: e.target.value };
                                    setTemplateForm({ ...templateForm, buttons: newButtons });
                                  }}
                                  placeholder="Texto do botão"
                                  className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  maxLength={25}
                                />
                                <div className="text-right text-xs text-gray-400 mt-1">{btn.title?.length || 0}/25</div>
                              </div>
                            </div>
                            {/* Campos específicos por tipo */}
                            {btn.type === 'QUICK_REPLY' && (
                              <div className="space-y-2">
                                <div>
                                  <label className="block text-xs font-medium text-gray-300 mb-2">Tipo</label>
                                  <select
                                    value={btn.quick_reply_type || 'custom'}
                                    onChange={(e) => {
                                      const newButtons = [...templateForm.buttons];
                                      newButtons[index] = { ...newButtons[index], quick_reply_type: e.target.value };
                                      setTemplateForm({ ...templateForm, buttons: newButtons });
                                    }}
                                    className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  >
                                    <option value="custom">Personalizado</option>
                                    <option value="preconfigured">Resposta pré-configurada</option>
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-gray-300 mb-2">Payload</label>
                                  <input
                                    type="text"
                                    value={btn.payload || ''}
                                    onChange={(e) => {
                                      const newButtons = [...templateForm.buttons];
                                      newButtons[index] = { ...newButtons[index], payload: e.target.value };
                                      setTemplateForm({ ...templateForm, buttons: newButtons });
                                    }}
                                    placeholder="Payload (identificador único para a resposta)"
                                    className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  />
                                </div>
                              </div>
                            )}
                            {btn.type === 'URL' && (
                              <div className="space-y-2">
                                <div>
                                  <label className="block text-xs font-medium text-gray-300 mb-2">Tipo de URL</label>
                                  <select
                                    value={btn.url_type || 'static'}
                                    onChange={(e) => {
                                      const newButtons = [...templateForm.buttons];
                                      newButtons[index] = { ...newButtons[index], url_type: e.target.value };
                                      setTemplateForm({ ...templateForm, buttons: newButtons });
                                    }}
                                    className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  >
                                    <option value="static">Estática</option>
                                    <option value="dynamic">Dinâmica</option>
                                  </select>
                                </div>
                                <div>
                                  <label className="block text-xs font-medium text-gray-300 mb-2">URL do site</label>
                                  <input
                                    type="url"
                                    value={btn.url || ''}
                                    onChange={(e) => {
                                      const newButtons = [...templateForm.buttons];
                                      newButtons[index] = { ...newButtons[index], url: e.target.value };
                                      setTemplateForm({ ...templateForm, buttons: newButtons });
                                    }}
                                    placeholder="https://exemplo.com"
                                    className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    maxLength={2000}
                                  />
                                  <div className="text-right text-xs text-gray-400 mt-1">{btn.url?.length || 0}/2000</div>
                                </div>
                              </div>
                            )}
                            {btn.type === 'PHONE_NUMBER_WHATSAPP' && (
                              <div>
                                <label className="block text-xs font-medium text-gray-300 mb-2">Número de telefone</label>
                                <input
                                  type="tel"
                                  value={btn.phone_number || ''}
                                  onChange={(e) => {
                                    const newButtons = [...templateForm.buttons];
                                    newButtons[index] = { ...newButtons[index], phone_number: e.target.value };
                                    setTemplateForm({ ...templateForm, buttons: newButtons });
                                  }}
                                  placeholder="Número de telefone (ex: +5511999999999)"
                                  className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                              </div>
                            )}
                            {btn.type === 'PHONE_NUMBER' && (
                              <div>
                                <label className="block text-xs font-medium text-gray-300 mb-2">Número de telefone</label>
                                <input
                                  type="tel"
                                  value={btn.phone_number || ''}
                                  onChange={(e) => {
                                    const newButtons = [...templateForm.buttons];
                                    newButtons[index] = { ...newButtons[index], phone_number: e.target.value };
                                    setTemplateForm({ ...templateForm, buttons: newButtons });
                                  }}
                                  placeholder="Número de telefone (ex: +5511999999999)"
                                  className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                              </div>
                            )}
                            {btn.type === 'COPY_CODE' && (
                              <div>
                                <label className="block text-xs font-medium text-gray-300 mb-2">Código da oferta</label>
                                <input
                                  type="text"
                                  value={btn.offer_code || ''}
                                  onChange={(e) => {
                                    const newButtons = [...templateForm.buttons];
                                    newButtons[index] = { ...newButtons[index], offer_code: e.target.value };
                                    setTemplateForm({ ...templateForm, buttons: newButtons });
                                  }}
                                  placeholder="Inserir amostra"
                                  className="w-full bg-[#2d2e4a] border border-[#35365a] text-white px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                  maxLength={20}
                                />
                                <div className="text-right text-xs text-gray-400 mt-1">{btn.offer_code?.length || 0}/20</div>
                                <p className="text-xs text-gray-400 mt-1">Adicionar texto de amostra</p>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Botões de ação */}
                    <div className="flex justify-end gap-4 pt-4">
                      <button
                        onClick={() => {
                          setShowCreateTemplate(false);
                          resetTemplateForm();
                        }}
                        className="bg-gray-600 hover:bg-gray-700 text-white px-6 py-2 rounded-lg text-sm font-semibold shadow transition"
                      >
                        Cancelar
                      </button>
                      <button
                        onClick={handleCreateTemplate}
                        disabled={creatingTemplate || !templateForm.name || !templateForm.body.text || validateVariableFormat().hasError}
                        className="bg-gradient-to-r from-green-500 to-green-700 hover:from-green-600 hover:to-green-800 text-white px-6 py-2 rounded-lg text-sm font-semibold shadow transition disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {creatingTemplate ? 'Criando...' : 'Criar Modelo'}
                      </button>
                    </div>
                  </div>

                  {/* Prévia do modelo */}
                  <div className="flex flex-col items-center sticky top-4">
                    <h5 className="text-sm font-semibold text-white mb-3">Prévia do modelo</h5>
                    {/* Fundo verde claro com padrão do WhatsApp */}
                    <div className="bg-[#e5ddd5] rounded-lg p-6 flex flex-col items-center justify-center relative overflow-hidden" style={{ width: '400px', minHeight: '500px', backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'100\' height=\'100\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cdefs%3E%3Cpattern id=\'grid\' width=\'40\' height=\'40\' patternUnits=\'userSpaceOnUse\'%3E%3Cpath d=\'M 40 0 L 0 0 0 40\' fill=\'none\' stroke=\'%23d4d4d4\' stroke-width=\'0.5\'/%3E%3C/pattern%3E%3C/defs%3E%3Crect width=\'100\' height=\'100\' fill=\'url(%23grid)\'/%3E%3C/svg%3E")' }}>
                      {/* Mensagem do template */}
                      <div className="bg-white rounded-lg p-4 shadow-lg max-w-[90%] w-full">
                        {/* Header do template (se houver) */}
                        {templateForm.header.type !== 'none' && (
                          <div className="mb-3 pb-3 border-b border-gray-200">
                            {templateForm.header.type === 'text' && templateForm.header.text && (
                              <p className="text-base font-bold text-gray-900 break-words">
                                {(() => {
                                  const validation = validateVariableFormat();
                                  return templateForm.header.text.split(/(\{\{\d+\}\})/).map((part, i) => {
                                    const varMatch = part.match(/\{\{(\d+)\}\}/);
                                    if (varMatch) {
                                      const varNum = parseInt(varMatch[1]);
                                      const sample = variableSamples[varNum];

                                      if (validation.hasError) {
                                        return (
                                          <span key={i} className="bg-red-200 px-1.5 py-0.5 rounded font-mono text-sm border border-red-400 inline-block mx-0.5 text-red-800">
                                            {part}
                                          </span>
                                        );
                                      }

                                      if (sample && sample.example) {
                                        return <span key={i} className="font-semibold">{sample.example}</span>;
                                      }
                                      return <span key={i} className="bg-yellow-200 px-1.5 py-0.5 rounded font-mono text-sm border border-yellow-300 inline-block mx-0.5">{part}</span>;
                                    }
                                    return <span key={i}>{part}</span>;
                                  });
                                })()}
                              </p>
                            )}
                            {['image', 'video', 'document'].includes(templateForm.header.type) && (
                              <div className="bg-gray-100 rounded p-3 text-sm text-gray-700 flex items-center gap-2">
                                <span>{templateForm.header.type === 'image' ? '📷' : templateForm.header.type === 'video' ? '🎥' : '📄'}</span>
                                <span>{templateForm.header.type === 'image' ? 'Imagem' : templateForm.header.type === 'video' ? 'Vídeo' : 'Documento'}</span>
                                {templateForm.header.media_id && <span className="text-gray-500 text-xs">({templateForm.header.media_id.substring(0, 8)}...)</span>}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Body do template */}
                        {templateForm.body.text ? (
                          <div className="mb-3">
                            <p className="text-sm text-gray-800 whitespace-pre-wrap break-words leading-relaxed">
                              {(() => {
                                const validation = validateVariableFormat();
                                return templateForm.body.text.split(/(\{\{\d+\}\})/).map((part, i) => {
                                  const varMatch = part.match(/\{\{(\d+)\}\}/);
                                  if (varMatch) {
                                    const varNum = parseInt(varMatch[1]);
                                    const sample = variableSamples[varNum];

                                    // Se houver erro de validação (tipo nome mas usando formato numérico), destacar em vermelho
                                    if (validation.hasError) {
                                      return (
                                        <span key={i} className="bg-red-200 px-1.5 py-0.5 rounded font-mono text-sm border border-red-400 inline-block mx-0.5 text-red-800">
                                          {part}
                                        </span>
                                      );
                                    }

                                    if (sample && sample.example) {
                                      // Mostrar o valor de exemplo
                                      return <span key={i} className="font-semibold">{sample.example}</span>;
                                    } else {
                                      // Destacar a variável em amarelo se não tiver exemplo
                                      return (
                                        <span key={i} className="bg-yellow-200 px-1.5 py-0.5 rounded font-mono text-sm border border-yellow-300 inline-block mx-0.5">
                                          {part}
                                        </span>
                                      );
                                    }
                                  }
                                  return <span key={i}>{part}</span>;
                                });
                              })()}
                            </p>
                          </div>
                        ) : (
                          <div className="mb-3 text-gray-400 italic text-sm">Digite o corpo da mensagem...</div>
                        )}

                        {/* Footer do template (se houver) */}
                        {templateForm.footer.text && (
                          <div className="mt-3 pt-3 border-t border-gray-200">
                            <p className="text-xs text-gray-600 break-words">
                              {(() => {
                                const validation = validateVariableFormat();
                                return templateForm.footer.text.split(/(\{\{\d+\}\})/).map((part, i) => {
                                  const varMatch = part.match(/\{\{(\d+)\}\}/);
                                  if (varMatch) {
                                    const varNum = parseInt(varMatch[1]);
                                    const sample = variableSamples[varNum];

                                    if (validation.hasError) {
                                      return (
                                        <span key={i} className="bg-red-200 px-1.5 py-0.5 rounded font-mono text-xs border border-red-400 inline-block mx-0.5 text-red-800">
                                          {part}
                                        </span>
                                      );
                                    }

                                    if (sample && sample.example) {
                                      return <span key={i} className="font-semibold">{sample.example}</span>;
                                    }
                                    return <span key={i} className="bg-yellow-200 px-1.5 py-0.5 rounded font-mono text-xs border border-yellow-300 inline-block mx-0.5">{part}</span>;
                                  }
                                  return <span key={i}>{part}</span>;
                                });
                              })()}
                            </p>
                          </div>
                        )}

                        {/* Botões do template */}
                        {templateForm.buttons.length > 0 && (
                          <div className="mt-4 space-y-2">
                            {templateForm.buttons.filter(btn => btn.type && btn.title).map((btn, idx) => {
                              let icon = null;
                              if (btn.type === 'URL') {
                                icon = '🔗';
                              } else if (btn.type === 'PHONE_NUMBER_WHATSAPP' || btn.type === 'PHONE_NUMBER') {
                                icon = '📞';
                              } else if (btn.type === 'COPY_CODE') {
                                icon = '📋';
                              }

                              return (
                                <div key={idx} className="bg-primary text-primary-foreground px-4 py-1.5 rounded-full text-xs font-bold hover:bg-primary/90 transition shadow-sm flex items-center justify-center gap-2">
                                  {icon && <span>{icon}</span>}
                                  <span>{btn.title}</span>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* Timestamp */}
                        <div className="flex justify-end items-center mt-3 gap-1">
                          <span className="text-xs text-gray-500">23:46</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
