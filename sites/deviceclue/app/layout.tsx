import type { Metadata } from 'next';
import { site } from '@/lib/site';
import { Header } from '@/components/header';
import { Footer } from '@/components/footer';
import { AnalyticsConsent } from '@/components/analytics-consent';
import './globals.css';
import './consent.css';
export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: { default: 'DeviceClue — Make sense of your equipment', template: '%s | DeviceClue' },
  description: site.description,
  robots: { index: true, follow: true },
  openGraph: { type: 'website', siteName: site.name, locale: 'en_GB', images: [{url:'/opengraph-image.png',width:1200,height:630,alt:'DeviceClue — Understand the signal. Find the next step.'}] },
};
export default function RootLayout({ children }: Readonly<{children:React.ReactNode}>) {return <html lang="en"><body><AnalyticsConsent><a className="skip-link" href="#main">Skip to content</a><Header/>{children}<Footer/></AnalyticsConsent></body></html>;}
