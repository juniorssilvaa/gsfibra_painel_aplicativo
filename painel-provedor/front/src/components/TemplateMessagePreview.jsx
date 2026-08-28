import { FileText, Image as ImageIcon } from 'lucide-react';
import {
  getTemplatePreviewModel,
  getTemplateCardPreviewButtons,
} from '../utils/templatePreview';
import '../styles/wa-template-preview.css';

const WA_ICON =
  'https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg';
const WA_LINK_BUTTON_ICON =
  'https://img.icons8.com/material-outlined/24/1a73e8/external-link.png';
const WA_COPY_BUTTON_ICON =
  'https://img.icons8.com/ios/50/11a24d/copy--v1.png';

function PreviewActionButton({ btn }) {
  const isLink = btn.kind === 'link';
  return (
    <div
      className={`wa-tpl-action${isLink ? ' wa-tpl-action--link' : ''}`}
      role="presentation"
    >
      <img
        className="h-4 w-4 shrink-0"
        src={isLink ? WA_LINK_BUTTON_ICON : WA_COPY_BUTTON_ICON}
        alt=""
      />
      <span className="truncate">{btn.text}</span>
    </div>
  );
}

export default function TemplateMessagePreview({ template, compact = false }) {
  if (!template) return null;

  const preview = getTemplatePreviewModel(template);
  const previewButtons = getTemplateCardPreviewButtons(preview);

  return (
    <div className="min-w-0 overflow-hidden">
      <div className={`wa-tpl-card${compact ? ' wa-tpl-card--compact' : ''}`}>
        <div className="wa-tpl-header">
          <img className="h-4 w-4 shrink-0" src={WA_ICON} alt="" />
          <span className="min-w-0 truncate" title={preview.displayTitle}>
            {preview.displayTitle}
          </span>
        </div>

        <div className="wa-tpl-body">
          <div className="wa-tpl-box shadow-sm">
            {preview.showTextHeader && (
              <div className="wa-tpl-header-text">{preview.headerText}</div>
            )}

            {preview.showPdfHeader && (
              <div className="m-2 flex items-center justify-between rounded-md border border-[#d9dce0] bg-[#f2f3f5] p-3">
                <div className="flex min-w-0 items-center gap-3">
                  <FileText className="h-8 w-8 shrink-0 text-red-500" />
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-bold text-black">
                      Documento anexado
                    </div>
                    <div className="text-[11px] text-[#444]">PDF</div>
                  </div>
                </div>
              </div>
            )}

            {preview.showMediaHeader && (
              <div className="m-2 flex h-20 items-center justify-center rounded-md border border-dashed border-gray-400 bg-[#dadada] text-[11px] font-semibold text-gray-600">
                <ImageIcon className="mr-1.5 h-3.5 w-3.5" />
                {preview.headerFormat === 'VIDEO' ? 'Vídeo (cabeçalho)' : 'Imagem (cabeçalho)'}
              </div>
            )}

            {preview.hasOrderDetails && (
              <div className="wa-tpl-payment">
                <div className="wa-tpl-payment-title">
                  <span>Pagar com</span>
                  <img
                    className="h-[22px] w-[22px] object-contain"
                    src="https://logospng.org/download/pix/logo-pix-icone-1024.png"
                    alt="Pix"
                  />
                </div>
                <div className="wa-tpl-total">
                  <span>Total</span>
                  <span>R$ —</span>
                </div>
              </div>
            )}

            <div className={`wa-tpl-message custom-scrollbar${compact ? ' wa-tpl-message--compact' : ''}`}>
              {preview.bodyText.trim() || 'Preencha o texto principal da mensagem'}
            </div>

            {preview.footerText ? (
              <div className="wa-tpl-footer">{preview.footerText}</div>
            ) : null}
          </div>

          {previewButtons.map((btn, i) => (
            <PreviewActionButton key={`${btn.kind}-${btn.text}-${i}`} btn={btn} />
          ))}
        </div>
      </div>

      <p className="wa-tpl-caption">Prévia enviada ao cliente</p>
    </div>
  );
}
