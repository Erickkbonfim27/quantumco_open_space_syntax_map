const km = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const int = new Intl.NumberFormat("pt-BR");
const dateTime = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "America/Sao_Paulo",
});

export const formatKm = (meters: number): string => `${km.format(meters / 1000)} km`;

export const formatMeters = (meters: number): string =>
  meters >= 1000 ? formatKm(meters) : `${int.format(Math.round(meters))} m`;

export const formatInt = (value: number): string => int.format(value);

export const formatDateTime = (iso: string): string => dateTime.format(new Date(iso));

export const percent = (part: number, total: number): string =>
  total > 0 ? `${km.format((100 * part) / total)}%` : "–";
