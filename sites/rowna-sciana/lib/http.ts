export class PageNotFound extends Error {}
export function notFound(): never { throw new PageNotFound(); }
