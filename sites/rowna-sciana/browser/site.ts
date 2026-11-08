import { GA_MEASUREMENT_ID } from '../lib/site';
import { CONSENT_KEY, sanitizedLocation, sanitizedReferrer, type ConsentChoice } from '../lib/analytics';

type AnalyticsWindow = Window & { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void };
const analytics = window as AnalyticsWindow;
const banner = document.querySelector<HTMLElement>('[data-consent-banner]');
const tagId = 'site-google-tag';
const denied = { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' };

function loadAnalytics() {
  (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = false;
  if (document.getElementById(tagId)) return;
  analytics.dataLayer ||= [];
  analytics.gtag = function () { analytics.dataLayer?.push(arguments); };
  analytics.gtag('consent', 'default', denied);
  analytics.gtag('consent', 'update', { ...denied, analytics_storage: 'granted' });
  analytics.gtag('js', new Date());
  analytics.gtag('config', GA_MEASUREMENT_ID, { allow_google_signals: false, allow_ad_personalization_signals: false, page_location: sanitizedLocation(location.href), page_referrer: sanitizedReferrer(document.referrer), cookie_expires: 15552000 });
  const script = document.createElement('script');
  script.id = tagId; script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_MEASUREMENT_ID;
  document.head.appendChild(script);
}

function choose(next: ConsentChoice) {
  try { localStorage.setItem(CONSENT_KEY, next); } catch { /* The choice still applies to this document. */ }
  if (banner) banner.hidden = true;
  if (next === 'accepted') { loadAnalytics(); return; }
  const loaded = !!document.getElementById(tagId);
  (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = true;
  analytics.gtag?.('consent', 'update', denied);
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.trim().split('=')[0];
    if (name === '_ga' || name.startsWith('_ga_')) {
      for (const domain of ['', location.hostname, '.' + location.hostname]) document.cookie = name + '=; Max-Age=0; Path=/' + (domain ? '; Domain=' + domain : '');
    }
  }
  if (loaded) location.reload();
}

const menu = document.querySelector<HTMLElement>('#main-navigation');
const menuButton = document.querySelector<HTMLButtonElement>('[data-menu-toggle]');
function setMenu(open: boolean) {
  menu?.classList.toggle('open', open);
  menuButton?.setAttribute('aria-expanded', String(open));
  menuButton?.setAttribute('aria-label', open ? 'Zamknij menu' : 'Otwórz menu');
  if (menuButton) {
    menuButton.querySelector<HTMLElement>('[data-menu-closed]')!.hidden = open;
    menuButton.querySelector<HTMLElement>('[data-menu-open]')!.hidden = !open;
  }
}

async function copyLink(button: Element) {
  const status = button.closest('[data-reader-tools]')?.querySelector('[role="status"]');
  try { await navigator.clipboard.writeText(location.href.split('#')[0]); if (status) status.textContent = 'Link skopiowany'; }
  catch { if (status) status.textContent = 'Skopiuj adres z paska przeglądarki.'; }
}

function inputs(section: Element) { return [...section.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')]; }
function count(section: Element) {
  const items = inputs(section);
  const counter = section.querySelector('[data-checklist-count]');
  if (counter) counter.textContent = `${items.filter(input => input.checked).length}/${items.length}`;
}
function storageNotice(section: Element) {
  const notice = section.querySelector('[data-checklist-notice]');
  if (notice) notice.textContent = 'Zaznaczenia są dostępne tylko do zamknięcia tej strony.';
}
for (const section of document.querySelectorAll<HTMLElement>('[data-checklist]')) {
  const items = inputs(section);
  try {
    const saved = JSON.parse(localStorage.getItem(section.dataset.storageKey!) || 'null');
    if (Array.isArray(saved) && saved.length === items.length && saved.every(value => typeof value === 'boolean')) items.forEach((input, index) => { input.checked = saved[index]; });
  } catch { storageNotice(section); }
  count(section);
}
document.addEventListener('change', event => {
  if (!(event.target instanceof HTMLInputElement) || event.target.type !== 'checkbox') return;
  const section = event.target.closest<HTMLElement>('[data-checklist]');
  if (!section) return;
  count(section);
  try { localStorage.setItem(section.dataset.storageKey!, JSON.stringify(inputs(section).map(input => input.checked))); }
  catch { storageNotice(section); }
});
document.addEventListener('click', event => {
  if (!(event.target instanceof Element)) return;
  const target = event.target;
  if (target.closest('[data-privacy-settings]')) { if (banner) banner.hidden = false; return; }
  const choice = target.closest<HTMLElement>('[data-consent]')?.dataset.consent;
  if (choice === 'accepted' || choice === 'rejected') { choose(choice); return; }
  if (target.closest('[data-menu-toggle]')) { setMenu(menuButton?.getAttribute('aria-expanded') !== 'true'); return; }
  if (target.closest('#main-navigation a')) setMenu(false);
  if (target.closest('[data-reader-print]')) window.print();
  const copy = target.closest('[data-reader-copy]');
  if (copy) void copyLink(copy);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && menuButton?.getAttribute('aria-expanded') === 'true') { setMenu(false); menuButton.focus(); }
});

let saved: string | null = null;
try { saved = localStorage.getItem(CONSENT_KEY); } catch { /* Ask again when storage is unavailable. */ }
if (saved === 'accepted') loadAnalytics();
else {
  (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = true;
  if (saved !== 'rejected' && banner) banner.hidden = false;
}
