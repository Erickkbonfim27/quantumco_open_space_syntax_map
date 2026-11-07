/**
 * Imóveis à venda no mapa (prova de conceito, docs/adr/0003): pino de casa ou de prédio e a
 * janela com foto, dados, valores e o link do anúncio. Os dados vêm de
 * `/cities/{ibge}/listings`, que só responde com login e com a flag `listings_glue_api` ligada.
 */
import type { LayerSpecification, Map as MapLibreMap } from "maplibre-gl";
import "./listings.css";

export const LISTINGS = "imoveis";
const ICON_HOUSE = "qc-imovel-casa";
const ICON_BUILDING = "qc-imovel-predio";

/** Tipos que viram pino de prédio; o resto (casa, terreno, comercial…) vira pino de casa. */
export const BUILDING_TYPES = [
  "APARTMENT",
  "PENTHOUSE",
  "FLAT",
  "KITNET",
  "STUDIO",
  "LOFT",
  "DUPLEX",
  "TRIPLEX",
  "RESIDENTIAL_BUILDING",
  "COMMERCIAL_BUILDING",
];

export const listingIcon = (propertyType: unknown) =>
  BUILDING_TYPES.includes(String(propertyType)) ? ICON_BUILDING : ICON_HOUSE;

const TYPE_LABEL: Record<string, string> = {
  APARTMENT: "Apartamento",
  PENTHOUSE: "Cobertura",
  FLAT: "Flat",
  KITNET: "Kitnet",
  STUDIO: "Studio",
  LOFT: "Loft",
  DUPLEX: "Duplex",
  TRIPLEX: "Triplex",
  HOME: "Casa",
  CONDOMINIUM: "Casa de condomínio",
  TWO_STORY_HOUSE: "Sobrado",
  VILLAGE_HOUSE: "Casa de vila",
  RESIDENTIAL_ALLOTMENT_LAND: "Terreno",
  ALLOTMENT_LAND: "Terreno",
  COMMERCIAL_ALLOTMENT_LAND: "Terreno comercial",
  FARM: "Chácara ou sítio",
  OFFICE: "Sala comercial",
  BUSINESS: "Ponto comercial",
  COMMERCIAL_PROPERTY: "Ponto comercial",
  COMMERCIAL_BUILDING: "Prédio comercial",
  RESIDENTIAL_BUILDING: "Prédio residencial",
  SHED_DEPOSIT_WAREHOUSE: "Galpão",
  PARKING_SPACE: "Vaga de garagem",
};

export const typeLabel = (propertyType: unknown) => {
  const code = String(propertyType ?? "");
  if (TYPE_LABEL[code]) return TYPE_LABEL[code];
  if (!code) return "Imóvel";
  const words = code.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Camada de pinos: ícone pelo tipo, sempre visível (os pinos não se escondem uns aos outros). */
export const listingsLayer = (): LayerSpecification => ({
  id: LISTINGS,
  type: "symbol",
  source: LISTINGS,
  layout: {
    visibility: "none",
    "icon-image": ["match", ["get", "property_type"], BUILDING_TYPES, ICON_BUILDING, ICON_HOUSE],
    "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.55, 14, 0.8, 17, 1],
    "icon-allow-overlap": true,
    "icon-ignore-placement": true,
  },
});

export type ListingTone = "light" | "dark";

/**
 * Pino no padrão do design system: vidro do mapa (o mesmo do rótulo do endereço), borda fina na
 * cor da tinta e o ícone de linha da Plataforma (grade de 24, traço arredondado). Neutro de
 * propósito: camadas que não são sintáticas não usam cor (methodology/v1/symbology.yaml).
 */
const PIN_TONE: Record<ListingTone, { glass: string; border: string; ink: string; shadow: string }> = {
  dark: { glass: "rgba(12,15,16,0.94)", border: "rgba(244,246,245,0.32)", ink: "#F4F6F5", shadow: "rgba(0,0,0,0.45)" },
  light: { glass: "rgba(255,255,255,0.96)", border: "rgba(15,18,19,0.24)", ink: "#0F1213", shadow: "rgba(0,0,0,0.22)" },
};

/** Ícones de linha na grade de 24, como os do trilho de ferramentas. */
const GLYPH: Record<"casa" | "predio", string[]> = {
  casa: ["M3.5 10.5 12 3.5l8.5 7", "M5.5 9v11.5h13V9", "M10 20.5V15h4v5.5"],
  predio: [
    "M6.5 20.5v-16a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16",
    "M3.5 20.5h17",
    "M9.75 7.5h.01M14.25 7.5h.01M9.75 11h.01M14.25 11h.01M9.75 14.5h.01M14.25 14.5h.01",
    "M11 20.5v-3h2v3",
  ],
};

const PIN_PX = 32; // tamanho do pino (px de tela); o desenho é feito em 2x
const GLYPH_PX = 16;

function drawPin(glyph: "casa" | "predio", tone: ListingTone): ImageData | null {
  const ratio = 2;
  const canvas = document.createElement("canvas");
  canvas.width = PIN_PX * ratio;
  canvas.height = PIN_PX * ratio;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const colors = PIN_TONE[tone];
  const center = PIN_PX / 2;
  ctx.scale(ratio, ratio);
  ctx.save();
  ctx.shadowColor = colors.shadow;
  ctx.shadowBlur = 4;
  ctx.shadowOffsetY = 1;
  ctx.beginPath();
  ctx.arc(center, center, 12.5, 0, Math.PI * 2);
  ctx.fillStyle = colors.glass;
  ctx.fill();
  ctx.restore();
  ctx.lineWidth = 1;
  ctx.strokeStyle = colors.border;
  ctx.stroke();
  ctx.translate(center - GLYPH_PX / 2, center - GLYPH_PX / 2);
  ctx.scale(GLYPH_PX / 24, GLYPH_PX / 24);
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = 1.8;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const path of GLYPH[glyph]) ctx.stroke(new Path2D(path));
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

/** Cria os pinos ou redesenha no tom do mapa (tema claro ou escuro). */
export function ensureListingIcons(map: MapLibreMap, tone: ListingTone) {
  for (const [id, glyph] of [
    [ICON_HOUSE, "casa"],
    [ICON_BUILDING, "predio"],
  ] as const) {
    const image = drawPin(glyph, tone);
    if (!image) continue;
    if (map.hasImage(id)) map.updateImage(id, image);
    else map.addImage(id, image, { pixelRatio: 2 });
  }
}

const escapeHtml = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** Só links https dos domínios do portal; qualquer outro valor some da janela. */
export function safeUrl(value: unknown, hosts: string[]): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    const allowed = hosts.some((host) => url.hostname === host || url.hostname.endsWith(`.${host}`));
    return url.protocol === "https:" && allowed ? url.toString() : null;
  } catch {
    return null;
  }
}

const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null);
const brl = (value: number) =>
  value.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** A janela do pino: foto, tipo, preço, cômodos, taxas, endereço e o link do anúncio. */
export function listingPopupHtml(props: Record<string, unknown>): string {
  const photo = safeUrl(props.photo_url, ["vivareal.com", "vivareal.com.br", "zapimoveis.com.br"]);
  const link = safeUrl(props.url, ["vivareal.com.br", "zapimoveis.com.br"]);
  const portal = props.portal === "zap" ? "ZAP Imóveis" : "Viva Real";
  const bedrooms = num(props.bedrooms);
  const title = [typeLabel(props.property_type), bedrooms ? plural(bedrooms, "quarto", "quartos") : ""]
    .filter(Boolean)
    .join(" · ");
  const price = num(props.price_brl);
  const area = num(props.usable_area_m2) ?? num(props.total_area_m2);
  const bathrooms = num(props.bathrooms);
  const parking = num(props.parking_spaces);
  const suites = num(props.suites);
  const facts = [
    area ? `${area.toLocaleString("pt-BR")} m²` : "",
    suites ? plural(suites, "suíte", "suítes") : "",
    bathrooms ? plural(bathrooms, "banheiro", "banheiros") : "",
    parking ? plural(parking, "vaga", "vagas") : "",
  ].filter(Boolean);
  const condo = num(props.condo_fee_brl);
  const iptu = num(props.iptu_brl);
  const fees = [condo ? `Condomínio ${brl(condo)}/mês` : "", iptu ? `IPTU ${brl(iptu)}/ano` : ""].filter(Boolean);
  const perM2 = price && area ? `${brl(price / area)}/m²` : "";
  const place = [props.street, props.neighborhood].filter((v) => typeof v === "string" && v).join(", ");
  const seen = typeof props.seen === "string" ? props.seen.split("-").reverse().join("/") : "";
  const line = (text: string, cls = "") => (text ? `<span class="${cls}">${escapeHtml(text)}</span>` : "");
  return [
    `<div class="qc-listing">`,
    photo
      ? `<img class="qc-listing-photo" src="${escapeHtml(photo)}" alt="Foto do anúncio" loading="lazy" referrerpolicy="no-referrer">`
      : "",
    `<div class="qc-listing-body">`,
    `<strong class="qc-listing-title">${escapeHtml(title)}</strong>`,
    `<div class="qc-listing-price">${escapeHtml(price ? brl(price) : "Preço sob consulta")}`,
    perM2 ? ` <span class="qc-listing-m2">${escapeHtml(perM2)}</span>` : "",
    `</div>`,
    line(facts.join(" · ")),
    line(fees.join(" · ")),
    line(place),
    link
      ? `<a class="qc-listing-link" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Ver anúncio no ${portal} ↗</a>`
      : "",
    line(`${portal}${seen ? ` · visto em ${seen}` : ""} · prova de conceito`, "qc-listing-source"),
    `</div></div>`,
  ].join("");
}
