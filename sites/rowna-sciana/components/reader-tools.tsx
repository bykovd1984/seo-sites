import { Check, Copy, Printer } from 'lucide-react';

export function ReaderTools() {
  return <div className="reader-tools" data-reader-tools><button type="button" data-reader-print><Printer size={17}/>Drukuj</button><button type="button" data-reader-copy><Copy size={17}/>Kopiuj link</button><span role="status"/></div>;
}
export function Checklist({ items, storageKey }: { items: string[]; storageKey: string }) {
  return <section className="checklist" data-checklist data-storage-key={storageKey}><div className="checklist-title"><span className="small-icon"><Check size={20}/></span><div><p className="eyebrow">Przed naprawą</p><h2>Masz już plan?</h2></div><span className="checklist-count" data-checklist-count aria-live="polite">0/{items.length}</span></div>{items.map(item => <label key={item}><input type="checkbox"/><span>{item}</span></label>)}<p className="small-note" data-checklist-notice>Zaznaczenia zapisują się tylko w tej przeglądarce.</p></section>;
}
