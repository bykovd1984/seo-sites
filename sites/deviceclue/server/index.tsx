import { createServer, type ServerResponse } from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { renderToStaticMarkup } from 'react-dom/server';
import Layout from '../app/layout';
import Home, { metadata as homeMetadata } from '../app/page';
import About, { metadata as aboutMetadata } from '../app/about/page';
import Privacy, { metadata as privacyMetadata } from '../app/privacy/page';
import Search, { metadata as searchMetadata } from '../app/search/page';
import Guide, { generateMetadata as guideMetadata } from '../app/guides/[slug]/page';
import Topic, { generateMetadata as topicMetadata } from '../app/topics/[category]/page';
import NotFound from '../app/not-found';
import sitemap from '../app/sitemap';
import robots from '../app/robots';
import { GET as health } from '../app/api/health/route';
import { PageNotFound } from '../lib/http';
import { site } from '../lib/site';
import type { Assets, Metadata } from '../lib/metadata';
import { contentSignals, htmlToMarkdown, prefersMarkdown } from '../lib/agent-content.mjs';

const root = path.resolve(process.env.SITE_ROOT || process.cwd());
const assets: Assets = JSON.parse(fs.readFileSync(path.join(root, 'dist/assets.json'), 'utf8'));
const mime: Record<string, string> = { '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8' };

async function page(url: URL) {
  let content: React.ReactNode;
  let metadata: Metadata;
  const route = url.pathname;
  if (route === '/') { content = <Home/>; metadata = homeMetadata; }
  else if (route === '/about') { content = <About/>; metadata = aboutMetadata; }
  else if (route === '/privacy') { content = <Privacy/>; metadata = privacyMetadata; }
  else if (route === '/search') { content = await Search({ searchParams: Promise.resolve({ q: url.searchParams.get('q') || undefined }) }); metadata = searchMetadata; }
  else if (/^\/guides\/[a-z0-9-]+$/.test(route)) {
    const props = { params: Promise.resolve({ slug: route.slice('/guides/'.length) }) };
    content = await Guide(props); metadata = await guideMetadata(props);
  } else if (/^\/topics\/[a-z0-9-]+$/.test(route)) {
    const props = { params: Promise.resolve({ category: route.slice('/topics/'.length) }) };
    content = await Topic(props); metadata = await topicMetadata(props);
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
      const url = new URL(request.url || '/', site.url);
      if (!['GET', 'HEAD'].includes(method)) { send(response, method, 405, 'Method not allowed', 'text/plain; charset=utf-8', { Allow: 'GET, HEAD' }); return; }
      if (url.pathname.length > 1 && url.pathname.endsWith('/')) { send(response, method, 308, '', 'text/plain', { Location: url.pathname.replace(/\/+$/, '') + url.search }); return; }
      if (url.pathname === '/api/health') {
        const result = await health(); send(response, method, result.status, await result.text(), 'application/json; charset=utf-8', { 'X-Robots-Tag': 'noindex, nofollow' }); return;
      }
      if (url.pathname === '/robots.txt') {
        const settings = robots();
        send(response, method, 200, `User-agent: ${settings.rules.userAgent}\nAllow: ${settings.rules.allow}\n${settings.rules.disallow.map(route => `Disallow: ${route}\n`).join('')}Sitemap: ${settings.sitemap}\n`, 'text/plain; charset=utf-8'); return;
      }
      if (url.pathname === '/sitemap.xml') {
        send(response, method, 200, '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + sitemap().map(entry => `<url><loc>${entry.url}</loc></url>`).join('') + '</urlset>', 'application/xml; charset=utf-8'); return;
      }
      const filename = staticFile(decodeURIComponent(url.pathname));
      if (filename) {
        const body = fs.readFileSync(filename);
        const etag = 'W/"' + createHash('sha256').update(body).digest('hex').slice(0, 24) + '"';
        const headers = { ETag: etag, 'Cache-Control': /^\/assets\//.test(url.pathname) ? 'public, max-age=31536000, immutable' : 'public, max-age=0, must-revalidate' };
        if (request.headers['if-none-match'] === etag) { response.writeHead(304, headers); response.end(); return; }
        send(response, method, 200, body, mime[path.extname(filename)] || 'application/octet-stream', headers); return;
      }
      const html = await page(url);
      const markdown = url.pathname !== '/search' && prefersMarkdown(request.headers.accept || '');
      send(response, method, 200, markdown ? htmlToMarkdown(html, new URL(url.pathname + url.search, site.url).href) : html, markdown ? 'text/markdown; charset=utf-8' : 'text/html; charset=utf-8', { Vary: 'Accept', ...(url.pathname === '/search' ? { 'X-Robots-Tag': 'noindex, follow' } : {}) });
    } catch (error) {
      if (error instanceof PageNotFound || error instanceof URIError) {
        const follow = !(request.url || '').startsWith('/api/');
        const html = '<!doctype html>' + renderToStaticMarkup(<Layout assets={assets} pageMetadata={{ title: 'Guide not found', robots: { index: false, follow } }}><NotFound/></Layout>);
        send(response, method, 404, html, 'text/html; charset=utf-8', { 'X-Robots-Tag': `noindex, ${follow ? 'follow' : 'nofollow'}`, Vary: 'Accept' });
      } else {
        console.error('DeviceClue request failed');
        send(response, method, 500, 'Request failed', 'text/plain; charset=utf-8', { 'X-Robots-Tag': 'noindex' });
      }
    }
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || '3000');
  const host = process.env.HOSTNAME || '127.0.0.1';
  createSiteServer().listen(port, host, () => console.log(`DeviceClue ready at http://${host}:${port}`));
}
