"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { GA_MEASUREMENT_ID } from "@/lib/site";
import { CONSENT_KEY, sanitizedLocation, sanitizedReferrer, type ConsentChoice } from "@/lib/analytics";
type AnalyticsWindow=Window & {dataLayer?:unknown[];gtag?:(...args:unknown[])=>void};
const ConsentSettings=createContext<()=>void>(()=>{});
export function PrivacySettingsButton() {
 const open=useContext(ConsentSettings);
 return <button type="button" className="privacy-settings-link" onClick={open}>Ustawienia prywatności</button>;
}
export function AnalyticsConsent({children}:{children:React.ReactNode}) {
 const [choice,setChoice]=useState<ConsentChoice|null>(null);
 const [ready,setReady]=useState(false);
 const [open,setOpen]=useState(false);
 useEffect(()=>{
   try {const saved=localStorage.getItem(CONSENT_KEY); if(saved==="accepted"||saved==="rejected") setChoice(saved); else setOpen(true);}
   catch {setOpen(true);}
   setReady(true);
 },[]);
 useEffect(()=>{
   if(!ready) return;
   const analytics=window as AnalyticsWindow;
   if(choice!=="accepted") {
     (window as unknown as Record<string,unknown>)["ga-disable-"+GA_MEASUREMENT_ID]=true;
     analytics.gtag?.("consent","update",{analytics_storage:"denied",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied"});
     return;
   }
   (window as unknown as Record<string,unknown>)["ga-disable-"+GA_MEASUREMENT_ID]=false;
   if(document.getElementById("site-google-tag")) {
     analytics.gtag?.("consent","update",{analytics_storage:"granted",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied"});
     return;
   }
   analytics.dataLayer=analytics.dataLayer||[];
   analytics.gtag=function(){analytics.dataLayer?.push(arguments);};
   analytics.gtag("consent","default",{analytics_storage:"denied",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied"});
   analytics.gtag("consent","update",{analytics_storage:"granted",ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied"});
   analytics.gtag("js",new Date());
   analytics.gtag("config",GA_MEASUREMENT_ID,{
     allow_google_signals:false,allow_ad_personalization_signals:false,
     page_location:sanitizedLocation(location.href),page_referrer:sanitizedReferrer(document.referrer),
     cookie_expires:15552000,
   });
   const script=document.createElement("script");
   script.id="site-google-tag"; script.async=true;
   script.src="https://www.googletagmanager.com/gtag/js?id="+GA_MEASUREMENT_ID;
   document.head.appendChild(script);
 },[choice,ready]);
 function choose(next:ConsentChoice) {
   try {localStorage.setItem(CONSENT_KEY,next);} catch {}
   if(next==="rejected") {
     for(const cookie of document.cookie.split(";")) {
       const name=cookie.trim().split("=")[0];
       if(name==="_ga"||name.startsWith("_ga_")) {
         for(const domain of ["",location.hostname,"."+location.hostname]) document.cookie=name+"=; Max-Age=0; Path=/"+(domain?"; Domain="+domain:"");
       }
     }
   }
   setChoice(next);setOpen(false);
 }
 return <ConsentSettings.Provider value={()=>setOpen(true)}>{children}
   {ready&&open&&<aside className="consent-banner" aria-label="Ustawienia prywatności">
     <div><h2>Twój wybór prywatności</h2><p>Za Twoją zgodą używamy Google Analytics, aby poznać ruch i korzystanie z poradników. Możesz odmówić i nadal korzystać z całej strony. <a href="/prywatnosc">Szczegóły prywatności</a></p></div>
     <div className="consent-actions"><button type="button" onClick={()=>choose("rejected")}>Tylko niezbędne</button><button type="button" onClick={()=>choose("accepted")}>Zgadzam się na analitykę</button></div>
   </aside>}
 </ConsentSettings.Provider>;
}
