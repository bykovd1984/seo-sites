const cases = [
  { key: "lap", letter: "A", title: "Łączenia wałka", detail: "Pasy między przejazdami. Sprawdź, czy krawędzie zdążyły podeschnąć.", alt: "Schemat ściany z ciemniejszymi pionowymi pasami na łączeniach farby.", anchor: "a-pasy-na-laczeniach-walka" },
  { key: "frame", letter: "B", title: "Ciemna obwódka", detail: "Inny kolor przy krawędziach. Porównaj pracę pędzla i wałka.", alt: "Schemat ściany z ciemniejszym pasem przy górnej i bocznych krawędziach.", anchor: "b-ciemniejsza-obwodka-przy-naroznikach" },
  { key: "patch", letter: "C", title: "Łata po poprawce", detail: "Ślad w miejscu domalowania. Sprawdź farbę, fakturę i przygotowanie łaty.", alt: "Schemat gładkiej ściany z jaśniejszą miejscową poprawką pośrodku.", anchor: "c-widoczna-lata-po-miejscowej-poprawce" },
];

export function WallGuide() {
  return <figure className="damage-guide wall-guide" aria-label="Trzy układy śladów na ścianie">
    <div className="damage-grid">{cases.map(item => <div className="damage-card" key={item.key}>
      <span className="damage-letter" aria-hidden="true">{item.letter}</span>
      <h3>{item.title}</h3>
      <img src={`/images/wall-${item.key}.svg`} alt={item.alt} width="460" height="275" loading="lazy" />
      <p>{item.detail}</p>
      <a href={`#${item.anchor}`}>Co sprawdzić? <span aria-hidden="true">↓</span></a>
    </div>)}</div>
  </figure>;
}
