import { ArrowUpRight } from "lucide-react";
export function Footer() {
  return <footer className="site-footer"><div className="footer-top"><div><a className="footer-brand" href="/">równaściana.</a><p>Małe naprawy zaczynają się<br />od dobrego rozpoznania.</p></div><div className="footer-links"><a href="/#poradniki">Poradniki <ArrowUpRight size={16} /></a><a href="/o-poradniku">O poradniku <ArrowUpRight size={16} /></a><a href="/prywatnosc">Prywatność <ArrowUpRight size={16} /></a></div></div><div className="footer-bottom"><span>© 2026 Równa ściana</span><span>Poradniki oparte na dokumentacji producentów</span><button type="button" className="privacy-settings-link" data-privacy-settings>Ustawienia prywatności</button><a href="#top">Do góry ↑</a></div></footer>;
}
