import type { NetworkEdit, RunStage } from "../../lib/platformTypes";
import type { LinkProperties } from "../../lib/types";

/** Ferramentas de edição da rede (cenário "e se…"). */
export type EditTool = "remove" | "close" | "add" | "reroute";

export const EDIT_LABEL: Record<EditTool, { verb: string; noun: string; hint: string }> = {
  remove: {
    verb: "Remover via",
    noun: "Via removida",
    hint: "Clique numa rua para tirá-la da rede. Clique de novo para desfazer.",
  },
  close: {
    verb: "Interditar via",
    noun: "Via interditada",
    hint: "Clique numa rua para interditá-la (obra, bloqueio). Na sintaxe tem o mesmo efeito de remover.",
  },
  add: {
    verb: "Nova via",
    noun: "Via nova",
    hint: "Clique para marcar os pontos. As pontas encaixam na rua mais próxima (ponto verde = conectada; laranja = solta). Termine com Enter, duplo clique ou clicando no último ponto. Backspace desfaz o último ponto; Esc cancela.",
  },
  reroute: {
    verb: "Redesenhar via",
    noun: "Via redesenhada",
    hint: "Clique na rua que vai mudar de traçado e depois desenhe o novo caminho, ligando as pontas às ruas vizinhas.",
  },
};

/** Só as pontas de uma via nova se conectam à rede (cruzar uma rua no meio é passar por cima). */
export const CONNECT_NOTE =
  "Só as pontas se conectam. Para criar um cruzamento no meio, termine a via na rua e comece outra dali.";

/** Liga/desliga remoção ou interdição de um trecho (uma alteração por via). */
export function toggleLinkEdit(edits: NetworkEdit[], type: "remove" | "close", link: LinkProperties): NetworkEdit[] {
  const existing = edits.find((e) => e.link_id === link.link_id);
  const rest = edits.filter((e) => e.link_id !== link.link_id);
  if (existing?.type === type) return rest; // mesmo tipo: desfaz
  return [...rest, { type, link_id: link.link_id }];
}

export function replaceReroute(edits: NetworkEdit[], linkId: string, coords: [number, number][]): NetworkEdit[] {
  return [...edits.filter((e) => e.link_id !== linkId), { type: "reroute", link_id: linkId, coords }];
}

/** Comprimento aproximado de uma linha em lon/lat (m), para a lista de edições. */
export function lineLength(coords: [number, number][] | undefined): number {
  if (!coords) return 0;
  let total = 0;
  for (let i = 1; i < coords.length; i++) {
    const [x0, y0] = coords[i - 1] as [number, number];
    const [x1, y1] = coords[i] as [number, number];
    const kx = 111_320 * Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
    total += Math.hypot((x1 - x0) * kx, (y1 - y0) * 110_574);
  }
  return total;
}

export const sameEdits = (a: NetworkEdit[] | undefined, b: NetworkEdit[] | undefined) =>
  JSON.stringify(a ?? []) === JSON.stringify(b ?? []);

export const STAGE_LABEL: Record<RunStage, string> = {
  queued: "Na fila",
  loading: "Carregando o mapa publicado",
  editing: "Aplicando as edições na rede",
  engine: "Análise angular da cidade inteira",
  comparing: "Comparando com o mapa atual",
  saving: "Gravando o resultado",
};
export const STAGES = Object.keys(STAGE_LABEL) as RunStage[];
