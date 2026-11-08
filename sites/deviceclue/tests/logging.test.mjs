import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
const require = createRequire(import.meta.url);
const { createTransport } = require('../runtime/log-transport.cjs');
const { publicPath, errorDetails } = require('../runtime/logging.cjs');

test('logging only admits published paths and safe error locations', () => {
  assert.equal(publicPath('/search?q=private@example.com#secret'), '/search');
  assert.equal(publicPath('/guides/fridge-coldest-setting?token=secret'), '/guides/fridge-coldest-setting');
  assert.equal(publicPath('/private@example.com/token'), '/[unmatched]');
  const error = new TypeError('private@example.com token=secret');
  error.stack = 'TypeError: secret\n at run (/app/server.js:20:3)\n at private@example.com';
  assert.deepEqual(errorDetails(error), { error: { type: 'TypeError', stack_trace: '/app/server.js:20:3' } });
});

test('bulk transport retries only failed items and preserves ids across ambiguous delivery', async () => {
  let clock = 100000;
  const bodies = [];
  const transport = createTransport({ endpoint: 'http://collector', apiKey: 'test-only', now: () => clock,
    fetchImpl: async (_, options) => {
      assert.equal(options.headers.Authorization, 'ApiKey test-only');
      const lines = options.body.trim().split('\n').map(JSON.parse);
      bodies.push(lines);
      return { ok: true, json: async () => ({ items: bodies.length === 1 ? [{ create: { status: 201 } }, { create: { status: 429 } }] : [{ create: { status: 409 } }] }) };
    } });
  try {
    transport.enqueue({ message: 'one' }); transport.enqueue({ message: 'two' });
    await transport.flush(); clock += 31000; await transport.flush();
    assert.equal(bodies[1].length, 2);
    assert.equal(bodies[1][0].create._id, bodies[0][2].create._id);
    assert.equal(bodies[1][1].message, 'two');
    await transport.flush(); assert.equal(bodies.length, 2);
  } finally { transport.close(); }
});

test('a real preloaded HTTP server reports status/duration/errors without request secrets', { timeout: 15000 }, async () => {
  const received = [];
  const collector = createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk;
    const lines = body.trim().split('\n').map(JSON.parse);
    for (let i = 1; i < lines.length; i += 2) received.push(lines[i]);
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ items: received.length ? Array.from({ length: lines.length / 2 }, () => ({ create: { status: 201 } })) : [] }));
  });
  collector.listen(0, '127.0.0.1'); await once(collector, 'listening');
  const temporary = await mkdtemp(path.join(tmpdir(), 'deviceclue-logging-'));
  const keyFile = path.join(temporary, 'key'); await writeFile(keyFile, 'fake-test-key');
  const preload = path.resolve(import.meta.dirname, '../runtime/logging.cjs');
  const child = spawn(process.execPath, ['--require', preload, '-e', `require('node:http').createServer((req,res)=>{if(req.url.startsWith('/privacy')){console.error(new TypeError('private@example.com'));res.statusCode=500;}else if(req.url.startsWith('/unknown'))res.statusCode=404;res.end('ok');}).listen(0,'127.0.0.1',function(){console.log(this.address().port)})`], { env: { ...process.env, DEVICECLUE_LOG_ENDPOINT: 'http://127.0.0.1:' + collector.address().port, DEVICECLUE_LOG_KEY_FILE: keyFile, DEPLOY_COMMIT: 'test-release' }, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stderr.resume();
  try {
    const [data] = await once(child.stdout, 'data');
    const base = 'http://127.0.0.1:' + String(data).trim();
    for (const route of ['/about?__agent_html=1', '/search?q=private@example.com&token=secret', '/unknown/private@example.com', '/privacy', '/api/health', '/_next/static/test.js', '/assets/site.test.js', '/diagrams/clock.svg']) await fetch(base + route, { headers: { Cookie: 'private=secret', Authorization: 'Bearer secret' } });
    const deadline = Date.now() + 8000;
    while (received.filter(r => r.event.action === 'http_request').length < 3 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 50));
    const requests = received.filter(r => r.event.action === 'http_request');
    assert.equal(requests.length, 3);
    assert.deepEqual(requests.map(r => r.http.response.status_code), [200, 404, 500]);
    assert.ok(requests.every(r => r.event.duration > 0 && r.service.version === 'test-release'));
    assert.ok(received.some(r => r.event.action === 'server_start'));
    assert.ok(received.some(r => r.event.action === 'application_error' && r.error.type === 'TypeError'));
    assert.doesNotMatch(JSON.stringify(received), /private@example|token=|Bearer|fake-test-key|Cookie/);
  } finally {
    child.kill(); await once(child, 'exit'); collector.closeAllConnections(); await new Promise(resolve => collector.close(resolve));
    await rm(temporary, { recursive: true, force: true });
  }
});
