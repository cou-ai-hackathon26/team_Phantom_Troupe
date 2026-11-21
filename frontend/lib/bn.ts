const BN_DIGITS = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];

export function toBnDigits(value: number | string): string {
  return String(value).replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)]);
}

export function formatScore(value: number | null, digits = 3): string {
  return value === null ? "—" : toBnDigits(value.toFixed(digits));
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${toBnDigits(ms)} মি.সে.` : `${toBnDigits((ms / 1000).toFixed(1))} সেকেন্ড`;
}
