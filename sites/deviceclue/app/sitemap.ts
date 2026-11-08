import { allArticles } from '@/lib/articles';
import { categories,site } from '@/lib/site';
export default function sitemap(){const articles=allArticles();return ['','/about','/privacy',...categories.filter(c=>articles.some(a=>a.category===c.id)).map(c=>`/topics/${c.id}`),...articles.map(a=>`/guides/${a.slug}`)].map(p=>({url:site.url+p}));}
