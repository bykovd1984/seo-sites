const steps = [
  { key: "collect", number: "01", title: "Zbierz luźny pył", detail: "Dobierz sprzęt do materiału. Oczyść ścianę i otoczenie bez intensywnego zamiatania.", alt: "Schemat końcówki odsysającej drobiny obok ściany.", anchor: "kolejnosc-odpylania-po-szlifowaniu" },
  { key: "check", number: "02", title: "Sprawdź powierzchnię", detail: "Obejrzyj osad i stan masy. Proste przetarcie nie potwierdza nośności wszystkich warstw.", alt: "Schemat ściereczki i lupy, bez wyniku testu.", anchor: "jak-sprawdzic-efekt-i-kiedy-przejsc-do-gruntu" },
  { key: "prepare", number: "03", title: "Dobierz przygotowanie", detail: "Gruntuj dopiero oczyszczone, odpowiednio suche podłoże zgodnie z instrukcją systemu.", alt: "Schemat instrukcji i pędzla do gruntu.", anchor: "przed-gruntowaniem-sprawdz-cztery-rzeczy" },
];

export function DustGuide() {
  return <figure className="damage-guide dust-guide" aria-label="Etapy odpylania i kontroli podłoża">
    <div className="damage-grid">{steps.map(step => <div className="damage-card" key={step.key}>
      <span className="damage-letter">{step.number}</span>
      <h3>{step.title}</h3>
      <img src={`/images/dust-${step.key}.svg`} alt={step.alt} width="460" height="275" loading="lazy" />
      <p>{step.detail}</p>
      <a href={`#${step.anchor}`}>Przejdź do wskazówek <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
