const steps = [
  { key: "stop", number: "01", title: "Przerwij przejazdy", detail: "Odłóż wałek i zanotuj, w którym momencie pojawiło się uszkodzenie.", alt: "Schemat wałka obok symbolu pauzy.", anchor: "zatrzymaj-prace-i-zachowaj-informacje" },
  { key: "inspect", number: "02", title: "Obejrzyj warstwy", detail: "Sprawdź odpadły fragment i odsłonięte podłoże. Wygląd nie przesądza o przyczynie.", alt: "Schemat lupy nad umownym przekrojem trzech warstw.", anchor: "sprawdz-co-naprawde-sie-odrywa" },
  { key: "prepare", number: "03", title: "Przygotuj i sprawdź", detail: "Napraw podłoże, zachowaj wymagane przerwy i oceń próbne wymalowanie po wyschnięciu.", alt: "Schemat karty z listą kontrolną i zegara bez wskazania czasu.", anchor: "przygotuj-podloze-przed-ponownym-malowaniem" },
];

export function RollerGuide() {
  return <figure className="damage-guide roller-guide" aria-label="Kolejność działań po oderwaniu farby wałkiem">
    <div className="damage-grid">{steps.map(step => <div className="damage-card" key={step.key}>
      <span className="damage-letter">{step.number}</span>
      <h3>{step.title}</h3>
      <img src={`/images/roller-${step.key}.svg`} alt={step.alt} width="460" height="275" loading="lazy" />
      <p>{step.detail}</p>
      <a href={`#${step.anchor}`}>Przejdź do wskazówek <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
