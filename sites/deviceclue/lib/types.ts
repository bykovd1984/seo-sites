export type Source = { title: string; url: string; note: string };
export type Article = {
  slug: string; title: string; shortTitle: string; description: string;
  category: string; brand: string; type: string; diagram: string;
  answer: string; scope: string; tags: string[]; related: string[];
  sources: Source[]; checkedDate: string; readingMinutes: number;
  bodyMarkdown: string; takeaway: string; publishAt?: string;
};
export type ArticleSummary = Omit<Article, 'bodyMarkdown' | 'sources' | 'related'>;
