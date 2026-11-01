"use client";
import { useEffect, useState } from "react";
import { Check, Copy, Printer } from "lucide-react";
export function ReaderTools() {
  const [status, setStatus] = useState("");
  async function copy() { try { await navigator.clipboard.writeText(window.location.href.split("#")[0]); setStatus("Link skopiowany"); } catch { setStatus("Skopiuj adres z paska przeglądarki."); } }
  return <div className="reader-tools"><button onClick={() => window.print()}><Printer size={17} />Drukuj</button><button onClick={copy}><Copy size={17} />Kopiuj link</button><span role="status">{status}</span></div>;
}
export function Checklist({ items, storageKey }: { items: string[]; storageKey: string }) {
  const [checked, setChecked] = useState<boolean[]>(items.map(() => false));
  const [storageNotice, setStorageNotice] = useState("");
  useEffect(() => { setChecked(items.map(() => false)); try { const saved = JSON.parse(localStorage.getItem(storageKey) || "null"); if (Array.isArray(saved) && saved.length === items.length && saved.every(v => typeof v === "boolean")) setChecked(saved); } catch { setStorageNotice("Zaznaczenia są dostępne tylko do zamknięcia tej strony."); } }, [items, storageKey]);
  function toggle(index: number) { const next = checked.map((v, i) => i === index ? !v : v); setChecked(next); try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { setStorageNotice("Zaznaczenia są dostępne tylko do zamknięcia tej strony."); } }
  return <section className="checklist"><div className="checklist-title"><span className="small-icon"><Check size={20} /></span><div><p className="eyebrow">Przed naprawą</p><h2>Masz już plan?</h2></div><span className="checklist-count" aria-live="polite">{checked.filter(Boolean).length}/{items.length}</span></div>{items.map((item, i) => <label key={item}><input type="checkbox" checked={checked[i]} onChange={() => toggle(i)} /><span>{item}</span></label>)}<p className="small-note">{storageNotice || "Zaznaczenia zapisują się tylko w tej przeglądarce."}</p></section>;
}
