'use client';
import { useState } from 'react';
import type { ArticleSummary } from '@/lib/types';
import { categories } from '@/lib/site';
import { ArticleCard } from './article-card';
export function Explorer({ articles }: { articles: ArticleSummary[] }) {
  const [active, setActive] = useState('all');
  const visible = active === 'all' ? articles : articles.filter(a => a.category === active);
  return <><div className="guide-filters" role="group" aria-label="Filter guides by topic"><button type="button" aria-pressed={active === 'all'} onClick={() => setActive('all')}>All guides <span>{articles.length.toString().padStart(2,'0')}</span></button>{categories.map(c => <button type="button" key={c.id} aria-pressed={active === c.id} onClick={() => setActive(c.id)}>{c.short}<span>{articles.filter(a=>a.category===c.id).length.toString().padStart(2,'0')}</span></button>)}</div><p className="sr-only" aria-live="polite">{visible.length} guides shown</p><div className="guides-grid">{visible.map(article => <ArticleCard key={article.slug} article={article}/>)}</div></>;
}
