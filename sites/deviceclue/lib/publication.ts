/** Keep stored dates canonical so SQLite's text comparison matches chronological order. */
export function validatePublishAt(value: unknown): void {
  if (value === undefined) return;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) {
    throw new Error('publishAt must be a canonical UTC timestamp with milliseconds');
  }
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new Error('publishAt must be a valid calendar date');
  }
}
