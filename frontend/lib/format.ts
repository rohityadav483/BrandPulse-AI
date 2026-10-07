export function pct(value: number): string {
  return `${value}%`;
}

export function score(value: number): string {
  return value.toFixed(2);
}

export function growth(value: number): string {
  return `${value.toFixed(1)}×`;
}

export function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${value}`;
}

export function label(value: string): string {
  return value.replace(/_/g, ' ');
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return 'Date unknown';
  return iso.slice(0, 10);
}
