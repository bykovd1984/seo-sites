import { Menu, Search, X, ArrowUpRight } from "lucide-react";
export function Brand() {
  return <a href="/" className="brand" aria-label="Równa ściana — strona główna"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>równa<span className="brand-light">ściana</span><b aria-hidden="true">.</b></span></a>;
}
export function Header() {
  return <><a className="skip-link" href="#main">Przejdź do treści</a><header className="site-header"><div className="header-inner"><Brand /><nav aria-label="Menu główne" className="nav" id="main-navigation"><a href="/#poradniki">Poradniki</a><a href="/o-poradniku">Jak tworzymy treści <ArrowUpRight size={14} /></a></nav><div className="header-actions"><a className="search-link" href="/szukaj" aria-label="Szukaj poradnika"><Search size={19} /><span>Szukaj</span></a><button type="button" className="menu-button" aria-label="Otwórz menu" aria-expanded={false} aria-controls="main-navigation" data-menu-toggle><span data-menu-closed><Menu size={22} /></span><span data-menu-open hidden><X size={22} /></span></button></div></div></header></>;
}
