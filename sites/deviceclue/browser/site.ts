import { analyticsConfiguration, CONSENT_KEY, GA_MEASUREMENT_ID, TAG_SCRIPT_ID, type ConsentChoice } from '../lib/analytics';

type AnalyticsWindow = Window & { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void };
const banner = document.querySelector<HTMLElement>('[data-consent-banner]');
const analytics = window as AnalyticsWindow;
const denied = { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' };

function loadAnalytics() {
  if (document.getElementById(TAG_SCRIPT_ID)) return;
  (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = false;
  analytics.dataLayer ||= [];
  analytics.gtag = function () { analytics.dataLayer?.push(arguments); };
  analytics.gtag('consent', 'default', denied);
  analytics.gtag('consent', 'update', { ...denied, analytics_storage: 'granted' });
  analytics.gtag('js', new Date());
  const configuration = analyticsConfiguration(location.href, document.referrer);
  analytics.gtag('config', GA_MEASUREMENT_ID, configuration);
  analytics.gtag('event', 'page_view', { send_to: GA_MEASUREMENT_ID, page_title: document.title, page_location: configuration.page_location, page_referrer: configuration.page_referrer });
  const script = document.createElement('script');
  script.id = TAG_SCRIPT_ID;
  script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_MEASUREMENT_ID;
  document.head.appendChild(script);
}

function choose(next: ConsentChoice) {
  try { localStorage.setItem(CONSENT_KEY, next); } catch { /* The choice still applies to this document. */ }
  if (banner) banner.hidden = true;
  if (next === 'accepted') { loadAnalytics(); return; }
  const loaded = !!document.getElementById(TAG_SCRIPT_ID);
  (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = true;
  analytics.gtag?.('consent', 'update', denied);
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.trim().split('=')[0];
    if (name === '_ga' || name.startsWith('_ga_')) {
      for (const domain of ['', location.hostname, '.' + location.hostname]) {
        document.cookie = name + '=; Max-Age=0; Path=/' + (domain ? '; Domain=' + domain : '');
      }
    }
  }
  if (loaded) location.reload();
}

document.addEventListener('click', event => {
  if (!(event.target instanceof Element)) return;
  if (event.target.closest('[data-privacy-settings]')) { if (banner) banner.hidden = false; return; }
  const value = event.target.closest<HTMLElement>('[data-consent]')?.dataset.consent;
  if (value === 'accepted' || value === 'rejected') choose(value);
});

let saved: string | null = null;
try { saved = localStorage.getItem(CONSENT_KEY); } catch { /* Ask again if browser storage is unavailable. */ }
if (saved === 'accepted') loadAnalytics();
else if (saved !== 'rejected' && banner) banner.hidden = false;
