import { Fragment } from 'react';
import { parseMarkdown, publishedHref } from '@/lib/content';

function Inline({ text, availableSlugs }: { text: string; availableSlugs: ReadonlySet<string> }) {
  return <>{text.split(/(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g).map((token, i) => {
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
    if (link) {
      const href = publishedHref(link[2], availableSlugs);
      return href ? <a key={i} href={href}>{link[1]}</a> : <Fragment key={i}>{link[1]}</Fragment>;
    }
    if (token.startsWith('**')) return <strong key={i}>{token.slice(2, -2)}</strong>;
    if (token.startsWith('`')) return <code key={i}>{token.slice(1, -1)}</code>;
    return <Fragment key={i}>{token}</Fragment>;
  })}</>;
}

export function Markdown({ source, availableSlugs }: { source: string; availableSlugs: ReadonlySet<string> }) {
  const inline = (text: string) => <Inline text={text} availableSlugs={availableSlugs}/>;
  return <div className="prose">{parseMarkdown(source).map((b, i) => {
    if (b.type === 'heading') return b.level === 2 ? <h2 key={i} id={b.id}>{inline(b.text)}</h2> : <h3 key={i} id={b.id}>{inline(b.text)}</h3>;
    if (b.type === 'table') return <div className="table-scroll" tabIndex={0} role="region" aria-label="Comparison table" key={i}><table><thead><tr>{b.rows[0].map((c, j) => <th scope="col" key={j}>{inline(c)}</th>)}</tr></thead><tbody>{b.rows.slice(1).map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody></table></div>;
    if (b.type === 'list') {
      const items = b.items.map((text, j) => <li key={j}>{inline(text)}</li>);
      return b.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
    }
    return b.type === 'paragraph' ? <p key={i}>{inline(b.text)}</p> : null;
  })}</div>;
}
