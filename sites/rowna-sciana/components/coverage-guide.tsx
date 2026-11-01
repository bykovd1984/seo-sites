export function CoverageGuide() {
  return <figure className="damage-guide coverage-guide" aria-label="Krycie a wydajność farby">
    <div className="damage-grid">
      <div className="damage-card">
        <span className="damage-letter">KRYCIE</span>
        <h3>Czy widać stary kolor?</h3>
        <img src="/images/coverage-opacity.svg" alt="Schemat zasłaniania kontrastowego podłoża; porównanie pojęciowe, nie test farb." width="460" height="275" loading="lazy" />
        <p>Opisuje zasłonięcie barwy podłoża przez powłokę. Sam wynik w m²/l tego nie rozstrzyga.</p>
      </div>
      <div className="damage-card">
        <span className="damage-letter">WYDAJNOŚĆ</span>
        <h3>Ile powierzchni z litra?</h3>
        <img src="/images/coverage-area.svg" alt="Schemat powierzchni podzielonej na pola; liczba pól nie określa wydajności produktu." width="460" height="275" loading="lazy" />
        <p>Sprawdź, dla ilu warstw podano m²/l. Do ilości farby trzeba uwzględnić wszystkie planowane warstwy.</p>
      </div>
    </div>
  </figure>;
}
