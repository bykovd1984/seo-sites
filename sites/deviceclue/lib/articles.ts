import path from 'node:path';
import { openRepository } from '@/db/repository';
import type { Article, ArticleSummary } from './types';
let repository: ReturnType<typeof openRepository> | undefined;
function getRepository() { return repository ??= openRepository(process.env.CONTENT_DB_PATH || path.join(process.cwd(), 'data/content.sqlite')); }
export const allArticles = () => getRepository().all();
export const findArticle = (slug: string) => getRepository().find(slug);
export const searchArticles = (query: unknown) => getRepository().search(query);
export const articleCount = () => getRepository().count();
export function summarize(article: Article): ArticleSummary { const { bodyMarkdown: _body, sources: _sources, related: _related, ...summary } = article; return summary; }
export function displayDate(date: string) { return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`)); }
