import { Fragment } from "react";
import { parseMarkdown, safeHref } from "@/lib/content";
import { DamageGuide } from "./damage-guide";
import { CeilingGuide } from "./ceiling-guide";
import { WallGuide } from "./wall-guide";
import { CoverageGuide } from "./coverage-guide";
import { SkimGuide } from "./skim-guide";
import { RollerGuide } from "./roller-guide";
import { AcrylicGuide } from "./acrylic-guide";
import { DustGuide } from "./dust-guide";
import { StainGuide } from "./stain-guide";
import { DryingGuide } from "./drying-guide";
function Inline({ text }: { text: string }) {
  const tokens = text.split(/(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return <>{tokens.map((token, i) => {
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
    if (link) { const href = safeHref(link[2]); return href ? <a key={i} href={href} rel={href.startsWith("https:") ? "noopener noreferrer" : undefined}>{link[1]}</a> : <Fragment key={i}>{link[1]}</Fragment>; }
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={i}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("*") && token.endsWith("*")) return <em key={i}>{token.slice(1, -1)}</em>;
    return <Fragment key={i}>{token}</Fragment>;
  })}</>;
}
export function Markdown({ source }: { source: string }) {
  return <div className="prose">{parseMarkdown(source).map((block, i) => {
    if (block.type === "heading") return block.level === 2 ? <h2 id={block.id} key={i}>{block.text}</h2> : <h3 id={block.id} key={i}>{block.text}</h3>;
    if (block.type === "image" && block.src === "/images/damage-layers.png") return <DamageGuide key={i} />;
    if (block.type === "image" && block.src === "/images/ceiling-symptoms.svg") return <CeilingGuide key={i} />;
    if (block.type === "image" && block.src === "/images/wall-patterns.svg") return <WallGuide key={i} />;
    if (block.type === "image" && block.src === "/images/coverage-and-yield.svg") return <CoverageGuide key={i} />;
    if (block.type === "image" && block.src === "/images/skim-layer-decision.svg") return <SkimGuide key={i} />;
    if (block.type === "image" && block.src === "/images/roller-repair-sequence.svg") return <RollerGuide key={i} />;
    if (block.type === "image" && block.src === "/images/acrylic-painting-sequence.svg") return <AcrylicGuide key={i} />;
    if (block.type === "image" && block.src === "/images/wall-dust-sequence.svg") return <DustGuide key={i} />;
    if (block.type === "image" && block.src === "/images/stain-blocking-sequence.svg") return <StainGuide key={i} />;
    if (block.type === "image" && block.src === "/images/paint-drying-sequence.svg") return <DryingGuide key={i} />;
    if (block.type === "image") return <figure key={i}><img src={block.src} alt={block.alt} width="1536" height="1024" loading="lazy" /></figure>;
    if (block.type === "table") return <div className="table-scroll" role="region" aria-label="Tabela porównawcza" tabIndex={0} key={i}><table><thead><tr>{block.rows[0].map((cell, j) => <th key={j} scope="col"><Inline text={cell} /></th>)}</tr></thead><tbody>{block.rows.slice(1).map((row, j) => <tr key={j}>{row.map((cell, k) => <td key={k}><Inline text={cell} /></td>)}</tr>)}</tbody></table></div>;
    if (block.type === "list") return <ul key={i}>{block.items.map((text, j) => <li key={j}><Inline text={text} /></li>)}</ul>;
    return <p key={i} className={block.text.startsWith("*") && !block.text.startsWith("**") ? "caption" : undefined}><Inline text={block.text} /></p>;
  })}</div>;
}
