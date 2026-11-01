import { ArrowUpRight, Clock3 } from "lucide-react";
import { imageAttributes } from "@/lib/images";
import type { Article } from "@/lib/articles";
export function ArticleCard({ article }: { article: Article }) {
  return <a className="article-card" href={`/poradniki/${article.slug}`}><div className="card-image"><img {...imageAttributes(article.coverImage, "card")} alt={article.coverAlt} width="1536" height="1024" loading="lazy" /><span className="image-label">ILUSTRACJA</span></div><div className="card-copy"><div className="eyebrow"><span>{article.category}</span><span className="read-time"><Clock3 size={14} />{article.readingMinutes} min</span></div><h3>{article.title}</h3><p>{article.description}</p><span className="text-link">Przeczytaj poradnik <ArrowUpRight size={20} /></span></div></a>;
}
