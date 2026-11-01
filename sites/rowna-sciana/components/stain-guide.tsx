const steps = [
  { key: "inspect", number: "01", title: "Ustal stan ściany", detail: "Wyjaśnij przyczynę i stan podłoża. Czynnej wilgoci nie przykrywaj farbą.", alt: "Schemat lupy nad przebarwieniem ściany.", anchor: "plama-po-wodzie-czy-zaciek-samej-farby" },
  { key: "compare", number: "02", title: "Porównaj instrukcje", detail: "Sprawdź podłoże, rozcieńczanie i przerwy. Parametry dotyczą konkretnego produktu.", alt: "Schemat dokumentów z różnymi parametrami, bez rankingu.", anchor: "porownanie-trzech-produktow-z-dokumentacji" },
  { key: "trial", number: "03", title: "Oceń małą próbę", detail: "Sprawdź cały zestaw po wyschnięciu. Próba nie gwarantuje trwałości całej ściany.", alt: "Schemat niewielkiego pola próbnego i pędzla, bez wyniku badania.", anchor: "jak-przygotowac-mala-probe-przed-malowaniem-calosci" },
];

export function StainGuide() {
  return <figure className="damage-guide stain-guide" aria-label="Dobór farby izolującej plamy">
    <div className="damage-grid">{steps.map(step => <div className="damage-card" key={step.key}>
      <span className="damage-letter">{step.number}</span>
      <h3>{step.title}</h3>
      <img src={`/images/stain-${step.key}.svg`} alt={step.alt} width="460" height="275" loading="lazy" />
      <p>{step.detail}</p>
      <a href={`#${step.anchor}`}>Przejdź do wskazówek <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
