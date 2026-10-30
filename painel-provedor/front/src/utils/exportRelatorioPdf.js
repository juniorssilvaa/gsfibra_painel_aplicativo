import {
  Chart,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { PDF_PAGE, SimplePdf } from './simplePdf';

Chart.register(CategoryScale, LinearScale, PointElement, LineElement, LineController, Filler, Tooltip, Legend);

function formatBrDate(iso) {
  return String(iso || '').split('-').reverse().join('/');
}

export function seriesValuesForKey(series, key) {
  return (series || []).map((row) => Number(row[key] || 0));
}

export function describeVolumeTrend(values) {
  const nums = (values || []).map((v) => Number(v) || 0);
  if (nums.length < 2) {
    return { code: 'short', text: 'período curto demais para comparar evolução' };
  }
  const mid = Math.ceil(nums.length / 2);
  const first = nums.slice(0, mid).reduce((a, b) => a + b, 0);
  const second = nums.slice(mid).reduce((a, b) => a + b, 0);
  const avgFirst = first / mid;
  const avgSecond = second / (nums.length - mid || 1);

  if (avgFirst === 0 && avgSecond === 0) {
    return { code: 'empty', text: 'não teve volume no período' };
  }
  if (avgFirst === 0 && avgSecond > 0) {
    return { code: 'up', text: 'passou a ter volume na segunda metade do período' };
  }
  if (avgSecond === 0) {
    return { code: 'down', text: 'zerou o volume na segunda metade do período' };
  }
  const delta = ((avgSecond - avgFirst) / avgFirst) * 100;
  if (delta >= 15) {
    return { code: 'up', text: `aumentou o volume (cerca de ${Math.round(delta)}% a mais na segunda metade)` };
  }
  if (delta <= -15) {
    return { code: 'down', text: `diminuiu o volume (cerca de ${Math.round(Math.abs(delta))}% a menos na segunda metade)` };
  }
  return { code: 'stable', text: 'manteve o volume estável, sem mudança relevante' };
}

function renderChartJpeg({ labels, datasets }) {
  const width = 1100;
  const height = 420;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: (datasets || []).map((ds) => ({
        label: ds.label,
        data: ds.data,
        borderColor: ds.borderColor,
        backgroundColor: ds.backgroundColor || `${ds.borderColor}33`,
        fill: true,
        tension: 0.35,
        pointRadius: 2,
        borderWidth: 2,
      })),
    },
    options: {
      animation: false,
      responsive: false,
      maintainAspectRatio: false,
      devicePixelRatio: 1,
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#334155', boxWidth: 10, usePointStyle: true, font: { size: 11 } },
        },
      },
      scales: {
        x: {
          ticks: { color: '#475569' },
          grid: { color: '#e2e8f0' },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#475569', precision: 0 },
          grid: { color: '#e2e8f0' },
        },
      },
    },
  });
  chart.draw();
  ctx.save();
  ctx.globalCompositeOperation = 'destination-over';
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
  const jpeg = canvas.toDataURL('image/jpeg', 0.92);
  chart.destroy();
  return jpeg;
}

export async function downloadRelatorioPdf({
  title,
  periodFrom,
  periodTo,
  kpis = [],
  intro = '',
  chart,
  table,
  analyses = [],
  filename,
}) {
  const pdf = new SimplePdf();
  const { W, H, MARGIN } = PDF_PAGE;
  const innerW = W - MARGIN * 2;
  const generatedAt = new Date().toLocaleString('pt-BR');
  const periodLabel = `de ${formatBrDate(periodFrom)} até ${formatBrDate(periodTo)}`;

  pdf.fillRect(0, H - 78, W, 78, '#0f172a');
  pdf.text(title || 'Relatório', MARGIN, H - 42, { size: 18, bold: true, color: '#ffffff' });
  pdf.text(periodLabel, MARGIN, H - 62, { size: 11, color: '#cbd5e1' });
  pdf.cursor = H - 96;

  if (kpis.length) {
    const gap = 8;
    const boxW = (innerW - gap * (kpis.length - 1)) / kpis.length;
    pdf.ensure(46);
    const top = pdf.cursor;
    kpis.forEach((kpi, i) => {
      const x = MARGIN + i * (boxW + gap);
      pdf.fillRect(x, top - 36, boxW, 40, '#f8fafc');
      pdf.strokeRect(x, top - 36, boxW, 40, '#e2e8f0');
      pdf.text(String(kpi.label || '').toUpperCase(), x + 8, top - 8, { size: 7, color: '#64748b' });
      pdf.text(String(kpi.value ?? '0'), x + 8, top - 26, { size: 13, bold: true, color: '#0f172a' });
    });
    pdf.cursor = top - 50;
  }

  if (intro) {
    pdf.paragraph(intro, MARGIN, { size: 10, width: innerW, line: 13, color: '#334155' });
    pdf.cursor -= 6;
  }

  if (chart?.labels?.length) {
    const imgH = 176;
    pdf.ensure(imgH + 22);
    pdf.text('Gráfico do período', MARGIN, pdf.cursor, { size: 12, bold: true });
    pdf.cursor -= 10;
    const jpeg = renderChartJpeg(chart);
    pdf.addJpeg(jpeg, MARGIN, pdf.cursor - imgH, innerW, imgH);
    pdf.cursor -= imgH + 16;
  }

  if (table?.columns?.length && table?.rows?.length) {
    const cols = table.columns;
    const colW = innerW / cols.length;
    const rowH = 16;
    pdf.ensure(rowH * 2);
    pdf.text(table.title || 'Detalhamento', MARGIN, pdf.cursor, { size: 12, bold: true });
    pdf.cursor -= 14;

    const drawHeader = () => {
      pdf.fillRect(MARGIN, pdf.cursor - 4, innerW, rowH, '#0f172a');
      cols.forEach((col, i) => {
        pdf.text(col.header, MARGIN + 4 + i * colW, pdf.cursor, { size: 8, bold: true, color: '#ffffff' });
      });
      pdf.cursor -= rowH;
    };

    drawHeader();
    table.rows.forEach((row, ri) => {
      pdf.ensure(rowH + 4);
      if (pdf.cursor > H - 90 && ri > 0 && pdf.cursor > H - 100) {
        /* keep going; ensure() already paginates */
      }
      if (pdf.cursor < 70) {
        pdf.addPage();
        drawHeader();
      }
      if (ri % 2 === 0) {
        pdf.fillRect(MARGIN, pdf.cursor - 4, innerW, rowH, '#f8fafc');
      }
      cols.forEach((col, i) => {
        pdf.text(String(row[col.key] ?? ''), MARGIN + 4 + i * colW, pdf.cursor, { size: 8, color: '#1e293b' });
      });
      pdf.cursor -= rowH;
    });
    pdf.cursor -= 10;
  }

  if (analyses.length) {
    pdf.ensure(40);
    pdf.text('Leitura do período', MARGIN, pdf.cursor, { size: 12, bold: true });
    pdf.cursor -= 16;
    analyses.forEach((item) => {
      pdf.ensure(36);
      pdf.fillRect(MARGIN, pdf.cursor - 2, 7, 7, item.color || '#64748b');
      pdf.text(item.name || '', MARGIN + 12, pdf.cursor, { size: 10, bold: true });
      pdf.cursor -= 14;
      pdf.paragraph(item.text || '', MARGIN + 12, { size: 9, width: innerW - 12, line: 12, color: '#334155' });
      pdf.cursor -= 8;
    });
  }

  pdf.pages.forEach((page, index) => {
    const current = pdf.current;
    pdf.current = page;
    pdf.text(`Gerado em ${generatedAt}  ·  página ${index + 1} de ${pdf.pages.length}`, MARGIN, 28, {
      size: 8,
      color: '#64748b',
    });
    pdf.current = current;
  });

  pdf.download(filename || `relatorio-${periodFrom}-${periodTo}.pdf`);
}
