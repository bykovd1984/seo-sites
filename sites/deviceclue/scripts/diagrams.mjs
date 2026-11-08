import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

// Reuse the existing vector artwork without putting every card's SVG in the page and RSC payload.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = fs.readFileSync(path.join(root, 'components/diagram.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.React, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { Diagram } = await import('data:text/javascript,' + encodeURIComponent(
  `import React from ${JSON.stringify(import.meta.resolve('react'))};\n${compiled}`
));
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'content/catalog.json'), 'utf8'));
const directory = path.join(root, 'public/diagrams');
fs.mkdirSync(directory, { recursive: true });
for (const kind of [...new Set(catalog.map(article => article.diagram))].sort()) {
  if (!/^[a-z]+$/.test(kind)) throw new Error('Invalid diagram name');
  const html = renderToStaticMarkup(React.createElement(Diagram, { kind, compact: true }));
  const svg = html.match(/<svg\b[\s\S]*<\/svg>/)?.[0];
  if (!svg) throw new Error(`Missing diagram: ${kind}`);
  fs.writeFileSync(path.join(directory, `${kind}.svg`), svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" color="#637365" ') + '\n');
}
console.log('Compact SVG diagrams generated from components/diagram.tsx.');
