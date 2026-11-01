const cases = [
  { key: "a", title: "Cienki płatek farby", detail: "Sprawdź, czy niższa warstwa i brzegi dobrze się trzymają.", alt: "Przekrój: odrywa się cienka warstwa farby, a niższe warstwy pozostają na miejscu.", anchor: "a-odszedl-cienki-platek-farby" },
  { key: "b", title: "Kilka warstw", detail: "Sprawdź, czy odspajanie wychodzi poza ślad po taśmie.", alt: "Przekrój: z taśmą unoszą się dwie powłoki, a podłoże pozostaje na miejscu.", anchor: "b-oderwalo-sie-kilka-warstw" },
  { key: "c", title: "Okruchy podłoża", detail: "Zacznij od oceny podłoża. Samo podmalowanie nie wystarczy.", alt: "Przekrój: razem z powłokami odrywa się fragment podłoża i pozostaje zagłębienie.", anchor: "c-oderwal-sie-fragment-podloza" },
];

export function DamageGuide() {
  return <figure className="damage-guide" aria-label="Trzy poglądowe przekroje uszkodzenia">
    <div className="damage-legend" aria-label="Oznaczenia warstw">
      <span><i className="paint" aria-hidden="true" />farba</span>
      <span><i className="coating" aria-hidden="true" />starsza powłoka</span>
      <span><i className="substrate" aria-hidden="true" />podłoże</span>
      <span><i className="tape" aria-hidden="true" />taśma</span>
    </div>
    <div className="damage-grid">
      {cases.map(item => <div className="damage-card" key={item.key}>
        <span className="damage-letter" aria-hidden="true">{item.key.toUpperCase()}</span>
        <h3>{item.title}</h3>
        <img src={`/images/damage-${item.key}.svg`} alt={item.alt} width="460" height="275" loading="lazy" />
        <p>{item.detail}</p>
        <a href={`#${item.anchor}`}>Co dalej? <span aria-hidden="true">↓</span></a>
      </div>)}
    </div>
    <a className="damage-original" href="/images/damage-layers.png" target="_blank" rel="noopener noreferrer">Otwórz pełny schemat w nowej karcie ↗</a>
  </figure>;
}
