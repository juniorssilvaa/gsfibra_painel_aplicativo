import fs from 'fs';
import path from 'path';

const root = path.resolve('src');
const successKw = /sucesso|salv|enviad|criad|exclu|transferid|encerrad|importad|atribu|confirm|alterad|redefinid|desativad|ativad|aprovad|conclu/i;

function walk(dir, files = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory() && e.name !== 'node_modules') walk(p, files);
    else if (/\.(jsx|js)$/.test(e.name) && !p.includes(`${path.sep}lib${path.sep}notify`)) files.push(p);
  }
  return files;
}

for (const file of walk(root)) {
  let s = fs.readFileSync(file, 'utf8');
  if (!s.includes('alert(')) continue;

  if (!s.includes('lib/notify')) {
    const rel = path.relative(path.dirname(file), path.join(root, 'lib', 'notify')).replace(/\\/g, '/');
    const importPath = rel.startsWith('.') ? rel : `./${rel}`;
    const importLine = `import { toast } from '${importPath}';\n`;
    const firstImport = s.match(/^import .+;\r?\n/m);
    if (firstImport) s = s.replace(firstImport[0], firstImport[0] + importLine);
    else s = importLine + s;
  }

  s = s.replace(/alert\(([\s\S]*?)\);/g, (full, inner) => {
    if (successKw.test(inner)) return `toast.success(${inner});`;
    return `toast.error(${inner});`;
  });

  fs.writeFileSync(file, s);
  console.log('updated', path.relative(root, file));
}
