import { ArrowUpRight, Clock3 } from 'lucide-react';
import { categories } from '@/lib/site';
import type { ArticleSummary } from '@/lib/types';
import { Diagram } from './diagram';
export function ArticleCard({ article, featured = false }: { article: ArticleSummary; featured?: boolean }) {
  const category = categories.find(c => c.id === article.category);
  return <article className={`guide-card${featured ? ' guide-card-featured' : ''}`}><a className="card-visual" href={`/guides/${article.slug}`} tabIndex={-1} aria-hidden="true"><span className="diagram-label">{article.brand.toUpperCase()} / {article.type.toUpperCase()}</span><Diagram kind={article.diagram} compact/><span className="diagram-code">DC—{article.diagram.toUpperCase()}</span><span className="card-arrow"><ArrowUpRight size={21}/></span></a><div className="card-content"><div className="card-category">{category?.short}<span>·</span>{article.type}</div><h3><a href={`/guides/${article.slug}`}>{article.shortTitle}</a></h3><p>{article.description}</p><div className="card-footer"><span><Clock3 size={13}/>{article.readingMinutes} min read</span><span>{article.brand}</span></div></div></article>;
}
