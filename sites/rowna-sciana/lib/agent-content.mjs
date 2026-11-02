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

// Fetch the existing public page locally as HTML, so publication gates and source notes stay identical.
export async function pageResponse(request, origin, asMarkdown, fetchPage = fetch) {
  const source = new URL(request.url);
  const pageUrl = new URL(source.pathname + source.search, origin).href;
  const headers = new Headers(request.headers);
  headers.set('Accept', 'text/html');
  headers.set('Accept-Encoding', 'identity');
  for (const name of ['host', 'connection', 'content-length', 'rsc', 'next-router-state-tree', 'next-router-prefetch', 'next-router-segment-prefetch', 'next-url']) headers.delete(name);
  if (asMarkdown) for (const name of ['if-none-match', 'if-modified-since', 'if-match', 'if-unmodified-since', 'range', 'if-range']) headers.delete(name);
  source.protocol = 'http:';
  source.hostname = '127.0.0.1';
  source.port = process.env.PORT || source.port || '3000';
  // A query marker keeps internal renders separate from publicly cacheable URLs.
  source.searchParams.set('__agent_html', '1');
  const response = await fetchPage(source, { method: 'GET', headers, redirect: 'manual', cache: 'no-store', signal: AbortSignal.timeout(15000) });
  const outputHeaders = new Headers(response.headers);
  varyOnAccept(outputHeaders);
  outputHeaders.set('Content-Signal', contentSignals);
  for (const name of ['content-length', 'content-encoding', 'transfer-encoding']) outputHeaders.delete(name);
  for (const name of [...outputHeaders.keys()]) if (name.startsWith('x-middleware-') || name.startsWith('x-nextjs-')) outputHeaders.delete(name);
  if (!asMarkdown || response.status !== 200 || !response.headers.get('content-type')?.startsWith('text/html')) {
    return new Response(request.method === 'HEAD' ? null : response.body, { status: response.status, headers: outputHeaders });
  }
  const markdown = htmlToMarkdown(await response.text(), pageUrl);
  outputHeaders.set('Content-Type', 'text/markdown; charset=utf-8');
  // Content can be released on a schedule; never reuse an HTML validator or cache this representation past a release.
  outputHeaders.set('Cache-Control', 'no-store');
  for (const name of ['etag', 'last-modified', 'content-range', 'accept-ranges']) outputHeaders.delete(name);
  return new Response(request.method === 'HEAD' ? null : markdown, { status: 200, headers: outputHeaders });
}
