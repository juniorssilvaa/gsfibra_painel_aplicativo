/** Card e prévia WhatsApp de templates da Meta (aba Modelos de Mensagem e Campanhas). */
import {
  getTemplateCardPreviewButtons,
  getTemplatePreviewModel,
  translateTemplateStatus,
} from '../utils/metaTemplatePreview';

const WA_LINK_BUTTON_ICON =
  'https://img.icons8.com/material-outlined/24/1a73e8/external-link.png';

export function PreviewActionButton({ btn, className = '', onClick }) {
  const isLink = btn.kind === 'link';
  return (
    <button
      type="button"
      className={`action-btn-custom${isLink ? ' wa-link-action-btn' : ''} ${className}`.trim()}
      onClick={onClick}
    >
      {isLink ? (
        <img className="w-4 h-4 shrink-0" src={WA_LINK_BUTTON_ICON} alt="" />
      ) : (
        <img
          className="w-4 h-4 shrink-0"
          src="https://img.icons8.com/ios/50/11a24d/copy--v1.png"
          alt="copy"
        />
      )}
      {btn.text}
    </button>
  );
}

/**
 * Prévia WhatsApp do template. `bodyText`, `headerText` e `headerImageUrl` substituem
 * o conteúdo do template (ex.: variáveis já preenchidas na campanha).
 */
export function MetaTemplatePreview({ template, bodyText, headerText, headerImageUrl, className = '' }) {
  const preview = getTemplatePreviewModel(template || {});
  const body = bodyText ?? preview.bodyText;
  const headerTitle = headerText ?? preview.headerText;
  const showImage = preview.headerFormat === 'IMAGE' && /^(https?:\/\/|blob:)/i.test(headerImageUrl || '');
  return (
    <div className={`wa-card-custom relative z-10 w-full max-w-[340px] mx-auto ${className}`.trim()}>
      <div className="wa-header-custom py-2 min-h-[36px]">
        <img
          className="w-4 h-4 shrink-0"
          src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg"
          alt=""
        />
        <span className="truncate min-w-0">{preview.displayTitle}</span>
      </div>
      <div className="wa-body-custom p-1.5 bg-[#e1f3fb]/20">
        <div className="box-custom shadow-sm border border-black/5">
          {preview.headerFormat === 'TEXT' && headerTitle && (
            <div className="wa-header-text-custom">
              {headerTitle}
            </div>
          )}
          {preview.showPdfHeader && (
            <div className="bg-[#f2f3f5] m-2 border border-[#d9dce0] rounded-md p-3 flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <img
                  className="w-8 shrink-0"
                  src="https://cdn.icon-icons.com/icons2/2107/PNG/512/file_type_pdf_icon_130274.png"
                  alt=""
                />
                <div className="min-w-0">
                  <div className="attach-title-custom truncate">Documento anexado</div>
                  <div className="attach-sub-custom">PDF</div>
                </div>
              </div>
              <div className="download-icon-custom shrink-0">
                <img
                  className="w-4 h-4"
                  src="https://img.icons8.com/material-outlined/24/22b15d/download--v1.png"
                  alt=""
                />
              </div>
            </div>
          )}
          {showImage ? (
            <img src={headerImageUrl} alt="" className="block w-full max-h-48 object-cover" />
          ) : preview.showMediaHeader && (
            <div className="m-2 flex h-24 items-center justify-center rounded-md border border-dashed border-gray-400 bg-[#dadada] text-[11px] font-semibold text-gray-600">
              {preview.headerFormat === 'VIDEO' ? 'Vídeo (cabeçalho)' : 'Imagem (cabeçalho)'}
            </div>
          )}
          {preview.hasOrderDetails && (
            <div className="payment-custom">
              <div className="payment-title-custom">
                <span>Pagar com</span>
                <div className="flex items-center gap-2">
                  <div
                    className="h-[17px] w-[17px] rounded-[2px] bg-black"
                    style={{
                      background:
                        'repeating-linear-gradient(to right, #000 0px, #000 2px, #fff 2px, #fff 3px)',
                    }}
                  />
                  <img
                    className="h-[26px] w-[26px] object-contain"
                    src="https://logospng.org/download/pix/logo-pix-icone-1024.png"
                    alt="Pix"
                  />
                </div>
              </div>
              <div className="total-custom">
                <span>Total</span>
                <span>R$ 129,90</span>
              </div>
            </div>
          )}
          <div className="message-custom">
            {String(body || '').trim() ? body : '—'}
          </div>
          {preview.footerText ? (
            <div className="border-t border-[#d7d7d7] bg-[#ececec] px-2.5 py-2 text-center text-[11px] text-gray-500">
              {preview.footerText}
            </div>
          ) : null}
        </div>
        {getTemplateCardPreviewButtons(preview).map((btn, bi) => (
          <PreviewActionButton
            key={bi}
            btn={btn}
            onClick={(e) => e.preventDefault()}
          />
        ))}
      </div>
    </div>
  );
}

const STATUS_BADGE_COLORS = {
  APPROVED: 'bg-green-500/10 text-green-500',
  REJECTED: 'bg-red-500/10 text-red-500',
};

/** Card completo (categoria, selo, status, idioma, prévia e nome técnico). `children` vai no rodapé. */
export function MetaTemplateCard({ template, className = '', children }) {
  const preview = getTemplatePreviewModel(template);
  const langLabel = template.language === 'pt_BR' ? 'PT-BR' : template.language || '—';
  return (
    <div className={`template-card group flex flex-col ${className}`.trim()}>
      <div className="relative z-10 mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="template-title truncate">{preview.categoryLabel}</div>
          <div className="badge-template-tab">{preview.badgeLabel}</div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {template.status && (
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-tighter ${
                STATUS_BADGE_COLORS[template.status] || 'bg-yellow-500/10 text-yellow-500'
              }`}
            >
              {translateTemplateStatus(template.status)}
            </span>
          )}
          <span className="text-[10px] text-gray-500">{langLabel}</span>
        </div>
      </div>

      <MetaTemplatePreview template={template} />

      <p
        className="relative z-10 mt-2 truncate text-center text-[11px] font-bold font-mono text-orange-500"
        title={template.name}
      >
        {template.name}
      </p>
      {children}
    </div>
  );
}
