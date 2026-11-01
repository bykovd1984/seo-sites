const steps = [
  { key: "card", number: "01", title: "Odczytaj kartę", detail: "Znajdź dokładny produkt, etap schnięcia i warunki, dla których podano czas.", alt: "Schemat karty produktu z zaznaczeniem i zegarem.", anchor: "ile-schna-konkretne-farby-porownanie-kart" },
  { key: "recoat", number: "02", title: "Zaplanuj drugą warstwę", detail: "Zapisz koniec malowania i wymaganą przerwę. Uwzględnij stan ściany oraz warunki.", alt: "Schemat wałka obok zegara, bez wskazania uniwersalnego czasu.", anchor: "kiedy-nakladac-druga-warstwe" },
  { key: "wash", number: "03", title: "Sprawdź termin mycia", detail: "Suchość powierzchni nie potwierdza odporności na czyszczenie. Sprawdź osobne zalecenia.", alt: "Schemat miękkiej ściereczki i kalendarza bez daty.", anchor: "kiedy-mozna-umyc-pomalowana-sciane" },
];

export function DryingGuide() {
  return <figure className="damage-guide drying-guide" aria-label="Planowanie schnięcia farby">
    <div className="damage-grid">{steps.map(step => <div className="damage-card" key={step.key}>
      <span className="damage-letter">{step.number}</span>
      <h3>{step.title}</h3>
      <img src={`/images/drying-${step.key}.svg`} alt={step.alt} width="460" height="275" loading="lazy" />
      <p>{step.detail}</p>
      <a href={`#${step.anchor}`}>Przejdź do wskazówek <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
