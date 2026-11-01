'use strict';
const { randomUUID } = require('node:crypto');

function createTransport({ endpoint, apiKey, version = 'local', fetchImpl = fetch, now = Date.now, maxQueue = 1000, batchSize = 50 }) {
  const queue = [];
  let busy = false;
  let failures = 0;
  let retryAt = 0;
  let lastWarning = 0;
  const warn = () => {
    if (now() - lastWarning > 60000) {
      lastWarning = now();
      process.stderr.write('DeviceClue log delivery delayed or queue full; details and credentials omitted.\n');
    }
  };
  function enqueue(fields) {
    if (queue.length >= maxQueue) { queue.shift(); warn(); }
    queue.push({ id: randomUUID(), document: {
      '@timestamp': new Date().toISOString(),
      service: { name: 'deviceclue', environment: 'production', version },
      ...fields,
    } });
  }
  async function flush() {
    if (busy || !queue.length || now() < retryAt) return;
    busy = true;
    const batch = queue.splice(0, batchSize);
    let pending = batch;
    try {
      const body = batch.map(item => JSON.stringify({ create: { _index: 'logs-deviceclue-prod', _id: item.id } }) + '\n' + JSON.stringify(item.document)).join('\n') + '\n';
      const response = await fetchImpl(endpoint.replace(/\/$/, '') + '/_bulk', {
        method: 'POST', headers: { Authorization: 'ApiKey ' + apiKey, 'Content-Type': 'application/x-ndjson' },
        body, signal: AbortSignal.timeout(1500),
      });
      if (!response.ok) throw new Error('Log delivery failed');
      const result = await response.json();
      if (!Array.isArray(result.items) || result.items.length !== batch.length) throw new Error('Invalid bulk response');
      pending = batch.filter((_, i) => {
        const status = result.items[i]?.create?.status;
        if ((status >= 200 && status < 300) || status === 409) return false;
        if (status !== 429 && !(status >= 500)) { warn(); return false; }
        return true;
      });
      if (pending.length) throw new Error('Partial delivery');
      failures = 0;
    } catch {
      failures++;
      retryAt = now() + Math.min(30000, 1000 * 2 ** Math.min(failures, 5));
      queue.unshift(...pending);
      if (queue.length > maxQueue) queue.splice(0, queue.length - maxQueue);
      warn();
    } finally { busy = false; }
  }
  const timer = setInterval(() => { void flush(); }, 2000);
  timer.unref();
  return { enqueue, flush, close: () => clearInterval(timer) };
}
module.exports = { createTransport };
