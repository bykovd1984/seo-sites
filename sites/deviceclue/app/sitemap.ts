import type { MetadataRoute } from 'next';
import { allArticles } from '@/lib/articles';
import { categories,site } from '@/lib/site';
export const dynamic='force-dynamic';
export default function sitemap():MetadataRoute.Sitemap{return ['','/about','/privacy',...categories.map(c=>`/topics/${c.id}`),...allArticles().map(a=>`/guides/${a.slug}`)].map(p=>({url:site.url+p}));}
