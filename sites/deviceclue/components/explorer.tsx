import type { ArticleSummary } from '@/lib/types';
import { categories } from '@/lib/site';
import { ArticleCard } from './article-card';
export function Explorer({ articles }: { articles: ArticleSummary[] }) {
  const topics = categories.map(category => ({
    id: category.id,
    label: category.short,
    count: articles.filter(article => article.category === category.id).length,
  })).filter(topic => topic.count > 0);
  return <div className="guide-explorer">
    <fieldset className="guide-filters">
      <legend className="sr-only">Filter guides by topic</legend>
      {[{ id: 'all', label: 'All guides', count: articles.length }, ...topics].map(topic =>
        <div className="guide-filter-option" key={topic.id}>
          <input className="sr-only" type="radio" name="guide-topic" id={`guide-topic-${topic.id}`} value={topic.id} defaultChecked={topic.id === 'all'}/>
          <label htmlFor={`guide-topic-${topic.id}`}>{topic.label}<span>{topic.count.toString().padStart(2, '0')}</span></label>
        </div>
      )}
    </fieldset>
    <div className="guides-grid">
      {articles.map(article => <div className="guide-slot" data-category={article.category} key={article.slug}>
        <ArticleCard article={article}/>
      </div>)}
    </div>
  </div>;
}
