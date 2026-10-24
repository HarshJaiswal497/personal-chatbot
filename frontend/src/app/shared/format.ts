/** Tiny, safe markdown → HTML for model answers. Escapes first, then formats. */
export function renderMarkdown(text: string): string {
  const escape = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const inline = (s: string) =>
    escape(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');

  const blocks: string[] = [];
  let list: { tag: 'ul' | 'ol'; items: string[] } | null = null;
  let para: string[] = [];

  const flushPara = () => {
    if (para.length) blocks.push(`<p>${para.map(inline).join('<br>')}</p>`);
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push(`<${list.tag}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`);
    list = null;
  };

  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const bullet  = line.match(/^[-*•]\s+(.*)/);
    const ordered = line.match(/^\d+[.)]\s+(.*)/);

    if (!line) { flushPara(); flushList(); continue; }
    if (bullet || ordered) {
      flushPara();
      const tag = bullet ? 'ul' : 'ol';
      if (list && list.tag !== tag) flushList();
      list ??= { tag, items: [] };
      list.items.push((bullet ?? ordered)![1]);
      continue;
    }
    flushList();
    para.push(line.replace(/^#{1,6}\s+/, ''));
  }
  flushPara();
  flushList();
  return blocks.join('');
}

/** "04_project_runway.txt" → "Project runway" */
export function sourceLabel(file: string): string {
  const s = file.replace(/\.txt$/i, '').replace(/^\d+_/, '').replace(/^qa_/, 'Q&A ').replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
