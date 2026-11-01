import path from "node:path";
import { openArticleRepository } from "../db/repository";
export type { Article } from "../db/repository";
let repository: ReturnType<typeof openArticleRepository> | undefined;
function getRepository() {
  return repository ??= openArticleRepository(process.env.CONTENT_DB_PATH || path.join(process.cwd(), "data", "content.sqlite"));
}
export async function allArticles() { return getRepository().all(); }
export async function findArticle(slug: string) { return getRepository().find(slug); }
export async function searchArticles(query: string) { return getRepository().search(query); }
export function articleCount() { return getRepository().count(); }
export function polishDate(date: string) {
  return new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));
}
