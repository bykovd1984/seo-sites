import { Search, ArrowRight } from "lucide-react";
import { searchArticles } from "@/lib/articles";
import { normalizeQuery } from "@/lib/content";
import { ArticleCard } from "@/components/article-card";
export const metadata = { title: "Znajdź poradnik", robots: {index:false,follow:true}, alternates:{canonical:"/szukaj"} };
export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string | string[] }> }) {
  const q = normalizeQuery((await searchParams).q);
  const articles = await searchArticles(q);
  return <main id="main" className="container search-page"><p className="eyebrow">Od czego zacząć?</p><h1>Znajdź swój problem.</h1><p className="page-intro">Wpisz objaw albo materiał, np. „taśma”, „farba” lub „gładź”.</p><form className="search-form" action="/szukaj" method="get"><Search size={22} aria-hidden="true" /><label className="sr-only" htmlFor="q">Szukaj poradnika</label><input id="q" name="q" type="search" maxLength={100} defaultValue={q} placeholder="Co wymaga naprawy?" /><button className="button" type="submit">Szukaj <ArrowRight size={18} /></button></form><p className="search-summary" role="status">{q ? `Wyniki dla „${q}”: ${articles.length}` : `Dostępne poradniki: ${articles.length}`}</p>{articles.length ? <div className="search-results">{articles.map(a => <ArticleCard key={a.slug} article={a} />)}</div> : <div className="empty-state"><span className="small-icon"><Search size={25} /></span><h2>Nie mamy jeszcze takiego poradnika.</h2><p>Spróbuj krótszej frazy, np. „farba” lub „taśma”. Nie musisz wpisywać polskich znaków.</p><a className="text-link" href="/szukaj">Zobacz wszystkie poradniki <ArrowRight size={17} /></a></div>}</main>;
}
