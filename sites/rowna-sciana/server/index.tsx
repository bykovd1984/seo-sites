import { createServer, type ServerResponse } from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { renderToStaticMarkup } from 'react-dom/server';
import Layout from '../app/layout';
import Home from '../app/page';
import About, { metadata as aboutMetadata } from '../app/o-poradniku/page';
import Privacy, { metadata as privacyMetadata } from '../app/prywatnosc/page';
import Search, { metadata as searchMetadata } from '../app/szukaj/page';
import Guide, { generateMetadata as guideMetadata } from '../app/poradniki/[slug]/page';
import NotFound from '../app/not-found';
import sitemap from '../app/sitemap';
import { GET as robots } from '../app/robots.txt/route';
import { GET as health } from '../app/api/health/route';
import { PageNotFound } from '../lib/http';
import { SITE_URL } from '../lib/site';
import ErrorPage from '../app/error';
import type { Assets, Metadata } from '../lib/metadata';
import { contentSignals, htmlToMarkdown, prefersMarkdown } from '../lib/agent-content.mjs';

const root = path.resolve(process.env.SITE_ROOT || process.cwd());
const assets: Assets = JSON.parse(fs.readFileSync(path.join(root, 'dist/assets.json'), 'utf8'));
const mime: Record<string, string> = { '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8' };

async function page(url: URL) {
  let content: React.ReactNode;
  let metadata: Metadata;
  const route = url.pathname;
  if (route === '/') { content = await Home(); metadata = {}; }
  else if (route === '/o-poradniku') { content = <About/>; metadata = aboutMetadata; }
  else if (route === '/prywatnosc') { content = <Privacy/>; metadata = privacyMetadata; }
  else if (route === '/szukaj') { content = await Search({ searchParams: Promise.resolve({ q: url.searchParams.get('q') || undefined }) }); metadata = searchMetadata; }
  else if (/^\/poradniki\/[a-z0-9-]+$/.test(route)) {
    const props = { params: Promise.resolve({ slug: route.slice('/poradniki/'.length) }) };
    content = await Guide(props); metadata = await guideMetadata(props);
  } else throw new PageNotFound();
  return '<!doctype html>' + renderToStaticMarkup(<Layout assets={assets} pageMetadata={metadata}>{content}</Layout>);
}

function send(response: ServerResponse, method: string, status: number, body: string | Buffer, type: string, headers: Record<string, string> = {}) {
  const bytes = Buffer.isBuffer(body) ? body : Buffer.from(body);
  response.writeHead(status, { 'Content-Type': type, 'Content-Length': bytes.length, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin', 'Content-Signal': contentSignals, 'Cache-Control': 'no-store', ...headers });
  response.end(method === 'HEAD' ? undefined : bytes);
}

function staticFile(pathname: string): string | undefined {
  // Only these two public roots can be served; content snapshots and source files stay private.
  if (pathname.includes('\0') || pathname.includes('\\')) return;
  for (const directory of ['dist/public', 'public']) {
    const base = path.join(root, directory);
    const filename = path.resolve(base, '.' + pathname);
    if (filename.startsWith(base + path.sep) && fs.existsSync(filename) && fs.statSync(filename).isFile()) return filename;
  }
}

export function createSiteServer() {
  return createServer(async (request, response) => {
    const method = request.method || 'GET';
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    response.setHeader('Content-Signal', contentSignals);
    try {
      const url = new URL(request.url || '/', SITE_URL);
      if (!['GET', 'HEAD'].includes(method)) { send(response, method, 405, 'Method not allowed', 'text/plain; charset=utf-8', { Allow: 'GET, HEAD' }); return; }
      if (url.pathname.length > 1 && url.pathname.endsWith('/')) { send(response, method, 308, '', 'text/plain', { Location: url.pathname.replace(/\/+$/, '') + url.search }); return; }
      if (url.pathname === '/api/health') {
        const result = await health(); send(response, method, result.status, await result.text(), 'application/json; charset=utf-8', { 'X-Robots-Tag': 'noindex, nofollow' }); return;
      }
      if (url.pathname === '/robots.txt') {
        const result = robots();
        send(response, method, result.status, await result.text(), 'text/plain; charset=utf-8', { 'Cache-Control': result.headers.get('cache-control') || 'no-store' }); return;
      }
      if (url.pathname === '/sitemap.xml') {
        send(response, method, 200, '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + sitemap().map(entry => `<url><loc>${entry.url}</loc></url>`).join('') + '</urlset>', 'application/xml; charset=utf-8'); return;
      }
      const filename = staticFile(decodeURIComponent(url.pathname));
      if (filename) {
        const body = fs.readFileSync(filename);
        const etag = 'W/"' + createHash('sha256').update(body).digest('hex').slice(0, 24) + '"';
        const headers = { ETag: etag, 'Cache-Control': (/^\/assets\//.test(url.pathname) || /^\/images\/.*\.webp$/.test(url.pathname)) ? 'public, max-age=31536000, immutable' : 'public, max-age=0, must-revalidate' };
        if (request.headers['if-none-match'] === etag) { response.writeHead(304, headers); response.end(); return; }
        send(response, method, 200, body, mime[path.extname(filename)] || 'application/octet-stream', headers); return;
      }
      const html = await page(url);
      const markdown = url.pathname !== '/szukaj' && prefersMarkdown(request.headers.accept || '');
      send(response, method, 200, markdown ? htmlToMarkdown(html, new URL(url.pathname + url.search, SITE_URL).href) : html, markdown ? 'text/markdown; charset=utf-8' : 'text/html; charset=utf-8', { Vary: 'Accept', ...(url.pathname === '/szukaj' ? { 'X-Robots-Tag': 'noindex, follow' } : {}) });
    } catch (error) {
      if (error instanceof PageNotFound || error instanceof URIError) {
        const follow = false;
        const html = '<!doctype html>' + renderToStaticMarkup(<Layout assets={assets} pageMetadata={{ title: 'Nie znaleziono poradnika', robots: { index: false, follow } }}><NotFound/></Layout>);
        send(response, method, 404, html, 'text/html; charset=utf-8', { 'X-Robots-Tag': `noindex, ${follow ? 'follow' : 'nofollow'}`, Vary: 'Accept' });
      } else {
        console.error('Rowna sciana request failed');
        const html = '<!doctype html>' + renderToStaticMarkup(<Layout assets={assets} pageMetadata={{ title: 'Nie udało się wczytać poradnika', robots: { index: false, follow: false } }}><ErrorPage/></Layout>);
        send(response, method, 500, html, 'text/html; charset=utf-8', { 'X-Robots-Tag': 'noindex, nofollow' });
      }
    }
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || '3000');
  const host = process.env.HOSTNAME || '127.0.0.1';
  createSiteServer().listen(port, host, () => console.log(`Rowna sciana ready at http://${host}:${port}`));
}
