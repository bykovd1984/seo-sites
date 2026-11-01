export function SkimGuide() {
  return <figure className="damage-guide skim-guide" aria-label="Przyczepność starej farby do podłoża">
    <div className="damage-legend">
      <span><i className="substrate" aria-hidden="true" />Podłoże mineralne</span>
      <span><i className="old-paint" aria-hidden="true" />Stara farba</span>
    </div>
    <div className="damage-grid">
      <div className="damage-card">
        <span className="damage-letter">SPRAWDŹ ZGODNOŚĆ</span>
        <h3>Farba trzyma się podłoża</h3>
        <img src="/images/skim-bonded.svg" alt="Przekrój: pomarańczowa warstwa farby przylega do szarego podłoża, bez szczeliny." width="460" height="275" loading="lazy" />
        <p>Możliwość pozostawienia zależy jeszcze od rodzaju farby i wymagań wybranej gładzi.</p>
      </div>
      <div className="damage-card">
        <span className="damage-letter">NAJPIERW PRZYGOTOWANIE</span>
        <h3>Farba odchodzi od ściany</h3>
        <img src="/images/skim-detached.svg" alt="Przekrój: stara farba odgina się od podłoża; strzałka wskazuje szczelinę pod farbą." width="460" height="275" loading="lazy" />
        <p>Usuń niezwiązane warstwy. Grunt na wierzchu nie rozwiązuje odspojenia pod farbą.</p>
      </div>
    </div>
  </figure>;
}
