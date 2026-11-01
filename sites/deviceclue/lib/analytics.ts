export const GA_MEASUREMENT_ID = 'G-VRLR3QNXZQ';
export const CONSENT_KEY = 'deviceclue:analytics-consent:v1';
export const TAG_SCRIPT_ID = 'deviceclue-google-tag';
export type ConsentChoice = 'accepted' | 'rejected';

export function sanitizedLocation(raw: string) {
  const url = new URL(raw);
  return url.origin + url.pathname;
}

export function sanitizedReferrer(raw: string) {
  try {
    const url = new URL(raw);
    return ['https:', 'http:'].includes(url.protocol) ? url.origin + url.pathname : '';
  } catch { return ''; }
}

export function analyticsConfiguration(location: string, referrer: string) {
  return {
    send_page_view: false,
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    page_location: sanitizedLocation(location),
    page_referrer: sanitizedReferrer(referrer),
    cookie_expires: 15552000,
  };
}
