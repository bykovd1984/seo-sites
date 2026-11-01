'use strict';
const fs = require('node:fs');
const dc = require('node:diagnostics_channel');
const { createTransport } = require('./log-transport.cjs');

function publicPath(value) {
  const path = String(value || '').split(/[?#]/, 1)[0];
  if (['/', '/about', '/privacy', '/search', '/sitemap.xml', '/robots.txt'].includes(path)) return path;
  // Only published routes can enter logs, including for arbitrary scanner URLs.
  if (publicPaths.has(path)) return path;
  return '/[unmatched]';
}
const publicPaths = new Set();
try {
  const articles = fs.existsSync(__dirname + '/log-routes.json') ? require('./log-routes.json') : require('../content/catalog.json');
  for (const article of articles) publicPaths.add('/guides/' + article.slug);
} catch {}
for (const topic of ['ovens', 'cooling', 'home-systems', 'batteries', 'small-engines']) publicPaths.add('/topics/' + topic);

function install() {
  const endpoint = process.env.DEVICECLUE_LOG_ENDPOINT;
  if (!endpoint) return;
  let apiKey;
  try { apiKey = fs.readFileSync(process.env.DEVICECLUE_LOG_KEY_FILE, 'utf8').trim(); }
  catch { process.stderr.write('DeviceClue logging key unavailable; continuing without remote logs.\n'); return; }
  if (!apiKey) return;
  const transport = createTransport({ endpoint, apiKey, version: process.env.DEPLOY_COMMIT });
  const starts = new WeakMap();
  dc.channel('http.server.request.start').subscribe(({ request, response }) => {
    if (/^\/(?:_next\/|api\/health(?:[?#]|$)|favicon\.|opengraph-image\.)/.test(request.url || '')) return;
    starts.set(response, { at: process.hrtime.bigint(), path: publicPath(request.url), method: /^(GET|HEAD|POST|PUT|DELETE|PATCH|OPTIONS)$/.test(request.method) ? request.method : 'OTHER' });
  });
  dc.channel('http.server.response.finish').subscribe(({ response }) => {
    const start = starts.get(response);
    if (!start) return;
    starts.delete(response);
    const status = response.statusCode;
    transport.enqueue({ message: 'HTTP request completed', log: { level: status >= 500 ? 'error' : status >= 400 ? 'warn' : 'info' },
      event: { action: 'http_request', duration: Number(process.hrtime.bigint() - start.at) },
      http: { request: { method: start.method }, response: { status_code: status } }, url: { path: start.path } });
  });
  const originalError = console.error;
  console.error = function (...args) {
    const error = args.find(value => value instanceof Error);
    transport.enqueue({ message: 'Application wrote an error; inspect container diagnostics for details', log: { level: 'error' }, event: { action: 'application_error' }, ...errorDetails(error) });
    originalError.apply(console, args);
  };
  // Monitoring must preserve Node's normal crash behavior.
  process.on('uncaughtExceptionMonitor', error => {
    transport.enqueue({ message: 'Uncaught application exception', log: { level: 'fatal' }, event: { action: 'uncaught_exception' }, ...errorDetails(error) });
    void transport.flush();
  });
  transport.enqueue({ message: 'DeviceClue server starting', log: { level: 'info' }, event: { action: 'server_start' } });
  void transport.flush();
}
function errorDetails(error) {
  if (!(error instanceof Error)) return {};
  const type = ['Error', 'TypeError', 'RangeError', 'SyntaxError', 'ReferenceError', 'URIError', 'AggregateError'].includes(error.name) ? error.name : 'Error';
  const frames = (String(error.stack || '').match(/\/app\/[a-zA-Z0-9_./()-]+:\d+:\d+/g) || []).slice(0, 12).join('\n');
  return { error: { type, ...(frames ? { stack_trace: frames } : {}) } };
}
install();
module.exports = { publicPath, errorDetails };
