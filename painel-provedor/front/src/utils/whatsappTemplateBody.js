/**
 * Ajusta o corpo do template às regras da Meta (variável não no início/fim absoluto).
 * Espelha normalize_body_text_for_meta no backend.
 */

/** Texto fixo exigido pela Meta na criação de templates ORDER_DETAILS (BR). */
export const META_ORDER_DETAILS_BUTTON_TEXT = 'Copy Pix code';

const MIN_TRAILING = 8;
const DEFAULT_TRAIL = 'Para sua comodidade, anexamos uma cópia da sua fatura.';

/** Números das variáveis {{n}} na ordem em que aparecem (sem repetir). */
export function extractVariableNumbers(text) {
  const ordered = [];
  const seen = new Set();
  for (const m of (text || '').matchAll(/\{\{(\d+)\}\}/g)) {
    const n = parseInt(m[1], 10);
    if (!Number.isNaN(n) && !seen.has(n)) {
      seen.add(n);
      ordered.push(n);
    }
  }
  return ordered;
}

function stripAccents(text) {
  return (text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function lineContextBeforeVar(bodyText, varIndex) {
  const marker = `{{${varIndex}}}`;
  const pos = (bodyText || '').indexOf(marker);
  if (pos < 0) return '';
  const lineStart = bodyText.lastIndexOf('\n', pos);
  const start = lineStart < 0 ? 0 : lineStart + 1;
  return stripAccents(bodyText.slice(start, pos)).toLowerCase();
}

/** Inferência do tipo de {{n}} pelo rótulo no template (valor, vencimento, nome…). */
export function classifyTemplateVariableSlot(bodyText, varIndex) {
  const text = bodyText || '';
  const marker = `{{${varIndex}}}`;
  const pos = text.indexOf(marker);
  if (pos < 0) return 'generic';

  const lineBefore = lineContextBeforeVar(text, varIndex);
  const closeBefore = stripAccents(text.slice(Math.max(0, pos - 28), pos)).toLowerCase();
  const before = stripAccents(text.slice(Math.max(0, pos - 55), pos)).toLowerCase();
  const after = stripAccents(text.slice(pos + marker.length, pos + marker.length + 40)).toLowerCase();

  const classify = (ctx) => {
    if (/valor|r\$/.test(ctx) && !/vencimento\s+original/.test(ctx)) return 'money';
    if (/vencimento|venc\.|venceu|vence em/.test(ctx)) return 'date';
    if (/conta\s*:|cliente\s*:|ol[aá]|nome|prezado/.test(ctx)) return 'name';
    if (/fatura/.test(ctx)) return 'title';
    return null;
  };

  return (
    classify(lineBefore)
    || classify(closeBefore)
    || classify(`${before} ${after}`)
    || 'generic'
  );
}

const DEFAULT_SAMPLE_BY_SLOT = {
  name: 'Nome Cliente',
  money: '70,00',
  date: '13/06/2026',
  title: '72418',
  generic: 'Exemplo',
};

/** Exemplo padrão para pré-visualização / envio à Meta conforme o contexto de {{n}}. */
export function inferVariableSampleExample(bodyText, varIndex) {
  const slot = classifyTemplateVariableSlot(bodyText, varIndex);
  return DEFAULT_SAMPLE_BY_SLOT[slot] || DEFAULT_SAMPLE_BY_SLOT.generic;
}

export function buildDefaultVariableSamples(bodyText) {
  const samples = {};
  for (const n of extractVariableNumbers(bodyText)) {
    samples[n] = { example: inferVariableSampleExample(bodyText, n) };
  }
  return samples;
}

/** Substitui {{n}} pelos exemplos digitados (pré-visualização). */
export function replaceVariablesWithExamples(text, variableSamples = {}) {
  if (!text) return '';
  return text.replace(/\{\{(\d+)\}\}/g, (match, varNum) => {
    const sample = variableSamples[parseInt(varNum, 10)];
    const ex = (sample?.example ?? sample ?? '').toString().trim();
    return ex || match;
  });
}

/** Variáveis {{n}} usadas no cabeçalho e no corpo (ordenadas, sem repetir). */
export function collectTemplateVariableNumbers(headerText, bodyText) {
  const seen = new Set();
  const ordered = [];
  for (const text of [headerText, bodyText]) {
    for (const n of extractVariableNumbers(text || '')) {
      if (!seen.has(n)) {
        seen.add(n);
        ordered.push(n);
      }
    }
  }
  return ordered.sort((a, b) => a - b);
}

/** Exemplos para cabeçalho TEXT com variáveis (Meta: header_text). */
export function buildHeaderTextExamples(headerText, variableSamples = {}) {
  const nums = [...new Set(extractVariableNumbers(headerText || ''))].sort((a, b) => a - b);
  if (!nums.length) return null;
  const row = nums.map((n) => {
    const ex = (variableSamples[n]?.example ?? '').toString().trim();
    return ex || `Exemplo ${n}`;
  });
  return { header_text: [row] };
}

/** Array body_text para a Meta: um valor por variável, na ordem {{1}}, {{2}}, … */
export function buildBodyTextExamples(bodyText, variableSamples = {}) {
  const nums = [...new Set(extractVariableNumbers(bodyText))].sort((a, b) => a - b);
  if (!nums.length) return null;
  const row = nums.map((n) => {
    const sample = variableSamples[n];
    const ex = (sample?.example ?? '').toString().trim();
    return ex || `Exemplo ${n}`;
  });
  return { body_text: [row] };
}

export function normalizeWhatsAppBodyForMeta(text) {
  const warnings = [];
  let body = (text || '').trim();
  if (!body) return { text: body, warnings };

  const matches = [...body.matchAll(/\{\{(\d+)\}\}/g)];
  if (!matches.length) return { text: body, warnings };

  const first = matches[0];
  const prefix = body.slice(0, first.index).trim();

  // Só altera se a variável for o primeiro caractere do template (sem "Olá, {{1}}." etc.)
  if (first.index === 0 || !prefix) {
    body = `Olá, ${body.slice(first.index).trimStart()}`;
    warnings.push('Saudação adicionada antes da primeira variável.');
  }

  const last = matches[matches.length - 1];
  const afterLastIdx = last.index + last[0].length;
  const suffix = body.slice(afterLastIdx).trim();
  const meaningful = suffix.replace(/^[\s.,;:!?\-—]+|[\s.,;:!?\-—]+$/g, '');
  if (!meaningful || meaningful.length < MIN_TRAILING) {
    body = `${body.slice(0, afterLastIdx).trimEnd()}. ${DEFAULT_TRAIL}`;
    warnings.push('Texto final adicionado após a última variável (exigência da Meta).');
  }

  return { text: body.trim(), warnings };
}

/** Domínios de placeholder que a Meta costuma bloquear na revisão (erro 368). */
const META_FLAGGED_URL_HOSTS = [
  'exemplo.com',
  'example.org',
  'seudominio.com',
  'seudominio.com.br',
  'teste.com',
  'dominio.com.br',
];

function parseTemplateUrl(url) {
  const raw = (url || '').trim();
  if (!raw) return null;
  try {
    return new URL(raw.includes('://') ? raw : `https://${raw}`);
  } catch {
    return null;
  }
}

/** Troca domínios de exemplo bloqueados por www.example.com (reservado IANA). */
export function sanitizeMetaTemplateUrl(url) {
  const raw = (url || '').trim();
  if (!raw) return raw;

  const parsed = parseTemplateUrl(raw);
  if (parsed) {
    const host = parsed.hostname.toLowerCase();
    const flagged = META_FLAGGED_URL_HOSTS.some(
      (h) => host === h || host.endsWith(`.${h}`),
    );
    if (flagged) {
      parsed.hostname = 'www.example.com';
      return parsed.toString();
    }
    return raw;
  }

  return raw
    .replace(/:\/\/(www\.)?exemplo\.com/gi, '://www.example.com')
    .replace(/:\/\/(www\.)?seudominio\.com(\.br)?/gi, '://www.example.com');
}

/** Exemplo de URL para botão dinâmico na criação do template na Meta. */
export function buildMetaUrlButtonExample(url, sampleUrl) {
  const base = sanitizeMetaTemplateUrl(normalizeDynamicTemplateUrl(url));
  const sample = (sampleUrl || '').trim();
  if (sample) {
    // Meta exige que o exemplo siga o formato da URL do template (sem query extra após o placeholder).
    let cleaned = sample.replace(/[?&]txt=1\b/gi, '').replace(/[?&]$/g, '');
    if (cleaned && !/^https?:\/\//i.test(cleaned)) {
      cleaned = `https://${cleaned}`;
    }
    return [sanitizeMetaTemplateUrl(cleaned)];
  }
  if (/\{\{\s*1\s*\}\}/.test(base)) {
    // Sufixo genérico (UUID-like) — melhor que "sample-receipt" para links de validação
    return [base.replace(/\{\{\s*1\s*\}\}/g, 'e988ed73-c16e-4c3f-96ad-3db2e10d9631')];
  }
  return [base];
}

/**
 * Garante URL dinâmica no formato exigido pela Meta:
 * https://dominio/caminho/{{1}}  — {{1}} deve ser o ÚLTIMO token (nada depois).
 */
export function normalizeDynamicTemplateUrl(url) {
  let raw = sanitizeMetaTemplateUrl((url || '').trim());
  if (!raw) return raw;

  // Remover espaços em {{ 1 }}
  raw = raw.replace(/\{\{\s*1\s*\}\}/g, '{{1}}');

  // Nada pode vir depois de {{1}} (barra, query, etc.)
  const idx = raw.indexOf('{{1}}');
  if (idx >= 0) {
    raw = raw.slice(0, idx + '{{1}}'.length);
    return raw;
  }

  // Sem placeholder: acrescentar /{{1}} (sem barra duplicada)
  return `${raw.replace(/\/$/, '')}/{{1}}`;
}

/** Valida URL dinâmica antes de enviar à Meta. Retorna mensagem de erro ou null. */
export function validateDynamicTemplateUrl(url) {
  const raw = (url || '').trim();
  if (!raw) return 'Informe a URL do botão.';
  if (!/^https:\/\//i.test(raw.includes('://') ? raw : `https://${raw}`)) {
    return 'A URL do botão deve começar com https://';
  }
  const normalized = normalizeDynamicTemplateUrl(raw);
  if (!normalized.endsWith('{{1}}')) {
    return 'A URL dinâmica deve terminar exatamente com {{1}} (sem barra nem parâmetros depois).';
  }
  const staticPart = normalized.slice(0, -'{{1}}'.length);
  if (!staticPart || staticPart.length < 12) {
    return 'Informe a parte fixa da URL antes de {{1}} (ex.: https://atendimento.seudominio.com/public/contato/validacao/).';
  }
  if (/\{\{/.test(staticPart)) {
    return 'A URL do botão só pode ter uma variável: {{1}} no final.';
  }
  return null;
}

export function isMetaFlaggedTemplateUrl(url) {
  const parsed = parseTemplateUrl(url);
  if (!parsed) return false;
  const host = parsed.hostname.toLowerCase();
  return META_FLAGGED_URL_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
}
