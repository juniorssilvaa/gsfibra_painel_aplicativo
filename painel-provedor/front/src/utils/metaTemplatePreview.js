/** Modelo de prévia e estilos dos cards de templates da Meta (aba Modelos de Mensagem e Campanhas). */

export const TEMPLATE_CARD_STYLES = `
    .template-card {
      position: relative;
      background: #3a3a3d;
      border-radius: 10px;
      padding: 16px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.05);
      transition: .35s ease;
      cursor: default;
    }

    .template-card::before {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(120deg, rgba(255,255,255,.18), rgba(255,255,255,.04) 40%, transparent 70%);
      opacity: 0;
      transition: .35s;
      z-index: 2;
      pointer-events: none;
    }

    .template-card::after {
      content: '';
      position: absolute;
      top: -120%;
      left: -60%;
      width: 200%;
      height: 200%;
      background: linear-gradient(to bottom right, transparent, rgba(255,255,255,.14), transparent);
      transform: rotate(25deg);
      transition: .9s;
      z-index: 3;
      pointer-events: none;
    }

    .template-card:hover::before { opacity: 1; }
    .template-card:hover::after { top: -40%; left: -10%; }
    .template-card:hover {
      transform: translateY(-5px);
      box-shadow: 0 20px 40px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.05);
    }

    .overlay-gallery {
      position: absolute;
      inset: 0;
      background: rgba(0,0,0,.40);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transition: .25s;
      z-index: 10;
    }

    .template-card:hover .overlay-gallery { opacity: 1; }

    .use-btn-gallery {
      border: none;
      height: 54px;
      padding: 0 28px;
      border-radius: 14px;
      background: linear-gradient(180deg,#ffae47,#ff9127);
      color: white;
      font-size: 15px;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 10px 30px rgba(255,145,39,.35);
      transform: translateY(15px);
      transition: .3s;
    }

    .template-card:hover .use-btn-gallery { transform: translateY(0); }

    /* WhatsApp UI Inside Cards */
    .wa-card-custom { background: #d8d1ca; border-radius: 12px; overflow: hidden; }
    .wa-header-custom { background: #16816f; height: 36px; display: flex; align-items: center; gap: 10px; padding: 0 12px; color: white; font-size: 13px; font-weight: 700; }
    .wa-body-custom { padding: 8px; }
    .box-custom { background: #ebedf0; border-radius: 6px; border: 1px solid #d5d7da; overflow: hidden; }
    .top-info-custom { font-size: 11px; color: #646464; padding: 7px 10px; border-bottom: 1px dashed #8d9197; }
    .wa-header-text-custom {
      font-size: 13px;
      font-weight: 700;
      color: #111827;
      padding: 10px 12px;
      border-bottom: 1px solid #d7d7d7;
      background: #ebedf0;
      line-height: 1.35;
    }
    .attach-title-custom { color: #000000; font-size: 13px; font-weight: 700; }
    .attach-sub-custom { color: #444444; font-size: 11px; }
    .download-icon-custom { width: 22px; height: 22px; border-radius: 50%; border: 2px solid #22b15d; display: flex; align-items: center; justify-content: center; color: #22b15d; font-size: 11px; font-weight: bold; }
    .payment-title-custom { display: flex; justify-content: space-between; align-items: center; color: #000000; font-size: 12px; font-weight: 800; margin-bottom: 5px; }
    .total-custom { border-top: 1px dashed #8d9197; padding-top: 6px; display: flex; justify-content: space-between; font-size: 12px; color: #000000; font-weight: 800; }
    .message-custom { background: #f7f7f7; border-top: 1px solid #d7d7d7; padding: 10px; color: #1a1a1a; font-size: 13px; line-height: 1.5; font-style: italic; white-space: pre-wrap; }
    .action-btn-custom { width: 100%; height: 32px; border: none; border-radius: 4px; background: #ffffff; border: 1px solid #d0d0d0; margin-top: 6px; color: #11a24d; font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
    .wa-link-action-btn { color: #1a73e8 !important; font-weight: 600; }
    .payment-custom { padding: 7px 10px; border-bottom: 1px dashed #8d9197; }
    .template-title { font-size: 12px; font-weight: 600; color: #e5e5e5; letter-spacing: 0.02em; }
    .badge-template-tab { display: inline-block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #ff9127; background: rgba(255,145,39,.14); padding: 4px 10px; border-radius: 6px; margin-top: 4px; }
    .badge { display: inline-block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #ff9127; background: rgba(255,145,39,.14); padding: 4px 10px; border-radius: 6px; margin-top: 4px; }
  `;

const TEMPLATE_STATUS_LABELS = { APPROVED: 'Aprovado', REJECTED: 'Rejeitado', PENDING: 'Em análise' };

export function translateTemplateStatus(status) {
  return TEMPLATE_STATUS_LABELS[status] || status;
}

/** Título amigável a partir do nome técnico na Meta (remove sufixo _p{id}). */
export function humanizeTemplateName(name) {
  if (!name) return 'Template';
  const base = String(name).replace(/_p\d+$/i, '').trim();
  const parts = base.split('_').filter(Boolean);
  if (parts.length === 0) return 'Template';
  return parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
    .join(' ');
}

/** Deriva o que exibir na prévia WhatsApp a partir do JSON da Meta. */
export function getTemplatePreviewModel(template) {
  const components = template?.components || [];
  const byType = (t) =>
    components.find((c) => String(c.type || '').toUpperCase() === t);
  const header = byType('HEADER');
  const body = byType('BODY');
  const foot = byType('FOOTER');
  const btnBlock = byType('BUTTONS');
  const fmt = String(header?.format || '').toUpperCase();
  const buttons = btnBlock?.buttons || [];
  const hasOrderDetails = buttons.some(
    (b) => String(b.type || '').toUpperCase() === 'ORDER_DETAILS'
  );

  const categoryLabel =
    template.category === 'UTILITY'
      ? 'Conversas de utilidade'
      : template.category === 'MARKETING'
        ? 'Marketing'
        : template.category === 'AUTHENTICATION'
          ? 'Autenticação'
          : template.category || 'Template';

  const badgeLabel = hasOrderDetails ? 'Detalhes de pedido' : 'Mensagem modelo';

  return {
    displayTitle: humanizeTemplateName(template?.name),
    categoryLabel,
    badgeLabel,
    bodyText: body?.text ?? '',
    footerText: (foot?.text || '').trim(),
    headerFormat: fmt,
    headerText: (header?.text || '').trim(),
    buttons,
    hasOrderDetails,
    showPdfHeader: fmt === 'DOCUMENT',
    showMediaHeader: fmt === 'IMAGE' || fmt === 'VIDEO',
    showTextHeader: fmt === 'TEXT' && !!(header?.text || '').trim(),
  };
}

export function orderDetailsPaymentFlags(orderDetailsType) {
  const t = orderDetailsType || 'pix_boleto';
  return {
    showPix: t === 'pix' || t === 'pix_boleto',
    showBoleto: t === 'boleto' || t === 'pix_boleto',
  };
}

/** Botões exibidos na prévia (Meta só registra um ORDER_DETAILS; boleto aparece no envio). */
export function getOrderDetailsPreviewActionButtons(orderDetailsType = 'pix_boleto') {
  const { showPix, showBoleto } = orderDetailsPaymentFlags(orderDetailsType);
  const buttons = [];
  if (showPix) buttons.push({ text: 'Copiar Chave Pix', kind: 'copy' });
  if (showBoleto) buttons.push({ text: 'Copiar código de barras', kind: 'copy' });
  return buttons;
}

export function getTemplateCardPreviewButtons(preview) {
  if (preview?.hasOrderDetails) {
    return getOrderDetailsPreviewActionButtons('pix_boleto');
  }
  return (preview?.buttons || []).map((btn) => {
    const type = String(btn.type || '').toUpperCase();
    const isUrl = type === 'URL' || type === 'WEB_URL';
    return {
      text:
        String(btn.text || '').toLowerCase().includes('pix')
          ? 'Copiar Chave Pix'
          : btn.text || btn.type || 'Ação',
      kind: isUrl ? 'link' : 'copy',
    };
  });
}
