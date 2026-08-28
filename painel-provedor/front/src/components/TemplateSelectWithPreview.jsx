import TemplateMessagePreview from './TemplateMessagePreview';
import { findTemplateByName, humanizeTemplateName } from '../utils/templatePreview';

export default function TemplateSelectWithPreview({
  templates = [],
  value = '',
  onChange,
  loading = false,
  emptyMessage = 'Nenhum template aprovado.',
  showPreview = true,
  layout = 'horizontal',
}) {
  const selected = findTemplateByName(templates, value);

  if (loading) {
    return <div className="text-xs text-white/45">Carregando templates...</div>;
  }

  if (templates.length === 0) {
    return <div className="text-xs text-white/45">{emptyMessage}</div>;
  }

  const selectEl = (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full min-w-0 max-w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-white/20"
    >
      <option value="" className="bg-[#1a1a1a] text-white">
        Selecione um template
      </option>
      {templates.map((template, index) => (
        <option
          key={template.id || template.name || `template-${index}`}
          value={template.name}
          className="bg-[#1a1a1a] text-white"
        >
          {humanizeTemplateName(template.name)} ({template.language || 'pt_BR'})
        </option>
      ))}
    </select>
  );

  if (!showPreview) {
    return <div className="min-w-0">{selectEl}</div>;
  }

  const previewEl = selected ? (
    <TemplateMessagePreview template={selected} compact={layout === 'horizontal'} />
  ) : (
    <p className="rounded-md border border-dashed border-white/15 bg-[#d8d1ca]/10 px-2 py-3 text-center text-[10px] text-white/45">
      {layout === 'horizontal'
        ? 'Prévia WhatsApp'
        : 'Selecione um template para ver a prévia no estilo WhatsApp'}
    </p>
  );

  if (layout === 'horizontal') {
    return (
      <div className="grid min-w-0 grid-cols-1 items-start gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,250px)]">
        <div className="min-w-0">{selectEl}</div>
        <div className="min-w-0">{previewEl}</div>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-2.5 overflow-hidden">
      {selectEl}
      {previewEl}
    </div>
  );
}
