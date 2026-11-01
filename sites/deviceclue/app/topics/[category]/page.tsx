import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { categories } from '@/lib/site';
import { allArticles, summarize } from '@/lib/articles';
import { ArticleCard } from '@/components/article-card';
export const dynamic='force-dynamic';
type Props={params:Promise<{category:string}>};
export async function generateMetadata({params}:Props):Promise<Metadata>{const {category}=await params;const c=categories.find(x=>x.id===category);return c&&allArticles().some(a=>a.category===category)?{title:c.name,description:c.description,alternates:{canonical:`/topics/${c.id}`}}:{title:'Topic not found'};}
export default async function Topic({params}:Props){const {category}=await params;const c=categories.find(x=>x.id===category);if(!c)notFound();const articles=allArticles().filter(a=>a.category===category);if(!articles.length)notFound();return <main id="main" className="container topic-page"><nav className="breadcrumb" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><span>{c.name}</span></nav><p className="eyebrow">THE EQUIPMENT FIELD GUIDE</p><h1 className="page-title">{c.name}</h1><p className="page-intro">{c.description}. Start with the question you have and check the details for your model.</p><p className="search-results-count">{articles.length.toString().padStart(2,'0')} GUIDES</p><div className="guides-grid">{articles.map(a=><ArticleCard key={a.slug} article={summarize(a)}/>)}</div></main>;}
