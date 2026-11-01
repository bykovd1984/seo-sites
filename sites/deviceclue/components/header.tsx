import { ArrowUpRight, Search } from 'lucide-react';
import { Brand } from './brand';
export function Header() { return <header className="site-header"><div className="container header-inner"><Brand/><nav aria-label="Main navigation"><a href="/#guides">The guides</a><a href="/#topics">Browse by topic</a><a href="/about">Our approach</a></nav><a className="header-search" href="/search"><Search size={16}/><span>Find an answer</span><ArrowUpRight size={15}/></a></div></header>; }
