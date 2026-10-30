const PAGE_W = 595.28;
const PAGE_H = 841.89;

const WINANSI = {
  Á: 0xc1, À: 0xc0, Â: 0xc2, Ã: 0xc3, Ä: 0xc4,
  É: 0xc9, È: 0xc8, Ê: 0xca, Ë: 0xcb,
  Í: 0xcd, Ì: 0xcc, Î: 0xce, Ï: 0xcf,
  Ó: 0xd3, Ò: 0xd2, Ô: 0xd4, Õ: 0xd5, Ö: 0xd6,
  Ú: 0xda, Ù: 0xd9, Û: 0xdb, Ü: 0xdc,
  Ç: 0xc7, Ñ: 0xd1,
  á: 0xe1, à: 0xe0, â: 0xe2, ã: 0xe3, ä: 0xe4,
  é: 0xe9, è: 0xe8, ê: 0xea, ë: 0xeb,
  í: 0xed, ì: 0xec, î: 0xee, ï: 0xef,
  ó: 0xf3, ò: 0xf2, ô: 0xf4, õ: 0xf5, ö: 0xf6,
  ú: 0xfa, ù: 0xf9, û: 0xfb, ü: 0xfc,
  ç: 0xe7, ñ: 0xf1,
  '°': 0xb0, 'º': 0xba, 'ª': 0xaa,
};

function toWinAnsi(text) {
  let out = '';
  for (const ch of String(text ?? '')) {
    const code = ch.codePointAt(0);
    if (code === 40 || code === 41 || code === 92) {
      out += `\\${ch}`;
    } else if (code < 128) {
      out += ch;
    } else if (WINANSI[ch] != null) {
      out += `\\${WINANSI[ch].toString(8).padStart(3, '0')}`;
    } else {
      out += '?';
    }
  }
  return out;
}

function hexRgb(hex) {
  const raw = String(hex || '#334155').replace('#', '');
  const full = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw;
  const n = Number.parseInt(full.slice(0, 6), 16);
  if (Number.isNaN(n)) return [0.2, 0.25, 0.33];
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function rgbOp(hex, stroke = false) {
  const [r, g, b] = hexRgb(hex);
  return `${r.toFixed(3)} ${g.toFixed(3)} ${b.toFixed(3)} ${stroke ? 'RG' : 'rg'}`;
}

function wrapText(text, maxChars) {
  const words = String(text || '').split(/\s+/).filter(Boolean);
  const lines = [];
  let current = '';
  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  });
  if (current) lines.push(current);
  return lines.length ? lines : [''];
}

function jpegSize(bytes) {
  let i = 2;
  while (i < bytes.length - 8) {
    if (bytes[i] !== 0xff) break;
    const marker = bytes[i + 1];
    const len = (bytes[i + 2] << 8) + bytes[i + 3];
    if (marker === 0xc0 || marker === 0xc1 || marker === 0xc2) {
      return { height: (bytes[i + 5] << 8) + bytes[i + 6], width: (bytes[i + 7] << 8) + bytes[i + 8] };
    }
    i += 2 + len;
  }
  return { width: 1100, height: 420 };
}

export class SimplePdf {
  constructor() {
    this.pages = [];
    this.addPage();
  }

  addPage() {
    this.current = { ops: [], images: [] };
    this.pages.push(this.current);
    this.cursor = PAGE_H - 36;
    return this;
  }

  ensure(h) {
    if (this.cursor - h < 50) {
      this.addPage();
    }
  }

  fillRect(x, y, w, h, color) {
    this.current.ops.push(rgbOp(color), `${x.toFixed(2)} ${y.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)} re f`);
  }

  strokeRect(x, y, w, h, color) {
    this.current.ops.push(rgbOp(color, true), '0.6 w', `${x.toFixed(2)} ${y.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)} re S`);
  }

  dot(x, y, r, color) {
    this.current.ops.push(rgbOp(color), `${x.toFixed(2)} ${y.toFixed(2)} ${r.toFixed(2)} 0 360 arc f`);
  }

  text(str, x, y, { size = 11, bold = false, color = '#0f172a' } = {}) {
    const font = bold ? 'F2' : 'F1';
    this.current.ops.push(
      rgbOp(color),
      'BT',
      `/${font} ${size} Tf`,
      `${x.toFixed(2)} ${y.toFixed(2)} Td`,
      `(${toWinAnsi(str)}) Tj`,
      'ET',
    );
  }

  paragraph(str, x, { size = 10, width = 515, line = 13, color = '#334155', bold = false } = {}) {
    const maxChars = Math.max(18, Math.floor(width / (size * 0.52)));
    const lines = wrapText(str, maxChars);
    this.ensure(lines.length * line + 4);
    lines.forEach((item) => {
      this.text(item, x, this.cursor, { size, bold, color });
      this.cursor -= line;
    });
    return lines.length * line;
  }

  addJpeg(dataUrl, x, y, displayW, displayH) {
    const match = String(dataUrl || '').match(/^data:image\/jpeg;base64,(.+)$/i);
    if (!match) return;
    const binary = atob(match[1]);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const { width, height } = jpegSize(bytes);
    const name = `Im${this.current.images.length + 1}`;
    this.current.images.push({ name, bytes, width, height });
    this.current.ops.push(
      'q',
      `${displayW.toFixed(2)} 0 0 ${displayH.toFixed(2)} ${x.toFixed(2)} ${y.toFixed(2)} cm`,
      `/${name} Do`,
      'Q',
    );
  }

  build() {
    const encoder = new TextEncoder();
    const objects = [];
    const add = (body, stream) => {
      objects.push({ body, stream: stream || null });
      return objects.length;
    };

    const f1 = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n');
    const f2 = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\n');

    const pageMeta = this.pages.map((page) => {
      const imgs = page.images.map((img) => ({
        name: img.name,
        id: add(
          `<< /Type /XObject /Subtype /Image /Width ${img.width} /Height ${img.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${img.bytes.length} >>\n`,
          img.bytes,
        ),
      }));
      const content = `${page.ops.join('\n')}\n`;
      const contentBytes = encoder.encode(content);
      const contentId = add(`<< /Length ${contentBytes.length} >>\n`, contentBytes);
      return { imgs, contentId };
    });

    const pageIds = [];
    pageMeta.forEach(() => pageIds.push(objects.length + pageIds.length + 1));
    const pagesId = objects.length + pageMeta.length + 1;

    pageMeta.forEach((meta) => {
      const xobj = meta.imgs.map((im) => `/${im.name} ${im.id} 0 R`).join(' ');
      add(
        `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Contents ${meta.contentId} 0 R /Resources << /Font << /F1 ${f1} 0 R /F2 ${f2} 0 R >> /XObject << ${xobj} >> >> >>\n`,
      );
    });

    const kids = pageIds.map((id) => `${id} 0 R`).join(' ');
    add(`<< /Type /Pages /Count ${pageIds.length} /Kids [ ${kids} ] >>\n`);
    const catalogId = add(`<< /Type /Catalog /Pages ${pagesId} 0 R >>\n`);

    const parts = [];
    const offsets = [0];
    let pos = 0;
    const write = (data) => {
      const bytes = typeof data === 'string' ? encoder.encode(data) : data;
      parts.push(bytes);
      pos += bytes.length;
    };

    write('%PDF-1.4\n');
    objects.forEach((obj, i) => {
      offsets.push(pos);
      write(`${i + 1} 0 obj\n`);
      write(obj.body);
      if (obj.stream) {
        write('stream\n');
        write(obj.stream);
        write('\nendstream\n');
      }
      write('endobj\n');
    });

    const xrefPos = pos;
    write(`xref\n0 ${objects.length + 1}\n`);
    write('0000000000 65535 f \n');
    offsets.slice(1).forEach((off) => write(`${String(off).padStart(10, '0')} 00000 n \n`));
    write(`trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xrefPos}\n%%EOF`);

    const total = parts.reduce((n, p) => n + p.length, 0);
    const out = new Uint8Array(total);
    let cursor = 0;
    parts.forEach((p) => {
      out.set(p, cursor);
      cursor += p.length;
    });
    return out;
  }

  download(filename) {
    const blob = new Blob([this.build()], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}

export const PDF_PAGE = { W: PAGE_W, H: PAGE_H, MARGIN: 40 };
