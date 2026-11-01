const cases = [
  { key: "coverage", letter: "A", title: "Nierówne krycie", detail: "Prześwituje podłoże lub poprzedni kolor. Sprawdź rozprowadzenie farby.", alt: "Umowny rysunek: warstwa farby nie pokrywa jednolicie koloru podłoża.", anchor: "a-widac-przeswity-lub-nierowno-pokryty-kolor" },
  { key: "sheen", letter: "B", title: "Różnice połysku", detail: "Pasy zmieniają wygląd pod kątem. Sprawdź chłonność i grubość powłoki.", alt: "Umowny rysunek: gładka powierzchnia ma pasy o różnym połysku.", anchor: "b-pasy-zmieniaja-wyglad-gdy-zmieniasz-miejsce" },
  { key: "ridges", letter: "C", title: "Wypukłe ślady", detail: "Widać grzbiet lub zgrubienie. Najpierw przygotuj powierzchnię.", alt: "Umowny przekrój: wypukły ślad farby wystaje nad powierzchnię sufitu.", anchor: "c-widac-wypukle-krawedzie-lub-chropowate-slady" },
];

export function CeilingGuide() {
  return <figure className="damage-guide ceiling-guide" aria-label="Trzy rodzaje śladów na suficie">
    <div className="damage-grid">{cases.map(item => <div className="damage-card" key={item.key}>
      <span className="damage-letter" aria-hidden="true">{item.letter}</span>
      <h3>{item.title}</h3>
      <img src={`/images/ceiling-${item.key}.svg`} alt={item.alt} width="460" height="275" loading="lazy" />
      <p>{item.detail}</p>
      <a href={`#${item.anchor}`}>Co sprawdzić? <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
