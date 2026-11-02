import assert from 'node:assert/strict';
const contentSignals = 'search=yes, ai-input=yes, ai-train=no';

export async function verifyMarkdown(base, routes, pending = []) {
  for (const path of routes) {
    const html = await fetch(new URL(path, base), { headers: { Accept: 'text/html' } });
    assert.equal(html.status, 200, path);
    assert.match(html.headers.get('content-type'), /^text\/html/);
    assert.match(html.headers.get('vary') || '', /(?:^|,)\s*accept(?:,|$)/i);
    const source = await html.text();
    const response = await fetch(new URL(path, base), { headers: { Accept: 'text/markdown', 'If-None-Match': '"html-source"', Range: 'bytes=0-5' } });
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get('content-type'), 'text/markdown; charset=utf-8', path);
    assert.equal(response.headers.get('content-signal'), contentSignals);
    assert.match(response.headers.get('vary') || '', /(?:^|,)\s*accept(?:,|$)/i);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.equal(response.headers.get('etag'), null);
    const markdown = await response.text();
    assert.match(markdown, /^# .+/m);
    assert.ok(markdown.startsWith('---\n'));
    const main = /<main\b[^>]*>([\s\S]*?)<\/main>/.exec(source)?.[1] || source;
    for (const link of main.matchAll(/<a\b[^>]*href="(https?:[^\"]+)"/g)) {
      const href = link[1].replaceAll('&amp;', '&');
      assert.ok(markdown.replace(/\\([()])/g, '$1').includes(href), path + ' loses source link ' + href);
    }
    assert.ok(!response.headers.get('x-robots-tag')?.includes('noindex'));
    assert.doesNotMatch(markdown, /<(?:html|script|style|nav)\b/);
  }
  const first = new URL(routes[0], base);
  const head = await fetch(first, { method: 'HEAD', headers: { Accept: 'text/markdown' } });
  assert.equal(head.status, 200);
  assert.match(head.headers.get('content-type'), /^text\/markdown/);
  assert.equal(await head.text(), '');
  for (const accept of ['*/*', 'text/markdown;q=0', 'text/html;q=1,text/markdown;q=0.5']) {
    const response = await fetch(first, { headers: { Accept: accept } });
    assert.match(response.headers.get('content-type'), /^text\/html/);
    await response.arrayBuffer();
  }
  for (const path of pending) {
    const response = await fetch(new URL(path, base), { headers: { Accept: 'text/markdown' } });
    assert.equal(response.status, 404, path);
    assert.match(response.headers.get('content-type'), /^text\/html/);
    assert.match(await response.text(), /noindex/);
  }
  for (const path of ['/robots.txt', '/sitemap.xml', '/api/health']) {
    const response = await fetch(new URL(path, base), { headers: { Accept: 'text/markdown' } });
    assert.equal(response.status, 200, path);
    assert.doesNotMatch(response.headers.get('content-type') || '', /text\/markdown/);
    await response.arrayBuffer();
  }
  console.log(`Markdown HTTP smoke passed: ${routes.length} public pages, ${pending.length} unpublished/missing pages, HEAD, HTML preferences, validators, citations and discovery resources.`);
}
