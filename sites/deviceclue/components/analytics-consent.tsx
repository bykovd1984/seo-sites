'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { analyticsConfiguration, CONSENT_KEY, GA_MEASUREMENT_ID, TAG_SCRIPT_ID, type ConsentChoice } from '@/lib/analytics';

type AnalyticsWindow = Window & { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void };
const Settings = createContext<() => void>(() => {});
const denied = { analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' };

export function PrivacySettingsButton() {
  const open = useContext(Settings);
  return <button type="button" className="privacy-settings-link" onClick={open}>Privacy settings</button>;
}

export function AnalyticsConsent({ children }: { children: React.ReactNode }) {
  const [choice, setChoice] = useState<ConsentChoice | null>(null);
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(CONSENT_KEY);
      if (saved === 'accepted' || saved === 'rejected') setChoice(saved);
      else setOpen(true);
    } catch { setOpen(true); }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready || choice !== 'accepted') return;
    const analytics = window as AnalyticsWindow;
    (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = false;
    if (document.getElementById(TAG_SCRIPT_ID)) return;
    analytics.dataLayer = analytics.dataLayer || [];
    analytics.gtag = function () { analytics.dataLayer?.push(arguments); };
    analytics.gtag('consent', 'default', denied);
    analytics.gtag('consent', 'update', { ...denied, analytics_storage: 'granted' });
    analytics.gtag('js', new Date());
    const configuration = analyticsConfiguration(location.href, document.referrer);
    analytics.gtag('config', GA_MEASUREMENT_ID, configuration);
    analytics.gtag('event', 'page_view', {
      send_to: GA_MEASUREMENT_ID,
      page_title: document.title,
      page_location: configuration.page_location,
      page_referrer: configuration.page_referrer,
    });
    const script = document.createElement('script');
    script.id = TAG_SCRIPT_ID;
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_MEASUREMENT_ID;
    document.head.appendChild(script);
  }, [choice, ready]);

  function choose(next: ConsentChoice) {
    try { localStorage.setItem(CONSENT_KEY, next); } catch {}
    const loaded = !!document.getElementById(TAG_SCRIPT_ID);
    if (next === 'rejected') {
      (window as unknown as Record<string, unknown>)['ga-disable-' + GA_MEASUREMENT_ID] = true;
      (window as AnalyticsWindow).gtag?.('consent', 'update', denied);
      for (const cookie of document.cookie.split(';')) {
        const name = cookie.trim().split('=')[0];
        if (name === '_ga' || name.startsWith('_ga_')) {
          for (const domain of ['', location.hostname, '.' + location.hostname]) {
            document.cookie = name + '=; Max-Age=0; Path=/' + (domain ? '; Domain=' + domain : '');
          }
        }
      }
    }
    setChoice(next);
    setOpen(false);
    if (next === 'rejected' && loaded) location.reload();
  }

  return <Settings.Provider value={() => setOpen(true)}>{children}
    {ready && open && <aside className="consent-banner" aria-label="Privacy choices">
      <div><p className="eyebrow">YOUR PRIVACY, YOUR CALL</p><h2>A little insight. With your permission.</h2><p>We use optional Google Analytics to understand which guides are useful. You can decline and use every page. <a href="/privacy">How your data is used</a></p></div>
      <div className="consent-actions"><button type="button" onClick={() => choose('rejected')}>Essential only</button><button type="button" onClick={() => choose('accepted')}>Allow analytics</button></div>
    </aside>}
  </Settings.Provider>;
}
