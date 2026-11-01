import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
test('migrated article bodies retain the original byte checksums',()=>{
 const manifest=JSON.parse(fs.readFileSync('content/source-checksums.json','utf8'));
 for (const entry of manifest) assert.equal(createHash('sha256').update(fs.readFileSync(entry.path)).digest('hex').toUpperCase(),entry.sha256);
});
