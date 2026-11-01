import { Fragment } from 'react';
import { parseMarkdown, safeHref } from '@/lib/content';
function Inline({ text }: { text: string }) {
  return <>{text.split(/(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g).map((token,i)=>{
    const link=/^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
    if(link){const href=safeHref(link[2]);return href?<a key={i} href={href}>{link[1]}</a>:<Fragment key={i}>{link[1]}</Fragment>;}
    return token.startsWith('**')?<strong key={i}>{token.slice(2,-2)}</strong>:<Fragment key={i}>{token}</Fragment>;
  })}</>;
}
export function Markdown({ source }: { source: string }) { return <div className="prose">{parseMarkdown(source).map((b,i)=>{
  if(b.type==='heading')return b.level===2?<h2 key={i} id={b.id}>{b.text}</h2>:<h3 key={i} id={b.id}>{b.text}</h3>;
  if(b.type==='table')return <div className="table-scroll" tabIndex={0} role="region" aria-label="Comparison table" key={i}><table><thead><tr>{b.rows[0].map((c,j)=><th scope="col" key={j}><Inline text={c}/></th>)}</tr></thead><tbody>{b.rows.slice(1).map((r,j)=><tr key={j}>{r.map((c,k)=><td key={k}><Inline text={c}/></td>)}</tr>)}</tbody></table></div>;
  if(b.type==='list')return <ul key={i}>{b.items.map((text,j)=><li key={j}><Inline text={text}/></li>)}</ul>;
  return b.type==='paragraph'?<p key={i}><Inline text={b.text}/></p>:null;
})}</div>; }
