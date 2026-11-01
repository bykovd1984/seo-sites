import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";
import { AnalyticsConsent } from "@/components/analytics-consent";
import { SITE_URL } from "@/lib/site";
export const metadata: Metadata = {
 metadataBase:new URL(SITE_URL),
 title:{default:"Równa ściana — małe naprawy, dobre decyzje",template:"%s | Równa ściana"},
 description:"Praktyczne poradniki o przygotowaniu ścian i poprawianiu błędów malowania. Ilustracje, konkretne kroki i źródła producentów.",
 robots:{index:true,follow:true},
 alternates:{canonical:"/"},
 openGraph:{type:"website",siteName:"Równa ściana",locale:"pl_PL",url:SITE_URL},
 icons:{icon:"/favicon.svg",shortcut:"/favicon.svg"},
};
export default function RootLayout({children}:{children:React.ReactNode}) {
 return <html lang="pl"><body id="top"><AnalyticsConsent><Header />{children}<Footer /></AnalyticsConsent></body></html>;
}
