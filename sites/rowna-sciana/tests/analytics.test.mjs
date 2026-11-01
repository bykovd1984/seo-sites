import test from 'node:test';
import assert from 'node:assert/strict';
import { sanitizedLocation, sanitizedReferrer } from '../lib/analytics.ts';
test('analytics excludes search terms, arbitrary query values and fragments from page location',()=>{
 assert.equal(sanitizedLocation('https://rownasciana.site/szukaj?q=my-email@example.com#private'),'https://rownasciana.site/szukaj');
 assert.equal(sanitizedLocation('https://rownasciana.site/?utm_source=bing&utm_medium=organic&email=person@example.com'),'https://rownasciana.site/?utm_source=bing&utm_medium=organic');
 assert.equal(sanitizedReferrer('https://example.com/article?q=private#data'),'https://example.com/article');
 assert.equal(sanitizedReferrer(''),'');
});
