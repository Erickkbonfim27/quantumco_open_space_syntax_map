import { useEffect, useId, useRef, useState } from "react";

import { api } from "../../lib/api";

export interface AddressHit {
  label: string;
  street: string;
  number: number | null;
  locality: string | null;
  cep: string | null;
  lon: number;
  lat: number;
  units: number;
  exact: boolean;
}

export type SearchMode = "poligono" | "endereco";

/** Pin do mapa para um endereço escolhido. */
export const pinFor = (hit: AddressHit | null) =>
  hit
    ? {
        lngLat: [hit.lon, hit.lat] as [number, number],
        label: hit.number === null ? hit.street : `${hit.street}, ${hit.number}`,
      }
    : null;

interface SearchBoxProps {
  /** com polígonos (mapa do cenário) há o seletor; no mapa público só endereço */
  modes?: SearchMode[];
  mode: SearchMode;
  onMode?: (mode: SearchMode) => void;
  /** texto do filtro de polígonos */
  polygonQuery?: string;
  onPolygonQuery?: (text: string) => void;
  onAddress: (hit: AddressHit | null) => void;
  className?: string;
}

/**
 * Busca da barra do mapa: filtra polígonos ou procura um endereço de Brusque (CNEFE 2022).
 * No modo endereço, a lista abre enquanto digita; Enter escolhe o primeiro, setas navegam.
 */
export function SearchBox({ modes = ["endereco"], mode, onMode, polygonQuery = "", onPolygonQuery, onAddress, className = "" }: SearchBoxProps) {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<AddressHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mode !== "endereco") return;
    const q = text.trim();
    if (q.length < 3 || q === chosen) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      api<AddressHit[]>(`territory/addresses?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then((result) => {
          setHits(result);
          setActive(0);
          setOpen(true);
        })
        .catch(() => undefined)
        .finally(() => setLoading(false));
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [text, mode, chosen]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);

  const choose = (hit: AddressHit) => {
    setChosen(hit.label);
    setText(hit.label);
    setOpen(false);
    onAddress(hit);
  };

  const clear = () => {
    setText("");
    setChosen(null);
    setHits([]);
    onAddress(null);
  };

  const value = mode === "poligono" ? polygonQuery : text;
  const short = text.trim().length < 3;
  return (
    <div className={`searchbox ${className}`} ref={box}>
      {modes.length > 1 && (
        <select
          className="searchbox-mode"
          value={mode}
          aria-label="Buscar por"
          onChange={(e) => {
            onMode?.(e.target.value as SearchMode);
            setOpen(false);
          }}
        >
          <option value="poligono">Polígono</option>
          <option value="endereco">Endereço</option>
        </select>
      )}
      <input
        className="searchbox-input"
        value={value}
        role="combobox"
        aria-expanded={mode === "endereco" && open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label={mode === "poligono" ? "Buscar polígono" : "Buscar endereço em Brusque"}
        placeholder={mode === "poligono" ? "Buscar polígono" : "Rua, número… (ex.: Rua Azambuja 300)"}
        onFocus={() => hits.length && setOpen(true)}
        onChange={(e) => {
          if (mode === "poligono") onPolygonQuery?.(e.target.value);
          else {
            setText(e.target.value);
            setChosen(null);
          }
        }}
        onKeyDown={(e) => {
          if (mode !== "endereco") return;
          if (e.key === "ArrowDown") setActive((i) => Math.min(hits.length - 1, i + 1));
          if (e.key === "ArrowUp") setActive((i) => Math.max(0, i - 1));
          if (e.key === "Enter" && hits[active]) choose(hits[active]);
          if (e.key === "Escape") setOpen(false);
        }}
      />
      {value && (
        <button type="button" className="searchbox-clear" aria-label="Limpar busca" onClick={() => (mode === "poligono" ? onPolygonQuery?.("") : clear())}>
          ×
        </button>
      )}
      {mode === "endereco" && open && !short && (
        <ul className="searchbox-list" id={listId} role="listbox">
          {loading && hits.length === 0 && <li className="searchbox-empty">Buscando…</li>}
          {!loading && hits.length === 0 && <li className="searchbox-empty">Nenhum endereço encontrado em Brusque.</li>}
          {hits.map((hit, i) => (
            <li key={`${hit.label}-${i}`} role="option" aria-selected={i === active}>
              <button type="button" className={i === active ? "searchbox-hit searchbox-hit-on" : "searchbox-hit"} onMouseEnter={() => setActive(i)} onClick={() => choose(hit)}>
                <span>{hit.number === null ? hit.street : `${hit.street}, ${hit.number}`}</span>
                <span className="muted-2 small">
                  {[hit.locality, hit.cep && `${hit.cep.slice(0, 5)}-${hit.cep.slice(5)}`].filter(Boolean).join(" · ")}
                  {hit.number !== null && !hit.exact && " · número mais próximo"}
                </span>
              </button>
            </li>
          ))}
          <li className="searchbox-source mono">CNEFE 2022 · IBGE</li>
        </ul>
      )}
    </div>
  );
}
