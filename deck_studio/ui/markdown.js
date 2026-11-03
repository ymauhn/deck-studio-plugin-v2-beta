// A safe subset of Markdown for the agent's answers: paragraphs, **bold**, *italic*, `code`, fenced code blocks,
// "- " and "1. " lists, and headings as bold lines. The text is escaped first, so nothing in it becomes markup:
// the only tags are the ones made here, and the only attribute is a list's start number.
const escape = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// code spans first, so nothing inside them turns bold or italic; an italic never spans a tag made here, so the tags
// always nest
const inline = (text) => text.split(/(`[^`\n]+`)/).map((part, i) => (i % 2
  ? `<code>${part.slice(1, -1)}</code>`
  : part.replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(?=[^\s*])([^<>]*?)(?<=[^\s*])\*/g, '<em>$1</em>'))).join('');

export function markdown(text) {
  const html = [];
  let paragraph = [];
  let list = null; // {tag, start, items}
  let code = null; // the lines of an open fenced block
  const close = () => {
    if (paragraph.length) html.push(`<p>${inline(paragraph.join('\n'))}</p>`);
    if (list) html.push(`<${list.tag}${list.start}>${list.items.map((item) => `<li>${inline(item)}</li>`).join('')}</${list.tag}>`);
    paragraph = [];
    list = null;
  };
  for (const line of escape(text).split('\n')) {
    let m;
    if (code) {
      if (/^\s*```/.test(line)) {
        html.push(`<pre><code>${code.join('\n')}</code></pre>`);
        code = null;
      } else code.push(line);
    } else if (/^\s*```/.test(line)) {
      close();
      code = [];
    } else if (!line.trim()) close();
    else if ((m = /^\s*#{1,6}\s+(.*)$/.exec(line))) {
      close();
      html.push(`<p><strong>${inline(m[1])}</strong></p>`);
    } else if ((m = /^\s*(?:-|(\d+)\.)\s+(.*)$/.exec(line))) {
      const tag = m[1] ? 'ol' : 'ul';
      if (list?.tag !== tag) {
        close();
        list = { tag, start: m[1] && Number(m[1]) !== 1 ? ` start="${Number(m[1])}"` : '', items: [] };
      }
      list.items.push(m[2]);
    } else if (list && /^\s/.test(line)) list.items[list.items.length - 1] += `\n${line.trim()}`; // the item goes on
    else {
      if (list) close();
      paragraph.push(line);
    }
  }
  if (code) html.push(`<pre><code>${code.join('\n')}</code></pre>`); // a block whose end has not streamed in yet
  close();
  return html.join('');
}
