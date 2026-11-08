import { Fragment } from "react";
import type { Metadata, Assets } from "@/lib/metadata";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";
import { AnalyticsConsent } from "@/components/analytics-consent";
import { SITE_URL } from "@/lib/site";
export const metadata: Metadata = {
 title:{default:"Równa ściana — małe naprawy, dobre decyzje",template:"%s | Równa ściana"},
 description:"Praktyczne poradniki o przygotowaniu ścian i poprawianiu błędów malowania. Ilustracje, konkretne kroki i źródła producentów.",
 robots:{index:true,follow:true},
 alternates:{canonical:"/"},
 openGraph:{type:"website",siteName:"Równa ściana",locale:"pl_PL",url:SITE_URL},
};
function absolute(value: string) { const url = new URL(value, SITE_URL); return url.pathname === '/' && !url.search && !url.hash ? SITE_URL : url.href; }
export default function RootLayout({ children, pageMetadata = {}, assets }: { children: React.ReactNode; pageMetadata?: Metadata; assets: Assets }) {
 const rootTitle = metadata.title as { default: string; template: string };
 const title = typeof pageMetadata.title === 'string' ? rootTitle.template.replace('%s', pageMetadata.title) : rootTitle.default;
 const description = pageMetadata.description || metadata.description;
 const robots = pageMetadata.robots || metadata.robots!;
 const canonical = pageMetadata.alternates?.canonical || (robots.index ? metadata.alternates?.canonical : undefined);
 const graph = { ...metadata.openGraph, ...pageMetadata.openGraph };
 return <html lang="pl"><head>
  <meta charSet="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title><meta name="description" content={description}/><meta name="robots" content={`${robots.index ? 'index' : 'noindex'}, ${robots.follow ? 'follow' : 'nofollow'}`}/>
  {canonical && <link rel="canonical" href={absolute(canonical)}/>}
  <link rel="icon" href="/favicon.svg"/><link rel="shortcut icon" href="/favicon.svg"/>
  <meta property="og:title" content={graph.title || title}/><meta property="og:description" content={graph.description || description}/><meta property="og:type" content={graph.type}/><meta property="og:site_name" content={graph.siteName}/><meta property="og:locale" content={graph.locale}/>
  {graph.url && <meta property="og:url" content={absolute(graph.url)}/>}
  {graph.images?.map(image => <Fragment key={image.url}><meta property="og:image" content={absolute(image.url)}/><meta property="og:image:width" content={String(image.width)}/><meta property="og:image:height" content={String(image.height)}/><meta property="og:image:alt" content={image.alt}/></Fragment>)}
  <meta name="twitter:card" content={graph.images?.length ? 'summary_large_image' : 'summary'}/><meta name="twitter:title" content={graph.title || title}/><meta name="twitter:description" content={graph.description || description}/>
  {graph.images?.map(image => <Fragment key={image.url}><meta name="twitter:image" content={absolute(image.url)}/><meta name="twitter:image:alt" content={image.alt}/><meta name="twitter:image:width" content={String(image.width)}/><meta name="twitter:image:height" content={String(image.height)}/></Fragment>)}
  <link rel="stylesheet" href={assets.stylesheet}/><script defer src={assets.script}/>
 </head><body id="top"><Header/>{children}<Footer/><AnalyticsConsent/></body></html>;
}
