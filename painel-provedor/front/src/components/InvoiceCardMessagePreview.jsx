import { FileText } from 'lucide-react';
import '../styles/wa-template-preview.css';

const WA_ICON = 'https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg';
const PIX_ICON = 'https://logospng.org/download/pix/logo-pix-icone-1024.png';
const COPY_ICON = 'https://img.icons8.com/ios/50/11a24d/copy--v1.png';

/** Escapa HTML e aplica *negrito* estilo WhatsApp para a prévia. */
export function formatWhatsAppPreviewHtml(text) {
  const raw = String(text || '');
  const escaped = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>');
}

export const INVOICE_PREVIEW_SAMPLES = {
  vencimento: '10.09.2026',
  valor: 'R$ 158,75',
  valor_original: 'R$ 149,90',
  multa: 'R$ 7,50',
  juros: 'R$ 1,35',
  // Exemplo com atraso — igual ao {{valores_texto}} que o cliente recebe nesse caso
  valores_texto:
    '*Valor original:* R$ 149,90\n' +
    '*Multa:* R$ 7,50\n' +
    '*Juros:* R$ 1,35\n' +
    '*Valor atualizado:* R$ 158,75',
  fatura_id: '3842',
  nome_cliente: 'Maria',
  nome_provedor: 'NIO NET',
  instrucoes:
    '*Pagamento via PIX*\n\n' +
    '1. Copie o código PIX abaixo;\n' +
    '2. Abra o aplicativo do seu banco;\n' +
    '3. Cole o código e finalize o pagamento.',
};

export function renderInvoiceTemplatePreview(template, samples = INVOICE_PREVIEW_SAMPLES) {
  let msg = template || '';
  Object.entries(samples).forEach(([key, value]) => {
    const re = new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'gi');
    msg = msg.replace(re, String(value ?? ''));
  });
  // Variáveis desconhecidas ficam visíveis
  return msg;
}

/**
 * Prévia do card Meta (order_details) — mesmo visual de Criar Template.
 */
export default function InvoiceCardMessagePreview({
  bodyText,
  title = 'Fatura',
  faturaId = '2715',
  total = 'R$ 100,00',
  footer = 'NIO NET',
  showPix = true,
  showBoleto = false,
}) {
  const html = formatWhatsAppPreviewHtml(
    (bodyText || '').trim() || 'Preencha o texto principal da mensagem'
  );

  return (
    <div className="min-w-0">
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-[#e5ddd5] p-6 pt-10 shadow-inner min-h-[420px] flex flex-col items-center">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")',
          }}
        />

        <div className="wa-tpl-card relative z-10 w-full max-w-[320px] shadow-2xl">
          <div className="wa-tpl-header">
            <img className="h-4 w-4 shrink-0" src={WA_ICON} alt="" />
            <span className="min-w-0 truncate font-bold tracking-tight">{title}</span>
          </div>

          <div className="wa-tpl-body">
            <div className="wa-tpl-box shadow-sm">
              <div className="border-b border-dashed border-[#8d9197] px-2.5 py-1.5 text-[11px] text-[#646464]">
                Nº da cobrança: {faturaId}
              </div>

              <div className="m-2 flex items-center justify-between rounded-md border border-[#d9dce0] bg-[#f2f3f5] p-3">
                <div className="flex min-w-0 items-center gap-3">
                  <FileText className="h-8 w-8 shrink-0 text-red-500" />
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-bold text-black">Fatura.pdf</div>
                    <div className="text-[11px] text-[#444]">PDF</div>
                  </div>
                </div>
              </div>

              <div className="wa-tpl-payment">
                <div className="wa-tpl-payment-title">
                  <span>Pagar com</span>
                  <div className="flex items-center gap-2">
                    {showBoleto && (
                      <div
                        className="h-[17px] w-[17px] rounded-[2px]"
                        style={{
                          background:
                            'repeating-linear-gradient(to right, #000 0px, #000 2px, #fff 2px, #fff 3px)',
                        }}
                        title="Boleto"
                      />
                    )}
                    {showPix && (
                      <img className="h-[22px] w-[22px] object-contain" src={PIX_ICON} alt="Pix" />
                    )}
                  </div>
                </div>
                <div className="wa-tpl-total">
                  <span>Total</span>
                  <span>{total}</span>
                </div>
              </div>

              <div
                className="wa-tpl-message"
                style={{ maxHeight: '14rem', fontStyle: 'normal' }}
                dangerouslySetInnerHTML={{ __html: html }}
              />

              {footer ? <div className="wa-tpl-footer">{footer}</div> : null}
            </div>

            {showPix && (
              <div className="wa-tpl-action" role="presentation">
                <img className="h-4 w-4 shrink-0" src={COPY_ICON} alt="" />
                <span>Copiar código Pix</span>
              </div>
            )}
            {showBoleto && (
              <div className="wa-tpl-action" role="presentation">
                <img className="h-4 w-4 shrink-0" src={COPY_ICON} alt="" />
                <span>Copiar código do boleto</span>
              </div>
            )}
          </div>
        </div>
      </div>
      <p className="wa-tpl-caption mt-2">Prévia do card enviado ao cliente</p>
    </div>
  );
}
