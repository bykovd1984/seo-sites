export type Block =
  | { type: "heading"; level: number; text: string; id: string }
  | { type: "paragraph"; text: string }
  | { type: "image"; alt: string; src: string }
  | { type: "table"; rows: string[][] }
  | { type: "list"; items: string[]; ordered?: boolean };
export function normalizeText(value: string): string {
  return value.toLowerCase().replace(/ł/g, "l").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
export function normalizeQuery(value: unknown): string {
  return typeof value === "string" ? value.trim().replace(/\s+/g, " ").slice(0, 100) : "";
}
export function escapeLike(value: string): string {
  return normalizeText(value).replace(/[\\%_]/g, "\\$&");
}
export function safeHref(value: string): string | null {
  if (/^\/(?!\/)/.test(value) || /^#[a-z0-9-]+$/.test(value)) return value;
  try { const url = new URL(value); return url.protocol === "https:" ? value : null; }
  catch { return null; }
}
export function parseMarkdown(markdown: string): Block[] {
  const blocks: Block[] = [];
  const used = new Map<string, number>();
  for (const raw of markdown.replace(/\r/g, "").trim().split(/\n\s*\n/)) {
    const text = raw.trim();
    const heading = /^(#{1,3}) (.+)$/.exec(text);
    if (heading) {
      if (heading[1].length === 1) continue;
      const base = normalizeText(heading[2]).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const count = (used.get(base) ?? 0) + 1; used.set(base, count);
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2], id: count === 1 ? base : `${base}-${count}` });
    } else if (/^!\[/.test(text)) {
      const img = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(text);
      if (img && /^\/images\/[a-z0-9-]+\.(png|webp|jpg|svg)$/.test(img[2])) blocks.push({ type: "image", alt: img[1], src: img[2] });
    } else if (text.startsWith("|")) {
      const rows = text.split("\n").filter(line => !/^\|[\s:|\-]+\|$/.test(line))
        .map(line => line.replace(/^\||\|$/g, "").split("|").map(cell => cell.trim()));
      blocks.push({ type: "table", rows });
    } else if (text.split("\n").every(line => /^[-*] /.test(line))) {
      blocks.push({ type: "list", items: text.split("\n").map(line => line.slice(2)) });
    } else if (text.split("\n").every(line => /^\d+\. /.test(line))) {
      blocks.push({ type: "list", ordered: true, items: text.split("\n").map(line => line.replace(/^\d+\. /, "")) });
    } else blocks.push({ type: "paragraph", text });
  }
  return blocks;
}

// Future guide links stay readable as text until their target is published.
export function publishedHref(value: string, availableSlugs: ReadonlySet<string>): string | null {
  const href = safeHref(value);
  if (!href) return null;
  const url = new URL(href, 'https://deviceclue.site');
  if (url.origin === 'https://deviceclue.site' && url.pathname.startsWith('/guides/')) {
    const slug = url.pathname.slice('/guides/'.length).replace(/\/$/, '');
    if (!availableSlugs.has(slug)) return null;
  }
  return href;
}
