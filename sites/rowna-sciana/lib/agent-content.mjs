import { parseHTML } from 'linkedom';
import TurndownService from 'turndown';
import { gfm } from 'turndown-plugin-gfm';

export const contentSignals = 'search=yes, ai-input=yes, ai-train=no';

export function prefersMarkdown(accept = '') {
  const types = new Map();
  for (const entry of (accept || '').split(',')) {
    const [type, ...parameters] = entry.trim().toLowerCase().split(';');
    let quality = 1;
    for (const parameter of parameters) {
      const [name, value] = parameter.trim().split('=');
      if (name !== 'q') continue;
      if (!/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(value || '')) return false;
      quality = Number(value);
    }
    types.set(type.trim(), Math.max(types.get(type.trim()) ?? 0, quality));
  }
  const markdown = types.get('text/markdown') ?? 0;
  const html = types.get('text/html') ?? types.get('text/*') ?? types.get('*/*') ?? 0;
  return markdown > 0 && markdown >= html;
}

export function varyOnAccept(headers) {
  const values = (headers.get('vary') || '').split(',').map(value => value.trim()).filter(Boolean);
  if (!values.some(value => value.toLowerCase() === 'accept' || value === '*')) values.push('Accept');
  headers.set('Vary', values.join(', '));
}

export function htmlToMarkdown(html, pageUrl) {
  const { document } = parseHTML(html);
  const metadata = {
    title: document.title,
    description: document.querySelector('meta[name="description"]')?.getAttribute('content'),
    language: document.documentElement.getAttribute('lang'),
    url: document.querySelector('link[rel="canonical"]')?.getAttribute('href') || pageUrl,
  };
  const schemas = [];
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { schemas.push(JSON.stringify(JSON.parse(script.textContent))); } catch { /* Preserve readable content if a schema is invalid. */ }
  }
  for (const element of document.querySelectorAll('script, style, nav, footer, svg, iframe, template, button, input, select, textarea, [hidden], [aria-hidden="true"], [role="dialog"]')) element.remove();
  for (const element of document.querySelectorAll('a[href], img[src]')) {
    const attribute = element.localName === 'a' ? 'href' : 'src';
    try {
      const url = new URL(element.getAttribute(attribute), pageUrl);
      if (['https:', 'http:', 'mailto:'].includes(url.protocol)) element.setAttribute(attribute, url.href);
      else element.removeAttribute(attribute);
    } catch { element.removeAttribute(attribute); }
  }
  const converter = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced', bulletListMarker: '-' });
  converter.use(gfm);
  const body = converter.turndown((document.querySelector('main') || document.body).innerHTML);
  const frontmatter = Object.entries(metadata).filter(([, value]) => value).map(([name, value]) => `${name}: ${JSON.stringify(value)}`).join('\n');
  return `---\n${frontmatter}\n---\n\n${body}\n` + schemas.map(schema => `\n\`\`\`json\n${schema}\n\`\`\`\n`).join('');
}
