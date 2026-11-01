import test from 'node:test';
import assert from 'node:assert/strict';
import { analyticsConfiguration, sanitizedLocation, sanitizedReferrer, CONSENT_KEY, GA_MEASUREMENT_ID } from '../lib/analytics.ts';

test('analytics strips query values and fragments on every page, including search', () => {
  assert.equal(sanitizedLocation('https://deviceclue.site/search?q=private@example.com&utm_source=private#secret'), 'https://deviceclue.site/search');
  assert.equal(sanitizedLocation('https://deviceclue.site/guides/fridge-coldest-setting?token=private'), 'https://deviceclue.site/guides/fridge-coldest-setting');
  assert.equal(sanitizedReferrer('https://example.com/article?email=private#secret'), 'https://example.com/article');
  assert.equal(sanitizedReferrer(''), '');
  assert.equal(sanitizedReferrer('about:blank'), '');
});

test('the new stream disables automatic duplicate views and advertising signals', () => {
  const config = analyticsConfiguration('https://deviceclue.site/search?q=private', 'https://example.com/?q=private');
  assert.equal(config.send_page_view, false);
  assert.equal(config.allow_google_signals, false);
  assert.equal(config.allow_ad_personalization_signals, false);
  assert.equal(config.page_location, 'https://deviceclue.site/search');
  assert.equal(config.page_referrer, 'https://example.com/');
  assert.equal(GA_MEASUREMENT_ID, 'G-VRLR3QNXZQ');
  assert.ok(CONSENT_KEY.startsWith('deviceclue:'));
});
