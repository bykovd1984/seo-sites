import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArrowLeft, Clock3, BookOpen, ArrowUpRight } from "lucide-react";
import { allArticles, findArticle, polishDate } from "@/lib/articles";
import catalog from "@/content/catalog.json";
import { parseMarkdown } from "@/lib/content";
import { Markdown } from "@/components/markdown";
import { Checklist, ReaderTools } from "@/components/reader-tools";
export const dynamic = "force-dynamic";
type Props = { params: Promise<{ slug: string }> };
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const a = await findArticle((await params).slug);
  return a ? { title: a.title, description: a.description } : { title: "Nie znaleziono poradnika" };
}
export default async function ArticlePage({ params }: Props) {
  const article = await findArticle((await params).slug);
  if (!article) notFound();
  const presentation = catalog.find(entry => entry.slug === article.slug);
  const related = (await allArticles()).filter(entry => entry.slug !== article.slug && entry.category === article.category).slice(0, 2);
  const headings = parseMarkdown(article.bodyMarkdown).filter(b => b.type === "heading" && b.level === 2);
  return <main id="main" className="article-shell container"><a href="/#poradniki" className="back-link"><ArrowLeft size={16} />Wszystkie poradniki</a><header className="article-header"><p className="eyebrow">Malowanie / Drobne naprawy</p><h1>{article.title}</h1><div className="article-meta"><span><Clock3 size={15} />{article.readingMinutes} min czytania</span><span>Źródła sprawdzone: {polishDate(article.checkedDate)}</span></div><p className="review-note">Opracowanie z pomocą AI na podstawie dokumentacji producentów. Wersja po redakcji, przed niezależną recenzją techniczną.</p><ReaderTools /></header><div className="article-layout"><div className="article-content"><Markdown source={article.bodyMarkdown} />{presentation && <Checklist key={article.slug} items={presentation.checklist} storageKey={presentation.checklistStorageKey} />}{related.length > 0 && <nav className="related-guides" aria-label="Powiązane poradniki"><p className="eyebrow">Powiązany problem</p>{related.map(entry => <a className="text-link" key={entry.slug} href={`/poradniki/${entry.slug}`}>{entry.title}<ArrowUpRight size={18} /></a>)}</nav>}<div className="article-end"><BookOpen size={24} /><div><h3>Warto wiedzieć, skąd pochodzi rada.</h3><p>Odnośniki przy tekście prowadzą do dokumentacji i porad producentów.</p><a href="/o-poradniku" className="text-link">Jak tworzymy treści <ArrowUpRight size={16} /></a></div></div></div><aside className="article-aside"><nav aria-label="Spis treści" className="toc"><p className="eyebrow">W tym poradniku</p><ol>{headings.map(b => b.type === "heading" && <li key={b.id}><a href={`#${b.id}`}>{b.text}</a></li>)}</ol><div className="toc-note"><span>Najpierw rozpoznanie.</span><p>Wygląd uszkodzenia to wskazówka, nie gotowa diagnoza.</p></div></nav></aside></div></main>;
}
