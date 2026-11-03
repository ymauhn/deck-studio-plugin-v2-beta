// Build the single-file deck: deck/dist/nexus-go-defense.html (docs/BUILD.md §2).
// Usage: node deck/build.mjs [--images] [--fonts]
//        node deck/build.mjs --page <slides.html>   isolated page -> deck/build/harness/<name>.html
//        (only the slides in that file and the components they use; for component work, GIFs, PDFs)
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import * as esbuild from 'esbuild';

const require = createRequire(import.meta.url);
const DECK = path.dirname(fileURLToPath(import.meta.url));
const KIT = path.dirname(DECK);
const SRC = path.join(DECK, 'src');
const BUILD = path.join(DECK, 'build');
const DIST = path.join(DECK, 'dist', 'nexus-go-defense.html');
const TEX = path.join(KIT, 'source', 'thesis', 'dissertation.tex');
const argv = process.argv.slice(2);
const args = new Set(argv);
const PAGE = args.has('--page') ? path.resolve(argv[argv.indexOf('--page') + 1]) : null;
const read = (p) => fs.readFileSync(p, 'utf8');
fs.mkdirSync(BUILD, { recursive: true });
fs.mkdirSync(path.dirname(DIST), { recursive: true });

// 1. tables from the current .tex (the kit copy in data/ stays as shipped)
const TABLES = path.join(BUILD, 'thesis_tables.json');
if (fs.existsSync(TEX) && !(PAGE && fs.existsSync(TABLES))) execFileSync('python', ['-I', path.join(KIT, 'tools', 'extract_tables.py'), TEX, TABLES], { stdio: 'pipe' });
const tables = JSON.parse(read(fs.existsSync(TABLES) ? TABLES : path.join(KIT, 'data', 'thesis_tables.json')));
// stacking importances are stated in the text of §6.3.4, not in a table: parse them from the .tex
{
  const t = read(TEX).replace(/\s+/g, ' ');
  const num = (s) => +s.replace(/\\times ?10\^\{(-?\d+)\}/, 'e$1');
  const a = /decision tree assigns \$([\d.]+)\$ and \$([\d.]+)\$, the random forest \$([\d.]+)\$ and \$([\d.]+)\$/.exec(t);
  const b = /receive \$([^$]+)\$ and \$([\d.]+)\$ in the tree, \$([\d.]+)\$ and \$([\d.]+)\$ in the forest/.exec(t);
  if (!a || !b) throw new Error('stacking importances not found in dissertation.tex');
  tables.importances = {
    label: 'sec:res_late (text)', caption: 'Fitted feature importances of the tree-based stacking models',
    rows: [['Model', 'Fixed prob.', 'GNN prob.', 'IC', 'log-degree'],
      ['Decision tree', num(a[1]), num(a[2]), num(b[1]), num(b[2])],
      ['Random forest', num(a[3]), num(a[4]), num(b[3]), num(b[4])]],
  };
}

// 2. images
const IMG = path.join(BUILD, 'img');
if (args.has('--images') || !fs.existsSync(IMG)) {
  execFileSync('python', ['-I', path.join(DECK, 'tools', 'process_images.py'), path.join(KIT, 'source', 'thesis'), IMG], { stdio: 'inherit' });
}

// 2b. TikZ figures of §2.2.3 -> SVG (needs latex + dvisvgm, e.g. MiKTeX)
const SVGDIR = path.join(BUILD, 'svg');
if (args.has('--images') || !fs.existsSync(path.join(SVGDIR, 'tikz_mlp.svg'))) {
  execFileSync('python', ['-I', path.join(DECK, 'tools', 'render_tikz.py'), TEX, SVGDIR, path.join(BUILD, 'tikz-work')], { stdio: 'inherit' });
}

// 3. fonts: WOFF2 latin subsets from the Google Fonts CSS API, embedded as data URIs (cached)
const FONTS = path.join(BUILD, 'fonts.css');
const FONT_URL = 'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,600..700&family=IBM+Plex+Mono:wght@400;500&display=swap';
if (args.has('--fonts') || !fs.existsSync(FONTS)) {
  try {
    const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
    const css = await (await fetch(FONT_URL, { headers: { 'User-Agent': ua } })).text();
    const blocks = [...css.matchAll(/\/\*\s*([\w-]+)\s*\*\/\s*(@font-face\s*\{[^}]*\})/g)].filter((m) => m[1] === 'latin').map((m) => m[2]);
    const out = [];
    for (const b of blocks) {
      const url = /url\((https:[^)]+)\)/.exec(b)[1];
      const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
      out.push(b.replace(/url\([^)]+\)/, `url(data:font/woff2;base64,${buf.toString('base64')})`));
    }
    fs.writeFileSync(FONTS, out.join('\n'));
    console.log(`fonts: ${out.length} faces embedded`);
  } catch (e) {
    console.warn(`fonts: download failed (${e.message}); the deck falls back to system faces offline`);
    if (!fs.existsSync(FONTS)) fs.writeFileSync(FONTS, '');
  }
}

// 4. math: TeX -> SVG with MathJax, no runtime library
const { mathjax } = require('mathjax-full/js/mathjax.js');
const { TeX } = require('mathjax-full/js/input/tex.js');
const { SVG } = require('mathjax-full/js/output/svg.js');
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js');
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js');
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const mjdoc = mathjax.document('', { InputJax: new TeX({ packages: AllPackages }), OutputJax: new SVG({ fontCache: 'none' }) });
const decode = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&');
// data-tex keeps the source for the Beamer exporter (beamer/tools/extract.py)
const attr = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const tex2svg = (t, display) => adaptor.outerHTML(mjdoc.convert(decode(t).trim(), { display }))
  .replace('<mjx-container', `<mjx-container data-tex="${attr(decode(t).trim())}"`);
let nMath = 0;
const renderMath = (html) => html
  .replace(/<div class="m d">([\s\S]*?)<\/div>/g, (_, t) => { nMath++; return `<div class="eq">${tex2svg(t, true)}</div>`; })
  .replace(/<span class="m">([\s\S]*?)<\/span>/g, (_, t) => { nMath++; return tex2svg(t, false); });
// math dictionary for components: src/math.json plus components/<id>.math.json
const COMP = path.join(SRC, 'components');
const mathSrc = Object.assign(JSON.parse(read(path.join(SRC, 'math.json'))),
  ...fs.readdirSync(COMP).filter((f) => f.endsWith('.math.json')).map((f) => JSON.parse(read(path.join(COMP, f)))));
const mathDict = Object.fromEntries(Object.entries(mathSrc).map(([k, t]) => [k, tex2svg(t, !k.startsWith('i:'))]));

// 5. slides: concatenate, pull out <style> blocks, render math, inline images
let slideCss = '';
const slideFiles = PAGE ? [PAGE] : fs.readdirSync(path.join(SRC, 'slides')).filter((f) => f.endsWith('.html')).sort().map((f) => path.join(SRC, 'slides', f));
let slides = slideFiles.map((f) => read(f)).join('\n')
  .replace(/<style>([\s\S]*?)<\/style>/g, (_, c) => { slideCss += c; return ''; });
// tables from the .tex: <div class="tbl" data-table="key" [data-rows="1-9"] [data-cols="0,2"] [data-head="1"]></div>
const numbering = JSON.parse(read(path.join(KIT, 'data', 'numbering.json')));
const numberOf = (kind, label) => Object.entries(numbering[kind] || {}).find(([, ls]) => ls.includes(label))?.[0];
const GREEK = { alpha: 'α', gamma: 'γ', kappa: 'κ', lambda: 'λ', tau: 'τ', rho: 'ρ', Delta: 'Δ', sigma: 'σ', varepsilon: 'ε', mu: 'μ' };
const texCell = (c) => {
  let s = String(c).replace(/^\\multicolumn\{\d+\}\{[^}]*\}\{(.*)\}$/, '$1');
  for (let i = 0; i < 4; i++) s = s.replace(/\\(?:textbf|emph|textit|mathrm|text|operatorname|mathbf)\{([^{}]*)\}/g, '$1');
  s = s.replace(/Equation~\\eqref\{([^}]+)\}/g, (_, l) => `Eq. ${numberOf('equation', l) || '?'}`)
    .replace(/\\(alpha|gamma|kappa|lambda|tau|rho|Delta|sigma|varepsilon|mu)(?![a-z])/g, (_, g) => GREEK[g])
    .replace(/\\(max|min|deg)(?![a-z])/g, '$1').replace(/\\times/g, '×').replace(/\\in(?![a-z])/g, '∈')
    .replace(/\\approx/g, '≈').replace(/\\downarrow/g, '↓').replace(/\\geq|>=/g, '≥').replace(/\\quad ?/g, '')
    .replace(/\\,/g, ' ').replace(/\\\{/g, '\u0001').replace(/\\\}/g, '\u0002').replace(/\\_/g, '_').replace(/\\ /g, ' ')
    .replace(/_\{([^{}]*)\}/g, '<sub>$1</sub>').replace(/\^\{([^{}]*)\}/g, '<sup>$1</sup>').replace(/_(\w)/g, '<sub>$1</sub>').replace(/\^(\*|\w)/g, '<sup>$1</sup>')
    .replace(/~/g, ' ').replace(/--/g, '–').replace(/(^|[\s(\[])-(?=\d)/g, '$1−').replace(/[{}]/g, '').replace(/\u0001/g, '{').replace(/\u0002/g, '}');
  if (/\\[a-zA-Z]/.test(s)) throw new Error(`table cell with unconverted TeX: ${c}`);
  return s;
};
const rangeOf = (r, n) => { if (!r) return [...Array(n).keys()]; return r.split(',').flatMap((p) => { const [a, b] = p.split('-').map(Number); return b === undefined ? [a] : [...Array(b - a + 1).keys()].map((k) => a + k); }); };
slides = slides.replace(/<div class="tbl([^"]*)" data-table="(\w+)"([^>]*)><\/div>/g, (_, extra, key, attrs) => {
  const t = tables[key];
  if (!t) throw new Error(`no table ${key}`);
  const at = (n) => (new RegExp(`data-${n}="([^"]*)"`).exec(attrs) || [])[1];
  const head = +(at('head') ?? 1);
  const cols = at('cols') ? at('cols').split(',').map(Number) : null;
  const rowIdx = rangeOf(at('rows'), t.raw.length - head).map((i) => i + head);
  const cells = (r, tag) => {
    let out = '', ci = 0;
    r.forEach((c, j) => {
      const mc = /^\\multicolumn\{(\d+)\}/.exec(c);
      const span = mc ? +mc[1] : 1;
      const keep = !cols || cols.includes(ci);
      if (keep) out += `<${tag}${span > 1 ? ` colspan="${span}"` : ''}>${texCell(c)}</${tag}>`;
      ci += span;
    });
    return `<tr>${out}</tr>`;
  };
  const num = numberOf('table', t.label);
  const style = (/style="([^"]*)"/.exec(attrs) || [])[1];
  return `<div class="tbl${extra}"${style ? ` style="${style}"` : ''}><table class="t"><thead>${t.raw.slice(0, head).map((r) => cells(r, 'th')).join('')}</thead>`
    + `<tbody>${rowIdx.map((i) => cells(t.raw[i], 'td')).join('')}</tbody></table>`
    + `<div class="cap">Dissertation, Table ${num || '?'}</div></div>`;
});
slides = renderMath(slides);
const missing = [];
const dataUri = (name) => {
  const p = path.join(BUILD, name);
  if (!fs.existsSync(p)) { missing.push(name); return name; }
  const ext = path.extname(p).slice(1);
  const mime = { webp: 'image/webp', png: 'image/png', svg: 'image/svg+xml', jpg: 'image/jpeg' }[ext];
  return `data:${mime};base64,${fs.readFileSync(p).toString('base64')}`;
};
slides = slides.replace(/src="((?:img|svg)\/[^"]+)"/g, (_, n) => `src="${dataUri(n)}"`);
if (missing.length) throw new Error(`missing assets: ${missing.join(', ')}`);

// 6. script bundle; the registry maps components/int-foo.js to data-component="INT-FOO"
const used = new Set([...slides.matchAll(/data-component="([^"]+)"/g)].map((m) => m[1]));
const compFiles = fs.readdirSync(COMP).filter((f) => /^int-[\w-]+\.js$/.test(f))
  .filter((f) => !PAGE || used.has(f.slice(0, -3).toUpperCase()));
const entry = [
  "import { startDeck } from './engine.js';",
  ...compFiles.map((f, i) => `import { mount as c${i} } from './components/${f}';`),
  `const registry = { ${compFiles.map((f, i) => `'${f.slice(0, -3).toUpperCase()}': c${i}`).join(', ')} };`,
  'const ctx = { data: window.NX_DATA, math: window.NX_MATH };',
  'window.NX = { registry, ctx };',
  'startDeck(registry, ctx);',
].join('\n');
const bundle = await esbuild.build({ stdin: { contents: entry, resolveDir: SRC, sourcefile: 'entry.js' }, bundle: true, format: 'iife', minify: !PAGE, target: 'es2020', write: false });
const js = bundle.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');

// 7. assemble
const compCss = fs.readdirSync(COMP).filter((f) => f.endsWith('.css')).sort().map((f) => read(path.join(COMP, f))).join('\n');
const css = read(FONTS) + '\n' + read(path.join(SRC, 'deck.css')) + '\n' + compCss + '\n' + slideCss;
const json = (o) => JSON.stringify(o).replace(/</g, '\\u003c');
const html = read(path.join(SRC, 'shell.html'))
  .replace('/*__CSS__*/', () => css)
  .replace('<!--__SLIDES__-->', () => slides)
  .replace('/*__DATA__*/', () => json(tables))
  .replace('/*__MATH__*/', () => json(mathDict))
  .replace('/*__JS__*/', () => js);
const OUT = PAGE ? path.join(BUILD, 'harness', path.basename(PAGE)) : DIST;
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, html);
const mb = fs.statSync(OUT).size / 1024 / 1024;
const nSlides = (slides.match(/<section class="slide/g) || []).length;
console.log(`built ${path.relative(KIT, OUT)}: ${nSlides} slides, ${nMath} equations, ${mb.toFixed(2)} MB${mb > 12 ? '  (over the 12 MB target!)' : ''}`);
if (mb > 16) process.exit(1);
