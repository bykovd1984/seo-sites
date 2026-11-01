export type ConsentChoice = "accepted" | "rejected";
export const CONSENT_KEY = "rowna-sciana:analytics-consent:v1";
export function sanitizedLocation(raw:string) {
 const url=new URL(raw);
 url.hash="";
 for(const key of [...url.searchParams.keys()]) if(!["utm_source","utm_medium","utm_campaign"].includes(key)) url.searchParams.delete(key);
 return url.href;
}
export function sanitizedReferrer(raw:string) {
 try {const url=new URL(raw); return url.origin+url.pathname;} catch {return "";}
}
