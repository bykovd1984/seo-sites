import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { build, transform } from 'esbuild';
import postcss from 'postcss';
import tailwindcss from '@tailwindcss/postcss';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'dist');
fs.mkdirSync(path.join(output, 'public/assets'), { recursive: true });
const client = await build({ absWorkingDir: root, entryPoints: ['browser/site.ts'], bundle: true, platform: 'browser', format: 'iife', target: 'es2020', minify: true, write: false, metafile: true });
if (Object.keys(client.metafile.inputs).some(filename => filename.includes('node_modules/'))) throw new Error('Browser code must not contain framework dependencies');
const processed = await postcss([tailwindcss({ base: root })]).process(fs.readFileSync(path.join(root, 'app/globals.css'), 'utf8'), { from: path.join(root, 'app/globals.css') });
const css = await transform(processed.css, { loader: 'css', minify: true, target: 'es2020' });
const assets = {};
for (const [name, extension, body] of [['script', 'js', client.outputFiles[0].contents], ['stylesheet', 'css', Buffer.from(css.code)]]) {
  const hash = createHash('sha256').update(body).digest('hex').slice(0, 12);
  const filename = `assets/site.${hash}.${extension}`;
  fs.writeFileSync(path.join(output, 'public', filename), body);
  assets[name] = '/' + filename;
}
fs.writeFileSync(path.join(output, 'assets.json'), JSON.stringify(assets));
await build({ absWorkingDir: root, entryPoints: ['server/index.tsx'], bundle: true, platform: 'node', format: 'cjs', target: 'node24', outfile: path.join(output, 'server.cjs'), minify: true, define: { 'process.env.NODE_ENV': '"production"' }, external: ['node:sqlite'] });
console.log(`Built server-only templates and ${client.outputFiles[0].contents.length} bytes of plain browser JavaScript.`);
