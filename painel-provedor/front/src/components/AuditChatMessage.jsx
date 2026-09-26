import CustomAudioPlayer from './ui/CustomAudioPlayer';
import FilePreview from './FilePreview';
import { buildMediaUrl, openMediaInNewTab } from '../config/environment';

/** Extrai assinatura do atendente (*Nome disse:* / **Nome** / *Nome*) e devolve nome + corpo limpo. */
export const stripAgentSignature = (content) => {
  if (!content || typeof content !== 'string') {
    return { name: null, body: content };
  }
  let match = content.match(/^\s*\*([^*\n]+?)\s+disse:\*\s*\n+([\s\S]*)$/i);
  if (match) return { name: match[1].trim(), body: match[2] };
  match = content.match(/^\s*\*\*([^*\n]+)\*\*\s*\n+([\s\S]*)$/);
  if (match) return { name: match[1].trim(), body: match[2] };
  match = content.match(/^\s*\*([^*\n]+)\*\s*\n+([\s\S]*)$/);
  if (match && !/disse/i.test(match[1])) return { name: match[1].trim(), body: match[2] };
  return { name: null, body: content };
};

const renderWithLinks = (text) => {
  if (!text || typeof text !== 'string') return text;
  const urlRegex = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;
  const parts = [];
  let lastIndex = 0;
  let match;
  while ((match = urlRegex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.substring(lastIndex, match.index));
    const url = match[0].replace(/[.,;:!?]+$/, '');
    const href = url.startsWith('http') ? url : `https://${url}`;
    parts.push(
      <a
        key={`${match.index}-${url}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="underline break-all text-[#7DD3FC] decoration-[#7DD3FC] hover:text-[#5BC0EB] hover:decoration-[#5BC0EB] transition-colors"
      >
        {url}
      </a>
    );
    lastIndex = match.index + url.length;
  }
  if (lastIndex < text.length) parts.push(text.substring(lastIndex));
  return parts.length ? parts : text;
};

const MEDIA_PLACEHOLDER = /^\[(image|audio|video|document|attachment|file|ig_reel|share|story_mention)\]$/i;

const AuditChatMessage = ({ message: msg, conversationId, channelType, chatbotName, statusIcon = null }) => {
  const attrs = msg.additional_attributes || {};
  const attachments = Array.isArray(msg.attachments) ? msg.attachments : [];
  const content = msg.content || msg.text || '';
  const isCustomer = msg.is_from_customer === true;

  const signature = !isCustomer ? stripAgentSignature(content) : { name: null, body: content };
  const agentName = (attrs.agent_name || msg.agent_display_name || msg.sender?.name || signature.name || '').trim();
  const hasHumanAgentMarker = Boolean(agentName || attrs.sent_by || msg.sender?.sender_type === 'agent');
  const isAI = !isCustomer && !hasHumanAgentMarker && (
    msg.sender?.sender_type === 'ai' || msg.from_ai === true || attrs.from_ai === true
  );
  const isBot = !isCustomer && !isAI && !hasHumanAgentMarker && (
    msg.message_type === 'incoming' || msg.sender?.sender_type === 'bot'
  );
  const isAgent = !isCustomer && !isBot && !isAI;
  const chatbotDisplayName = (attrs.chatbot_name || chatbotName || '').trim();
  const headerName = isAgent ? agentName : (isAI || isBot) ? chatbotDisplayName : '';

  const isSystemMessage = !isAI && (
    attrs.system_message ||
    (typeof content === 'string' && (
      content.includes('Conversa atribuída para') ||
      content.includes('Conversa transferida para') ||
      content.includes('Protocolo alterado de')
    ))
  );
  const isResumoSuporte = attrs.tipo === 'resumo_suporte';
  const isRevoked = msg.message_type === 'revoke';

  const fileUrl = msg.file_url;
  const hasImage = attachments.some((a) => a.file_type === 'image') || (msg.message_type === 'image' && fileUrl);
  const hasVideo = attachments.some((a) => a.file_type === 'video') || (msg.message_type === 'video' && fileUrl);
  const hasAudio = attachments.some((a) => a.file_type === 'audio') ||
    ((msg.message_type === 'audio' || msg.message_type === 'ptt') && fileUrl);
  const hasDocument = attachments.some((a) => a.file_type === 'file') || (msg.message_type === 'document' && fileUrl);
  const isQrPix = msg.message_type === 'image' && content.includes('QR Code PIX');
  const hasBoleto = content.includes('🔗') && content.includes('Link do Boleto:');
  const isInvoice = attrs.is_invoice || content.includes('dados para pagamento de sua fatura');

  let displayText = signature.name ? signature.body : content;
  if (headerName && displayText) {
    const boldPrefix = `*${headerName}*`;
    if (displayText.startsWith(boldPrefix)) {
      displayText = displayText.slice(boldPrefix.length).replace(/^\n+/, '');
    } else if (displayText.startsWith(headerName)) {
      displayText = displayText.slice(headerName.length).replace(/^[:\s\n]+/, '');
    }
  }
  const trimmedText = (displayText || '').trim();
  const isAgentAudioPlaceholder = !isCustomer && hasAudio && trimmedText === 'Mensagem de voz';
  const showText = Boolean(trimmedText) &&
    !MEDIA_PLACEHOLDER.test(trimmedText) &&
    !isAgentAudioPlaceholder &&
    !hasBoleto &&
    !(hasDocument && fileUrl && trimmedText === (msg.file_name || '').trim()) &&
    !(hasDocument && fileUrl && msg.message_type === 'document' && !isInvoice && trimmedText === 'Documento');

  const hasCaption = showText && !isQrPix && !isInvoice;
  const isPureImage = hasImage && !hasVideo && !hasAudio && !hasDocument && !hasCaption && !isQrPix;
  const isImageWithCaption = hasImage && hasCaption && !hasVideo && !hasAudio && !hasDocument;

  const bubbleShape = isPureImage
    ? 'p-0 bg-transparent shadow-none'
    : isImageWithCaption
      ? 'p-0 overflow-hidden shadow-sm rounded-2xl'
      : 'px-5 py-3 shadow-sm rounded-2xl';
  const bubbleColor = isPureImage
    ? ''
    : isCustomer
      ? 'bg-[#4A5568] text-white'
      : isResumoSuporte
        ? 'bg-[#FFF9C4] text-[#856404] border border-[#FFE69C]'
        : isSystemMessage
          ? 'bg-zinc-200/70 text-zinc-800 border border-zinc-300/60 dark:bg-zinc-800/55 dark:text-zinc-100 dark:border-white/10'
          : 'bg-[#2196F3] text-white';

  const imageClass = `max-w-full h-auto cursor-pointer hover:opacity-95 transition-opacity block ${
    isPureImage ? 'rounded-2xl shadow-md' : isImageWithCaption ? 'w-full rounded-t-2xl' : 'rounded-lg'
  }`;
  const imageStyle = { maxHeight: isPureImage ? '420px' : '300px' };
  const showInteractive = channelType !== 'telegram';

  return (
    <div className={`flex ${isCustomer ? 'justify-start' : 'justify-end'} mb-4 min-w-0`}>
      <div className="max-w-[70%] min-w-0">
        <div className={`relative ${bubbleShape} ${bubbleColor}`}>
          {!isCustomer && !isSystemMessage && headerName && (
            <div
              className={
                isAgent
                  ? 'text-[11px] font-semibold tracking-wide text-white/90 mb-2 pb-1 border-b border-white/15 text-left leading-tight'
                  : 'text-[11px] font-bold tracking-wide text-white/95 mb-3 pb-1.5 border-b border-white/20 text-left leading-tight'
              }
            >
              {headerName}
            </div>
          )}

          {attrs.is_reply && (
            <div className={`mb-2 p-2 rounded-lg text-xs opacity-90 ${isCustomer ? 'bg-white/30' : 'bg-black/10'}`}>
              <div className="font-medium">{isCustomer ? 'Resposta a:' : 'Respondendo a:'}</div>
              <div className="truncate">{attrs.reply_to_content || 'Mensagem anterior'}</div>
            </div>
          )}

          {isRevoked && <div className="text-sm italic opacity-75">Mensagem apagada</div>}

          {!isRevoked && hasImage && !isQrPix && (
            attachments.filter((a) => a.file_type === 'image').length > 0
              ? attachments.filter((a) => a.file_type === 'image').map((a, i) => (
                <div key={i} className={isPureImage ? '' : 'mb-2'}>
                  <img
                    src={buildMediaUrl(a.data_url)}
                    alt="Imagem"
                    className={imageClass}
                    style={imageStyle}
                    onClick={(e) => openMediaInNewTab(buildMediaUrl(a.data_url), e)}
                  />
                </div>
              ))
              : fileUrl && (
                <div className={isPureImage ? '' : 'mb-2'}>
                  <img
                    src={buildMediaUrl(fileUrl)}
                    alt="Imagem"
                    className={imageClass}
                    style={imageStyle}
                    onClick={(e) => openMediaInNewTab(buildMediaUrl(fileUrl), e)}
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                </div>
              )
          )}

          {!isRevoked && hasVideo && (
            <div className="mb-2">
              <video controls className="max-w-full h-auto rounded-lg" style={{ maxHeight: '300px' }}>
                <source
                  src={buildMediaUrl(attachments.find((a) => a.file_type === 'video')?.data_url || fileUrl)}
                  type="video/mp4"
                />
                Seu navegador não suporta o elemento de vídeo.
              </video>
            </div>
          )}

          {!isRevoked && hasAudio && (
            <div className="mb-2">
              <CustomAudioPlayer
                src={buildMediaUrl(attachments.find((a) => a.file_type === 'audio')?.data_url || fileUrl)}
                isCustomer={isCustomer}
                conversationId={conversationId}
              />
            </div>
          )}

          {!isRevoked && hasDocument && (
            attachments.filter((a) => a.file_type === 'file').length > 0
              ? attachments.filter((a) => a.file_type === 'file').map((a, i) => (
                <div key={i} className="mb-2">
                  <FilePreview
                    file={{ url: a.data_url, name: a.file_name || 'Documento', type: a.mime_type || 'application/pdf' }}
                    isCustomer={isCustomer}
                  />
                </div>
              ))
              : fileUrl && (
                <div className="mb-2">
                  <FilePreview
                    file={{
                      url: fileUrl,
                      name: msg.file_name || (trimmedText && trimmedText.length < 120 ? trimmedText : '') || 'Documento',
                      size: msg.file_size,
                      type: attrs.file_type || attrs.mime_type || 'application/pdf',
                      pages: attrs.pages,
                      jpegThumbnail: attrs.pdf_thumbnail,
                      uazapi_url: attrs.file_url,
                      additional_attributes: attrs,
                    }}
                    isCustomer={isCustomer}
                    content={msg.content}
                  />
                </div>
              )
          )}

          {!isRevoked && isQrPix && (
            <div className="mb-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
              <div className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">🎯 QR Code PIX</div>
              <div className="text-xs text-green-700 dark:text-green-300 mb-2">
                Escaneie este QR code com o app do seu banco para pagar via PIX
              </div>
              {fileUrl && (
                <div className="bg-white p-2 rounded border">
                  <img src={buildMediaUrl(fileUrl)} alt="QR Code PIX" className="w-32 h-32 mx-auto" />
                </div>
              )}
            </div>
          )}

          {!isRevoked && hasBoleto && (
            <div className="mb-2 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
              <div className="text-sm font-medium text-orange-900 dark:text-orange-100 mb-2">📄 Boleto Bancário</div>
              <div className="text-xs text-orange-700 dark:text-orange-300 mb-2">
                Clique no link abaixo para acessar o boleto completo
              </div>
              {content.split('\n').filter((line) => line.includes('https://')).map((line, i) => (
                <a
                  key={i}
                  href={line.trim()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block w-full px-3 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors text-sm text-center"
                >
                  📥 Baixar Boleto PDF
                </a>
              ))}
            </div>
          )}

          {!isRevoked && showInteractive && Array.isArray(attrs.interactive_rows) && attrs.interactive_rows.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <div className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                Opções da lista do menu
              </div>
              {attrs.interactive_rows.map((row, i) => (
                <div
                  key={row.id || i}
                  className="px-3 py-2 bg-white/10 dark:bg-slate-700/50 border border-slate-200/20 dark:border-slate-600/30 rounded-lg"
                >
                  <div className="text-xs font-bold text-foreground">{row.title}</div>
                  {row.description && (
                    <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">{row.description}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {!isRevoked && showInteractive && Array.isArray(attrs.interactive_buttons) && attrs.interactive_buttons.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {attrs.interactive_buttons.map((btn, i) => (
                <div
                  key={btn.id || i}
                  className="px-3 py-2 bg-blue-500/10 dark:bg-blue-500/20 border border-blue-300/30 dark:border-blue-600/30 rounded-lg text-center"
                >
                  <span className="text-xs font-bold text-blue-600 dark:text-blue-400">{btn.title}</span>
                </div>
              ))}
            </div>
          )}

          {!isRevoked && showText && (
            <div
              className={`whitespace-pre-wrap break-words ${isImageWithCaption ? 'px-4 py-3' : ''}`}
              style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}
            >
              {renderWithLinks(displayText)}
            </div>
          )}

          <div className={`flex w-full min-w-0 items-center justify-between gap-2 mt-1 ${isPureImage ? 'px-0.5' : ''} ${isImageWithCaption ? 'px-4 pb-2' : ''}`}>
            <span
              className={`inline-flex items-center gap-1 text-xs ${
                isPureImage || isCustomer || isSystemMessage || isResumoSuporte ? 'text-muted-foreground' : 'text-white'
              }`}
            >
              {msg.created_at || msg.timestamp
                ? new Date(msg.created_at || msg.timestamp).toLocaleString('pt-BR', {
                  hour: '2-digit',
                  minute: '2-digit',
                  day: '2-digit',
                  month: '2-digit',
                })
                : ''}
            </span>
            {statusIcon}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuditChatMessage;
