/** Parse a comma-separated competitor field. Max 2 competitors per analysis. */
export function parseCompetitors(raw: string): string[] {
  return raw
    .split(',')
    .map((c) => c.trim())
    .filter((c) => c.length > 0)
    .slice(0, 2);
}
