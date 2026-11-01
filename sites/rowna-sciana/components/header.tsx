"use client";
import { useState } from "react";
import { Menu, Search, X, ArrowUpRight } from "lucide-react";
export function Brand() {
  return <a href="/" className="brand" aria-label="Równa ściana — strona główna"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>równa<span className="brand-light">ściana</span><b aria-hidden="true">.</b></span></a>;
}
export function Header() {
  const [open, setOpen] = useState(false);
  return <><a className="skip-link" href="#main">Przejdź do treści</a><header className="site-header"><div className="header-inner"><Brand /><nav aria-label="Menu główne" className={open ? "nav open" : "nav"} id="main-navigation"><a href="/#poradniki" onClick={() => setOpen(false)}>Poradniki</a><a href="/o-poradniku" onClick={() => setOpen(false)}>Jak tworzymy treści <ArrowUpRight size={14} /></a></nav><div className="header-actions"><a className="search-link" href="/szukaj" aria-label="Szukaj poradnika"><Search size={19} /><span>Szukaj</span></a><button className="menu-button" aria-label={open ? "Zamknij menu" : "Otwórz menu"} aria-expanded={open} aria-controls="main-navigation" onClick={() => setOpen(!open)}>{open ? <X size={22} /> : <Menu size={22} />}</button></div></div></header></>;
}
