import test from 'node:test';
import assert from 'node:assert/strict';
import { contentSignals, prefersMarkdown, htmlToMarkdown, pageResponse } from '../lib/agent-content.mjs';

test('only an explicit preferred Markdown representation changes the browser response', () => {
  for (const accept of ['', '*/*', 'text/*', 'text/html', 'text/markdown;q=0', 'text/html;q=1,text/markdown;q=0.5', 'text/*;q=0.9,text/markdown;q=0.5', 'text/markdown;q=invalid', 'text/markdown;q=2']) assert.equal(prefersMarkdown(accept), false, accept);
  for (const accept of ['text/markdown', 'TEXT/MARKDOWN; charset=utf-8', 'text/html,text/markdown', 'text/html;q=0.5,text/markdown;q=1']) assert.equal(prefersMarkdown(accept), true, accept);
});

const html = `<!doctype html><html lang="pl"><head><title>Źródła &amp; scope</title><meta name="description" content="Checked sources"><link rel="canonical" href="https://example.com/guides/clock"><script type="application/ld+json">{"@type":"Article","citation":["https://manufacturer.example/manual"]}</script></head><body><nav>Navigation noise</nav><main><h1>Clock — zegar</h1><aside><nav>Table of contents</nav><p>Only for model ABC.</p></aside><p>Not independently tested.</p><p><a href="/about">About</a> <a href="https://manufacturer.example/manual">Manufacturer manual</a></p><table><thead><tr><th>Control</th><th>Meaning</th></tr></thead><tbody><tr><td>A</td><td>Clock</td></tr></tbody></table><ol><li>First</li><li>Second</li></ol><p hidden>Hidden noise</p><script>window.tracker=1</script></main><footer>Footer noise</footer></body></html>`;

test('Markdown retains citations, model restrictions, review limits, tables, lists and metadata', () => {
  const markdown = htmlToMarkdown(html, 'https://example.com/guides/clock');
  for (const text of ['title: "Źródła & scope"', 'language: "pl"', '# Clock — zegar', 'Only for model ABC.', 'Not independently tested.', '[About](https://example.com/about)', 'https://manufacturer.example/manual', '| Control | Meaning |', '1.  First', '```json']) assert.ok(markdown.includes(text), text);
  for (const noise of ['Navigation noise', 'Table of contents', 'Hidden noise', 'Footer noise', 'window.tracker', '<script']) assert.ok(!markdown.includes(noise), noise);
});

test('a local HTML render ignores HTML validators and yields independently negotiated headers and HEAD', async () => {
  for (const method of ['GET', 'HEAD']) {
    const request = new Request('https://example.com/guides/clock?view=full', { method, headers: { Accept: 'text/markdown', 'If-None-Match': '"html"', Range: 'bytes=0-5', RSC: '1' } });
    const response = await pageResponse(request, 'https://example.com', true, async (url, options) => {
      assert.equal(url.hostname, '127.0.0.1');
      assert.equal(url.pathname, '/guides/clock');
      assert.equal(url.searchParams.get('view'), 'full');
      assert.equal(url.searchParams.get('__agent_html'), '1');
      assert.equal(options.headers.get('accept'), 'text/html');
      for (const header of ['if-none-match', 'range', 'rsc']) assert.equal(options.headers.get(header), null);
      return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8', ETag: '"html"', Vary: 'RSC, Accept-Encoding', 'Content-Encoding': 'gzip' } });
    });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'text/markdown; charset=utf-8');
    assert.equal(response.headers.get('content-signal'), contentSignals);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.match(response.headers.get('vary'), /RSC, Accept-Encoding, Accept/);
    for (const header of ['etag', 'content-encoding', 'content-length']) assert.equal(response.headers.get(header), null);
    const body = await response.text();
    assert.equal(body.includes('# Clock'), method === 'GET');
  }
});

test('unpublished pages and redirects keep their original status, privacy rules and representation', async () => {
  for (const status of [404, 307]) {
    const response = await pageResponse(new Request('https://example.com/guides/future'), 'https://example.com', true, async () => new Response(status === 404 ? 'Not published' : null, { status, headers: { 'Content-Type': 'text/html', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex', ...(status === 307 ? { Location: '/guides/clock' } : {}) } }));
    assert.equal(response.status, status);
    assert.equal(response.headers.get('content-type'), 'text/html');
    assert.equal(response.headers.get('x-robots-tag'), 'noindex');
    if (status === 404) assert.equal(await response.text(), 'Not published');
    else assert.equal(response.headers.get('location'), '/guides/clock');
  }
});

test('HTML keeps its body and validators while declaring Accept as a cache dimension', async () => {
  const response = await pageResponse(new Request('https://example.com/', { headers: { 'If-None-Match': '"html"' } }), 'https://example.com', false, async (url, options) => {
    assert.equal(options.headers.get('if-none-match'), '"html"');
    return new Response(html, { headers: { 'Content-Type': 'text/html', ETag: '"html"' } });
  });
  assert.equal(await response.text(), html);
  assert.equal(response.headers.get('etag'), '"html"');
  assert.equal(response.headers.get('vary'), 'Accept');
});
