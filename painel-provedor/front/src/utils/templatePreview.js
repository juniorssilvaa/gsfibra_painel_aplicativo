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

function findComponent(template, type) {
  const components = template?.components || [];
  return components.find((c) => String(c.type || '').toUpperCase() === type);
}

/** Substitui {{1}}, {{2}}… pelos exemplos da Meta quando existirem. */
export function fillTemplateVariables(text, exampleRow) {
  if (!text) return '';
  if (!Array.isArray(exampleRow) || exampleRow.length === 0) return text;
  return text.replace(/\{\{(\d+)\}\}/g, (_, n) => {
    const idx = parseInt(n, 10) - 1;
    return exampleRow[idx] != null ? String(exampleRow[idx]) : `{{${n}}}`;
  });
}

/** Deriva o que exibir na prévia WhatsApp a partir do JSON da Meta. */
export function getTemplatePreviewModel(template) {
  const header = findComponent(template, 'HEADER');
  const body = findComponent(template, 'BODY');
  const foot = findComponent(template, 'FOOTER');
  const btnBlock = findComponent(template, 'BUTTONS');
  const fmt = String(header?.format || '').toUpperCase();
  const buttons = btnBlock?.buttons || [];
  const hasOrderDetails = buttons.some(
    (b) => String(b.type || '').toUpperCase() === 'ORDER_DETAILS'
  );

  const headerExamples = header?.example?.header_text?.[0];
  const bodyExamples = body?.example?.body_text?.[0];

  const rawHeader = (header?.text || '').trim();
  const rawBody = body?.text ?? '';
  const rawFooter = (foot?.text || '').trim();

  return {
    displayTitle: humanizeTemplateName(template?.name),
    technicalName: template?.name || '',
    language: template?.language || 'pt_BR',
    category: template?.category || '',
    bodyText: fillTemplateVariables(rawBody, bodyExamples),
    footerText: fillTemplateVariables(rawFooter, null),
    headerText: fillTemplateVariables(rawHeader, headerExamples),
    headerFormat: fmt,
    buttons,
    hasOrderDetails,
    showPdfHeader: fmt === 'DOCUMENT',
    showMediaHeader: fmt === 'IMAGE' || fmt === 'VIDEO',
    showTextHeader: fmt === 'TEXT' && !!rawHeader,
  };
}

export function findTemplateByName(templates, name) {
  if (!name || !Array.isArray(templates)) return null;
  return templates.find((t) => t.name === name) || null;
}

export function orderDetailsPaymentFlags(orderDetailsType) {
  const t = orderDetailsType || 'pix_boleto';
  return {
    showPix: t === 'pix' || t === 'pix_boleto',
    showBoleto: t === 'boleto' || t === 'pix_boleto',
  };
}

/** Botões sintéticos na prévia quando o template usa ORDER_DETAILS (Pix/boleto). */
export function getOrderDetailsPreviewActionButtons(orderDetailsType = 'pix_boleto') {
  const { showPix, showBoleto } = orderDetailsPaymentFlags(orderDetailsType);
  const buttons = [];
  if (showPix) buttons.push({ text: 'Copiar Chave Pix', kind: 'copy' });
  if (showBoleto) buttons.push({ text: 'Copiar código de barras', kind: 'copy' });
  return buttons;
}

/** Botões exibidos no card de prévia WhatsApp (igual à galeria de modelos). */
export function getTemplateCardPreviewButtons(preview, orderDetailsType = 'pix_boleto') {
  if (preview?.hasOrderDetails) {
    return getOrderDetailsPreviewActionButtons(orderDetailsType);
  }
  return (preview?.buttons || [])
    .filter((btn) => String(btn?.type || '').toUpperCase() !== 'ORDER_DETAILS')
    .map((btn) => {
      const type = String(btn.type || '').toUpperCase();
      const isUrl = type === 'URL' || type === 'WEB_URL';
      const rawText = btn.text || btn.title || btn.type || 'Ação';
      return {
        text: String(rawText).toLowerCase().includes('pix') ? 'Copiar Chave Pix' : rawText,
        kind: isUrl ? 'link' : 'copy',
      };
    });
}
