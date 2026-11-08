import test from 'node:test';
import assert from 'node:assert/strict';
import { contentSignals, prefersMarkdown, htmlToMarkdown } from '../lib/agent-content.mjs';

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
