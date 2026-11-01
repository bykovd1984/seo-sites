const steps = [
  { key: "joint", number: "01", title: "Przygotuj połączenie", detail: "Sprawdź materiał, stan podłoża i wymiary szczeliny według karty produktu.", alt: "Schemat dwóch brzegów połączenia z zaznaczoną szczeliną, bez skali.", anchor: "przed-ostatnia-warstwa-ale-na-przygotowanym-podlozu" },
  { key: "shape", number: "02", title: "Nałóż i uformuj", detail: "Zachowaj czas obróbki. Taśmę przy spoinie zdejmij w terminie z instrukcji.", alt: "Schemat szpachelki nad spoiną, bez wskazania geometrii wykonawczej.", anchor: "kolejnosc-pracy-przy-listwie-lub-oscieznicy" },
  { key: "paint", number: "03", title: "Sprawdź termin", detail: "Maluj według instrukcji dokładnego produktu. Sam naskórek nie wyznacza terminu.", alt: "Schemat karty technicznej i pędzla.", anchor: "kiedy-mozna-malowac-akryl-porownanie-trzech-produktow" },
];

export function AcrylicGuide() {
  return <figure className="damage-guide acrylic-guide" aria-label="Kolejność przygotowania akrylu do malowania">
    <div className="damage-grid">{steps.map(step => <div className="damage-card" key={step.key}>
      <span className="damage-letter">{step.number}</span>
      <h3>{step.title}</h3>
      <img src={`/images/acrylic-${step.key}.svg`} alt={step.alt} width="460" height="275" loading="lazy" />
      <p>{step.detail}</p>
      <a href={`#${step.anchor}`}>Przejdź do wskazówek <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
