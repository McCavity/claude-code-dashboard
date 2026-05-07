/** Compact number formatting used across panels.
 *  e.g. 12,345 → "12.3K", 1,500,000 → "1.5M". */
export function compact(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs < 1_000) return n.toString();
  const fmt = new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: digits,
  });
  return fmt.format(n);
}

/** Locale thousand-separator for tables. 12345 → "12,345". */
export function thou(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString();
}

/** Duration in milliseconds → human readable. */
export function dur(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3_600_000) return `${(ms / 60_000).toFixed(1)}m`;
  return `${(ms / 3_600_000).toFixed(1)}h`;
}

/** Relative time. "3 min ago" / "in 1h". */
export function rel(iso: string | null | undefined): string {
  if (!iso) return "—";
  let d: Date;
  try {
    d = new Date(iso);
  } catch {
    return iso;
  }
  if (Number.isNaN(d.getTime())) return iso;
  const delta = (d.getTime() - Date.now()) / 1000;
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const abs = Math.abs(delta);
  if (abs < 60) return fmt.format(Math.round(delta), "second");
  if (abs < 3600) return fmt.format(Math.round(delta / 60), "minute");
  if (abs < 86400) return fmt.format(Math.round(delta / 3600), "hour");
  if (abs < 86400 * 30) return fmt.format(Math.round(delta / 86400), "day");
  if (abs < 86400 * 365) return fmt.format(Math.round(delta / (86400 * 30)), "month");
  return fmt.format(Math.round(delta / (86400 * 365)), "year");
}

/** Cron expression → human-friendly string. Best effort, English only. */
export function cronToHuman(expr: string): string {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return expr;
  const [m, h, dom, mon, dow] = parts;
  const days = dow === "*" ? "" : dowList(dow);
  const time = formatTime(h, m);
  if (dom === "*" && mon === "*" && dow === "*") {
    if (m === "*" && h === "*") return "every minute";
    if (m.startsWith("*/")) return `every ${m.slice(2)} minutes`;
    return `every day at ${time}`;
  }
  if (dom === "*" && mon === "*") {
    return `${days} at ${time}`;
  }
  return expr;
}

const DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function dowList(dow: string): string {
  const ns = dow
    .split(",")
    .map((p) => parseInt(p.trim(), 10))
    .filter((n) => !Number.isNaN(n));
  if (ns.length === 7) return "every day";
  if (ns.length === 5 && ns.every((n) => n <= 4)) return "weekdays";
  if (ns.length === 2 && ns.includes(5) && ns.includes(6)) return "weekends";
  return ns.map((n) => DOW_NAMES[n] ?? "?").join(", ");
}

function formatTime(h: string, m: string): string {
  const hh = h.padStart(2, "0");
  const mm = m.padStart(2, "0");
  return `${hh}:${mm}`;
}
