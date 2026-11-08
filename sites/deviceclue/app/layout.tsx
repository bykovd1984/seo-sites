import { Fragment } from 'react';
import type { Metadata, Assets } from '@/lib/metadata';
import { site } from '@/lib/site';
import { Header } from '@/components/header';
import { Footer } from '@/components/footer';
import { AnalyticsConsent } from '@/components/analytics-consent';
export const metadata: Metadata = {
  title: { default: 'DeviceClue — Make sense of your equipment', template: '%s | DeviceClue' },
  description: site.description,
  robots: { index: true, follow: true },
  openGraph: { type: 'website', siteName: site.name, locale: 'en_GB', images: [{url:'/opengraph-image.png',width:1200,height:630,alt:'DeviceClue — Understand the signal. Find the next step.'}] },
};
export default function RootLayout({ children, pageMetadata = {}, assets }: Readonly<{children:React.ReactNode; pageMetadata?:Metadata; assets:Assets}>) {
  const rootTitle = metadata.title as { default: string; template: string };
  const title = typeof pageMetadata.title === 'string' ? rootTitle.template.replace('%s', pageMetadata.title) : rootTitle.default;
  const description = pageMetadata.description || metadata.description;
  const robots = pageMetadata.robots || metadata.robots!;
  const canonical = pageMetadata.alternates?.canonical;
  const graph = { ...metadata.openGraph, ...pageMetadata.openGraph };
  return <html lang="en"><head>
    <meta charSet="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{title}</title><meta name="description" content={description}/>
    <meta name="robots" content={`${robots.index ? 'index' : 'noindex'}, ${robots.follow ? 'follow' : 'nofollow'}`}/>
    {canonical && <link rel="canonical" href={new URL(canonical, site.url).href}/>}
    <link rel="icon" href="/favicon.svg" type="image/svg+xml"/>
    <meta property="og:title" content={graph.title || title}/><meta property="og:description" content={graph.description || description}/>
    <meta property="og:type" content={graph.type}/><meta property="og:site_name" content={graph.siteName}/><meta property="og:locale" content={graph.locale}/>
    {(graph.url || canonical) && <meta property="og:url" content={new URL(graph.url || canonical!, site.url).href}/>}
    {graph.publishedTime && <meta property="article:published_time" content={graph.publishedTime}/>}
    {graph.images?.map(image => <Fragment key={image.url}><meta property="og:image" content={new URL(image.url, site.url).href}/><meta property="og:image:width" content={String(image.width)}/><meta property="og:image:height" content={String(image.height)}/><meta property="og:image:alt" content={image.alt}/></Fragment>)}
    <meta name="twitter:card" content="summary_large_image"/><meta name="twitter:title" content={graph.title || title}/><meta name="twitter:description" content={graph.description || description}/>
    {graph.images?.map(image => <Fragment key={image.url}><meta name="twitter:image" content={new URL(image.url, site.url).href}/><meta name="twitter:image:alt" content={image.alt}/><meta name="twitter:image:width" content={String(image.width)}/><meta name="twitter:image:height" content={String(image.height)}/></Fragment>)}
    <link rel="stylesheet" href={assets.stylesheet}/><script defer src={assets.script}/>
  </head><body><a className="skip-link" href="#main">Skip to content</a><Header/>{children}<Footer/><AnalyticsConsent/></body></html>;
}
