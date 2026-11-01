import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArrowLeft, Clock3, BookOpen, ArrowUpRight } from "lucide-react";
import { allArticles, findArticle, polishDate } from "@/lib/articles";
import catalog from "@/content/catalog.json";
import { parseMarkdown } from "@/lib/content";
import { SITE_URL, SITE_NAME } from "@/lib/site";
import { imageAttributes } from "@/lib/images";
import { Markdown } from "@/components/markdown";
import { Checklist, ReaderTools } from "@/components/reader-tools";
export const dynamic = "force-dynamic";
type Props = { params: Promise<{ slug: string }> };
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const a = await findArticle((await params).slug);
  return a ? { title:a.title,description:a.description,alternates:{canonical:"/poradniki/"+a.slug},openGraph:{type:"article",url:SITE_URL+"/poradniki/"+a.slug,title:a.title,description:a.description,locale:"pl_PL",siteName:SITE_NAME,images:[{url:imageAttributes(a.coverImage,"article").src,width:1200,height:800,alt:a.coverAlt}]} } : { title: "Nie znaleziono poradnika", robots:{index:false,follow:false} };
}
export default async function ArticlePage({ params }: Props) {
  const article = await findArticle((await params).slug);
  if (!article) notFound();
  const presentation = catalog.find(entry => entry.slug === article.slug);
  const related = (await allArticles()).filter(entry => entry.slug !== article.slug && entry.category === article.category).slice(0, 2);
  const headings = parseMarkdown(article.bodyMarkdown).filter(b => b.type === "heading" && b.level === 2);
  const structuredData={"@context":"https://schema.org","@type":"Article",headline:article.title,description:article.description,inLanguage:"pl-PL",mainEntityOfPage:SITE_URL+"/poradniki/"+article.slug,image:[SITE_URL+imageAttributes(article.coverImage,"article").src],datePublished:"2026-11-01",author:{"@type":"Organization",name:SITE_NAME,url:SITE_URL+"/o-poradniku"},publisher:{"@type":"Organization",name:SITE_NAME,url:SITE_URL}};
  return <main id="main" className="article-shell container"><script type="application/ld+json" dangerouslySetInnerHTML={{__html:JSON.stringify(structuredData).replaceAll("<",String.fromCharCode(92)+"u003c")}} /><a href="/#poradniki" className="back-link"><ArrowLeft size={16} />Wszystkie poradniki</a><header className="article-header"><p className="eyebrow">Malowanie / Drobne naprawy</p><h1>{article.title}</h1><div className="article-meta"><span><Clock3 size={15} />{article.readingMinutes} min czytania</span><span>Źródła sprawdzone: {polishDate(article.checkedDate)}</span></div><p className="review-note">Opracowanie z pomocą AI na podstawie dokumentacji producentów. Wersja po redakcji, przed niezależną recenzją techniczną.</p><ReaderTools /></header><div className="article-layout"><div className="article-content"><Markdown source={article.bodyMarkdown} />{presentation && <Checklist key={article.slug} items={presentation.checklist} storageKey={presentation.checklistStorageKey} />}{related.length > 0 && <nav className="related-guides" aria-label="Powiązane poradniki"><p className="eyebrow">Powiązany problem</p>{related.map(entry => <a className="text-link" key={entry.slug} href={`/poradniki/${entry.slug}`}>{entry.title}<ArrowUpRight size={18} /></a>)}</nav>}<div className="article-end"><BookOpen size={24} /><div><h3>Warto wiedzieć, skąd pochodzi rada.</h3><p>Odnośniki przy tekście prowadzą do dokumentacji i porad producentów.</p><a href="/o-poradniku" className="text-link">Jak tworzymy treści <ArrowUpRight size={16} /></a></div></div></div><aside className="article-aside"><nav aria-label="Spis treści" className="toc"><p className="eyebrow">W tym poradniku</p><ol>{headings.map(b => b.type === "heading" && <li key={b.id}><a href={`#${b.id}`}>{b.text}</a></li>)}</ol><div className="toc-note"><span>Najpierw rozpoznanie.</span><p>Wygląd uszkodzenia to wskazówka, nie gotowa diagnoza.</p></div></nav></aside></div></main>;
}
