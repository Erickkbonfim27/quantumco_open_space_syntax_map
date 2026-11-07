import "./content.css";

import { type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Footer } from "../components/Footer";
import { PlatformBar } from "../components/PlatformBar";
import { EDIT_COLORS, OVERLAY_COLOR } from "../features/map/MapView";
import { DELTA_COLORS, RADII, SYNTAX_PALETTE } from "../features/map/syntaxPalette";
import { apiCached } from "../lib/api";
import { cityApi, DEFAULT_CITY } from "../lib/city";
import type { Manifest } from "../lib/types";

/**
 * Página "Dados": de onde vem cada dado (Fontes) e o que cada camada do mapa mede (Indicadores).
 * Pública. Os números ao vivo (registros, datas) vêm da API e somem sem erro se ela falhar.
 */

type Tab = "fontes" | "indicadores";
const TABS: { key: Tab; label: string }[] = [
  { key: "fontes", label: "Fontes de dados" },
  { key: "indicadores", label: "Indicadores" },
];

interface LayerInfo {
  layer: string;
  source: string;
  source_url: string;
  license: string;
  rows: number;
  fetched_at: string;
}

const int = (v: number) => v.toLocaleString("pt-BR");
const day = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });

function useLiveData() {
  const [layers, setLayers] = useState<LayerInfo[] | null>(null);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  useEffect(() => {
    let alive = true;
    // as contagens desta página são de Brusque, a primeira cidade (as fontes valem para todas)
    apiCached<LayerInfo[]>(cityApi(DEFAULT_CITY, "territory/layers"))
      .then((v) => alive && setLayers(v))
      .catch(() => alive && setLayers([]));
    apiCached<Manifest>(cityApi(DEFAULT_CITY, "network/manifest"))
      .then((v) => alive && setManifest(v))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  return { layers, manifest };
}

export function DataPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("aba") === "indicadores" ? "indicadores" : "fontes";
  const refs = useRef<Record<Tab, HTMLButtonElement | null>>({ fontes: null, indicadores: null });
  const live = useLiveData();

  const select = (next: Tab, focus = false) => {
    setParams(next === "fontes" ? {} : { aba: next }, { replace: true });
    if (focus) refs.current[next]?.focus();
  };

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.key === tab);
    const last = TABS.length - 1;
    const to =
      event.key === "ArrowRight" ? (i === last ? 0 : i + 1)
      : event.key === "ArrowLeft" ? (i === 0 ? last : i - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (to === null) return;
    event.preventDefault();
    select(TABS[to]?.key ?? "fontes", true);
  };

  return (
    <div className="platform content-page">
      <PlatformBar active="dados" />
      <main className="ct-main">
        <header className="ct-hero">
          <span className="label">DADOS</span>
          <h1>Dados abertos de cada cidade</h1>
          <p className="ct-lead">
            Tudo o que aparece no mapa vem de fontes públicas e gratuitas, recortadas para cada cidade
            pelo código do IBGE. Aqui estão as fontes, o que cada uma traz e como a usamos, e cada
            indicador que você pode ligar nos mapas. Os números de exemplo são de Brusque, a primeira
            cidade do quantumco.
          </p>
        </header>

        <div className="ct-tabs" role="tablist" aria-label="Seções da página de dados" onKeyDown={onKey}>
          {TABS.map((t) => (
            <button
              key={t.key}
              ref={(el) => {
                refs.current[t.key] = el;
              }}
              id={`tab-${t.key}`}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              aria-controls={`painel-${t.key}`}
              tabIndex={tab === t.key ? 0 : -1}
              className={tab === t.key ? "ct-tab ct-tab-on" : "ct-tab"}
              onClick={() => select(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <section
          id={`painel-${tab}`}
          role="tabpanel"
          aria-labelledby={`tab-${tab}`}
          tabIndex={0}
          className="ct-panel"
        >
          {tab === "fontes" ? <Sources {...live} /> : <Indicators />}
        </section>
      </main>
      <div className="ct-footer">
        <Footer />
      </div>
    </div>
  );
}

/* ================================================================== fontes */

interface Source {
  id: string;
  name: string;
  publisher: string;
  what: string;
  links: { label: string; href: string }[];
  version: string;
  license: string;
  use: string[];
  cautions: string[];
  /** camadas de /territory/layers que vieram desta fonte (números ao vivo) */
  layers?: string[];
  where: string[];
}

const SOURCES: Source[] = [
  {
    id: "osm",
    name: "OpenStreetMap",
    publisher: "Colaboradores do OpenStreetMap",
    what: "Mapa colaborativo do mundo. É de onde vem a rede de ruas que a sintaxe espacial analisa.",
    links: [
      { label: "openstreetmap.org", href: "https://www.openstreetmap.org/relation/296588" },
      { label: "Overpass API", href: "https://overpass-api.de/" },
    ],
    version: "Extrato datado, baixado pela Overpass API",
    license: "ODbL 1.0 · © OpenStreetMap contributors",
    use: [
      "Seleção pelo código IBGE 4202909 e pela relação OSM 296588, com uma faixa de 7 km em volta (só para o cálculo).",
      "Entram as vias veiculares públicas e também pedestrian, living_street e steps. Ficam de fora service privado (garagem, estacionamento) e access=private/no. Estradas rurais (track) só na faixa externa.",
      "Calçadas e trilhas (footway, path, cycleway) ficam reservadas para uma variante de sensibilidade.",
    ],
    cautions: [
      "A rede é tão boa quanto o mapeamento. Se achar um erro, clique no trecho e use “Reportar erro na rede”: abre uma nota no OSM.",
      "Pontes e túneis só se conectam onde o OSM tem um nó compartilhado.",
    ],
    where: ["Mapa público", "Polígonos", "Cenários"],
  },
  {
    id: "censo",
    name: "Censo Demográfico 2022: setores censitários",
    publisher: "IBGE",
    what: "Malha dos 206 setores censitários de Brusque, com população, idade, alfabetização, domicílios, saneamento, renda do responsável e características do entorno dos domicílios.",
    links: [
      {
        label: "Agregados por setores (FTP do IBGE)",
        href: "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/",
      },
    ],
    version: "Censo 2022 · renda do responsável publicada em 2026-05-08",
    license: "Uso livre citando a fonte: IBGE, Censo Demográfico 2022",
    use: [
      "População e domicílios: V0001 (pessoas), V0003 (domicílios particulares) e V0007 (ocupados).",
      "Renda: V06001 (responsáveis), V06004 (média) e V06006 (mediana).",
      "Entorno dos domicílios: V05000 a V05033 (calçada, iluminação, árvores, rampa, ponto de ônibus, ciclovia…).",
      "Idade em 4 faixas: V01031 a V01041 (0–14, 15–29, 30–59 e 60+).",
      "Alfabetização: V00900 (15 anos ou mais que sabe ler e escrever) sobre V00900 + V00901.",
      "Saneamento sobre os domicílios permanentes (V00001): água da rede geral (V00111), esgoto na rede geral ou pluvial (V00309) e lixo coletado (V00397).",
      "No polígono, cada setor entra com a fração dos seus domicílios que cai dentro dele (interpolação dasimétrica com o CNEFE).",
    ],
    cautions: [
      "Em setores pequenos o IBGE omite a renda por sigilo; o painel avisa quantos setores ficaram sem renda.",
      "O entorno só foi pesquisado em setores urbanos (186 dos 206).",
      "Setores com algum valor sigiloso ficam de fora da taxa (numerador e base juntos), para não distorcer a conta.",
      "“Esgoto na rede geral ou pluvial” junta as duas opções do IBGE: a pluvial não leva a tratamento.",
      "Valores num polígono desenhado são estimativas, não contagens.",
    ],
    layers: ["setores"],
    where: ["Polígonos (N3 e N4)"],
  },
  {
    id: "cnefe",
    name: "CNEFE 2022",
    publisher: "IBGE · Cadastro Nacional de Endereços para Fins Estatísticos",
    what: "Todos os endereços visitados no Censo 2022, com coordenada e espécie (domicílio, ensino, saúde, religioso, outras finalidades, em construção).",
    links: [
      {
        label: "Arquivo de Brusque (FTP do IBGE)",
        href: "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/42_SC/4202909_BRUSQUE.zip",
      },
    ],
    version: "Censo 2022",
    license: "Uso livre citando a fonte: IBGE, Censo Demográfico 2022",
    use: [
      "Peso da interpolação dasimétrica: onde estão os domicílios dentro de cada setor.",
      "Escolas no mapa (espécie “ensino”) e contagem de usos no polígono.",
      "Só entram endereços com coordenada de boa precisão (nível ≤ 3).",
    ],
    cautions: ["É um retrato de 2022: “em construção” quer dizer em obra em 2022, não hoje."],
    layers: ["cnefe"],
    where: ["Mapa público (escolas)", "Polígonos (N3 e N5)"],
  },
  {
    id: "sgb",
    name: "Áreas de risco e suscetibilidade",
    publisher: "SGB · Serviço Geológico do Brasil (antigo CPRM) e IPT",
    what: "Setorização de áreas de risco geológico e cartas de suscetibilidade a inundação, movimento de massa, enxurrada e corrida de massa.",
    links: [{ label: "GeoServiços do SGB (WFS)", href: "https://geoservicos.sgb.gov.br/geoserver/ows" }],
    version: "Setores de risco 2018–2019 · cartas de suscetibilidade IPT/SGB 2013 (escala 1:25.000)",
    license: "Uso livre citando a fonte: Serviço Geológico do Brasil (SGB/CPRM)",
    use: [
      "No polígono: setores de risco que ele toca, a pior categoria e as pessoas em risco (proporcional à área do setor dentro do polígono).",
      "Parte da área do polígono em cada classe de suscetibilidade.",
      "No mapa: camadas de áreas de risco e de suscetibilidade a inundação.",
    ],
    cautions: [
      "Suscetibilidade é a propensão do terreno, não uma previsão de evento.",
      "Escala 1:25.000: serve para leitura de bairro, não de lote.",
    ],
    layers: ["risco", "suscet_inundacao", "suscet_movimento_de_massa", "suscet_enxurrada", "suscet_corrida_de_massa"],
    where: ["Mapa público", "Polígonos (N6)"],
  },
  {
    id: "cnes",
    name: "CNES",
    publisher: "Ministério da Saúde · Cadastro Nacional de Estabelecimentos de Saúde",
    what: "Estabelecimentos de saúde de Brusque com tipo de unidade, atendimento SUS e coordenada.",
    links: [
      {
        label: "API de dados abertos da Saúde",
        href: "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos?codigo_municipio=420290",
      },
    ],
    version: "Consulta à API na data da importação",
    license: "Dados abertos do Ministério da Saúde (CNES)",
    use: [
      "Pontos de saúde no mapa (os que atendem SUS em cor cheia).",
      "Contagem por tipo no polígono: atenção básica, hospital, urgência, clínicas, diagnóstico, CAPS…",
    ],
    cautions: [
      "Guardamos só nome, tipo, SUS e coordenada. Telefone e e-mail são descartados na importação.",
      "A coordenada é informada pelo próprio estabelecimento.",
    ],
    layers: ["cnes"],
    where: ["Mapa público", "Polígonos (N5)"],
  },
  {
    id: "overture",
    name: "Edificações (Overture Maps)",
    publisher: "Overture Maps Foundation · reúne OpenStreetMap, Microsoft ML Buildings e Google Open Buildings",
    what: "A pegada no chão de cada edificação de Brusque. O OSM tem pouco mais de 700 prédios na cidade; os outros vêm de detecção por satélite feita pela Microsoft e pelo Google, já sem duplicatas.",
    links: [
      { label: "Tema buildings (Overture)", href: "https://docs.overturemaps.org/guides/buildings/" },
      { label: "Atribuição e licenças", href: "https://docs.overturemaps.org/attribution/" },
    ],
    version: "Release 2026-10-21.0 (fixa: trocar de release é uma decisão registrada)",
    license:
      "ODbL 1.0 · © OpenStreetMap contributors, Overture Maps Foundation (Microsoft ML Buildings: ODbL; Google Open Buildings: CC BY 4.0)",
    use: [
      "No polígono: número de edificações (contadas pelo ponto interno da pegada, cada uma uma vez só), área no chão e taxa de ocupação.",
      "Taxa de ocupação = área no chão ÷ área do polígono. A área do polígono inclui ruas e áreas livres.",
      "No mapa: camada “Edificações” a partir do zoom 13, por baixo da malha sintática.",
    ],
    cautions: [
      "Cerca de 99% das pegadas vêm de detecção por satélite: a forma é aproximada e prédios colados podem virar um só.",
      "Altura e número de andares quase nunca são informados (8 prédios em Brusque); por isso não mostramos volume.",
      "Descartamos pegadas com menos de 10 m², quase sempre ruído do modelo.",
    ],
    layers: ["edificacoes"],
    where: ["Mapa público", "Polígonos (N7)"],
  },
  {
    id: "overture-lugares",
    name: "Comércio e serviços (Overture Maps)",
    publisher: "Overture Maps Foundation · lugares da Meta, Microsoft, Foursquare e AllThePlaces",
    what: "Estabelecimentos com nome e categoria: lojas, restaurantes, salões, oficinas, clínicas, escritórios, igrejas…",
    links: [{ label: "Tema places (Overture)", href: "https://docs.overturemaps.org/guides/places/" }],
    version: "Release 2026-10-21.0 (fixa)",
    license: "CDLA Permissive 2.0 (Meta, Microsoft) · Apache 2.0 (Foursquare) · CC0 (AllThePlaces)",
    use: [
      "Só lugares com confiança de pelo menos 0,5 (limite pré-registrado): 5.797 dos 8.727 do recorte.",
      "Agrupados pelo primeiro nível da categoria do Overture: comércio, serviços, alimentação, beleza, automotivo, saúde, cultura e religião, educação, esporte, comunidade, arte e hospedagem.",
      "No polígono: quantos lugares de cada grupo. No mapa: um ponto por lugar, com nome e categoria.",
    ],
    cautions: [
      "Vem de cadastros de empresas e redes sociais: pode haver lugar fechado ou mal localizado.",
      "Telefone, e-mail, site e redes sociais não são guardados.",
      "Não substitui o CNPJ: é a parte visível (com página na internet) da atividade da cidade.",
    ],
    layers: ["lugares"],
    where: ["Mapa público", "Polígonos (N5)"],
  },
  {
    id: "relevo",
    name: "Terrain Tiles",
    publisher: "AWS Open Data (Mapzen) · SRTM, USGS e outras",
    what: "Modelo de elevação mundial em blocos de imagem (codificação terrarium).",
    links: [{ label: "Registro na AWS", href: "https://registry.opendata.aws/terrain-tiles/" }],
    version: "Blocos até o zoom 13 (sombreamento) e 12 (relevo 3D)",
    license: "Dados abertos, com atribuição às fontes de origem",
    use: ["Sombreamento do relevo e relevo 3D no mapa."],
    cautions: [
      "Resolução de dezenas de metros: mostra morros e vales, não o detalhe da rua.",
      "O relevo 3D está em beta: o MapLibre desenha riscas verticais sobre as linhas da rede.",
    ],
    where: ["Mapa público", "Polígonos"],
  },
  {
    id: "fundos",
    name: "Fundos de mapa",
    publisher: "OpenFreeMap / OpenMapTiles · Esri World Imagery · OpenTopoMap",
    what: "Só a imagem de fundo: nomes de lugares, rios, ruas de referência, satélite e topografia. Nada disso entra no cálculo.",
    links: [
      { label: "OpenFreeMap", href: "https://openfreemap.org" },
      { label: "Esri World Imagery", href: "https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9" },
      { label: "OpenTopoMap", href: "https://opentopomap.org" },
    ],
    version: "Servidos ao vivo pelos provedores",
    license: "OpenMapTiles e © OpenStreetMap (ODbL) · imagens © Esri, Maxar, Earthstar Geographics · OpenTopoMap (CC-BY-SA)",
    use: ["Fundo escuro, claro, ruas, satélite ou topográfico, à escolha na lateral do mapa."],
    cautions: ["A data das imagens de satélite varia por região e não é informada no mapa."],
    where: ["Mapa público", "Polígonos"],
  },
];

const NEXT_SOURCES: [string, string][] = [
  ["Bairros do IBGE 2022", "27 bairros como polígonos prontos para escolher."],
  ["Empresas", "CNPJ da Receita, localizado pelo CNEFE (só agregados, sem MEI como ponto)."],
  ["Relevo fino", "Declividade e altitude a partir do MDT de 1 m do SIGSC (só estatísticas derivadas)."],
  ["Verde, calor e expansão urbana", "NDVI do Sentinel-2, temperatura de superfície do Landsat e a série do MapBiomas desde 1985."],
  ["A cidade na cheia", "Cenário que tira da rede os trechos em área inundável e recalcula a integração."],
  ["Pedido via LAI", "Lotes, zoneamento da LC 419/2024 e bairros oficiais da prefeitura, que não existem abertos."],
];

function Sources({ layers, manifest }: { layers: LayerInfo[] | null; manifest: Manifest | null }) {
  const report = manifest?.cleaning_report;
  return (
    <>
      {manifest && report && (
        <div className="ct-stats" aria-label="Rede viária publicada">
          <Stat value={day(manifest.osm_base_timestamp)} label="extrato do OSM" />
          <Stat value={int(report.links_kept)} label="trechos na rede (com a faixa de 7 km)" />
          <Stat value={`${int(Math.round(report.length_kept_m / 1000))} km`} label="de ruas na rede" />
          <Stat value={`v${manifest.methodology_version}`} label="metodologia" />
        </div>
      )}
      <div className="ct-grid">
        {SOURCES.map((s) => (
          <SourceCard key={s.id} source={s} layers={layers} />
        ))}
      </div>
      <div className="ct-card ct-card-soft">
        <span className="label">EM BREVE</span>
        <ul className="ct-next">
          {NEXT_SOURCES.map(([title, text]) => (
            <li key={title}>
              <strong>{title}.</strong> {text}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="ct-stat">
      <span className="ct-stat-value">{value}</span>
      <span className="muted small">{label}</span>
    </div>
  );
}

function SourceCard({ source: s, layers }: { source: Source; layers: LayerInfo[] | null }) {
  const imported = (layers ?? []).filter((l) => s.layers?.includes(l.layer));
  const rows = imported.reduce((sum, l) => sum + l.rows, 0);
  const latest = imported.map((l) => l.fetched_at).sort().at(-1);
  return (
    <article className="ct-card" aria-labelledby={`fonte-${s.id}`}>
      <div className="ct-card-head">
        <h2 id={`fonte-${s.id}`}>{s.name}</h2>
        <span className="muted small">{s.publisher}</span>
      </div>
      <p>{s.what}</p>
      <dl className="ct-dl">
        <dt>Versão</dt>
        <dd>{s.version}</dd>
        <dt>Licença</dt>
        <dd>{s.license}</dd>
        {latest && (
          <>
            <dt>Importado</dt>
            <dd className="mono">
              {day(latest)} · {int(rows)} registros
            </dd>
          </>
        )}
      </dl>
      <Block title="COMO USAMOS" items={s.use} />
      <Block title="CUIDADOS" items={s.cautions} />
      <div className="ct-card-foot">
        <span className="ct-chips">
          {s.where.map((w) => (
            <span key={w} className="ct-chip">
              {w}
            </span>
          ))}
        </span>
        <span className="ct-links">
          {s.links.map((l) => (
            <a key={l.href} href={l.href} target="_blank" rel="noreferrer">
              {l.label} ↗
            </a>
          ))}
        </span>
      </div>
    </article>
  );
}

function Block({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="ct-block">
      <span className="label">{title}</span>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/* ================================================================== indicadores */

type Where = "Mapa público" | "Polígonos" | "Cenários";

interface Indicator {
  id: string;
  tag?: string;
  name: string;
  what: string;
  read: string;
  unit: string;
  source: string;
  where: Where[];
  formula?: string;
  metrics?: string[];
  legend?: ReactNode;
}

interface Group {
  id: string;
  title: string;
  intro: string;
  items: Indicator[];
}

function Swatches({ items, line = false }: { items: [string, string][]; line?: boolean }) {
  return (
    <ul className="ct-legend">
      {items.map(([color, label]) => (
        <li key={label}>
          <span className={line ? "ct-swatch ct-swatch-line" : "ct-swatch"} style={{ background: color }} aria-hidden="true" />
          {label}
        </li>
      ))}
    </ul>
  );
}

function Ramp({ low, high }: { low: string; high: string }) {
  return (
    <div className="ct-ramp-wrap">
      <div className="ct-ramp" aria-hidden="true">
        {SYNTAX_PALETTE.map((c) => (
          <span key={c} style={{ background: c }} />
        ))}
      </div>
      <div className="ct-ramp-labels muted small">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  );
}

const WALK: Record<string, string> = {
  n: "a cidade inteira",
  "2000": "≈ 25 min a pé",
  "1200": "≈ 15 min a pé",
  "800": "≈ 10 min a pé",
  "400": "≈ 5 min a pé",
};

const GROUPS: Group[] = [
  {
    id: "sintaxe",
    title: "Sintaxe espacial",
    intro:
      "Medidas da configuração da malha: como cada trecho de rua se liga ao resto da cidade. Calculadas por trecho, em cinco raios, e pintadas em 7 classes.",
    items: [
      {
        id: "nain",
        tag: "NAIN",
        name: "Integração (facilidade de chegar)",
        what: "Quão fácil é chegar a este trecho a partir de todos os outros dentro do raio, contando as mudanças de direção do caminho (profundidade angular).",
        read: "Mais quente (vermelho) = mais integrado: um lugar central, por onde a cidade “passa perto”. Azul = segregado.",
        unit: "Adimensional. Normalizado para comparar raios e cidades.",
        formula: "NAIN = NC^1,2 ÷ TD",
        source: "Rede do OpenStreetMap + cálculo próprio (motor cityseer 5.8)",
        where: ["Mapa público", "Polígonos", "Cenários"],
        legend: <Ramp low="menos integrado" high="mais integrado" />,
      },
      {
        id: "nach",
        tag: "NACH",
        name: "Escolha (potencial de passagem)",
        what: "Quantos dos caminhos mais simples entre pares de trechos passam por este trecho, dentro do raio.",
        read: "Mais quente = mais escolhido como rota de passagem: tende a concentrar movimento de quem está atravessando.",
        unit: "Adimensional. Normalizado (Hillier, Yang & Turner, 2012).",
        formula: "NACH = log(CH + 1) ÷ log(TD + 3)",
        source: "Rede do OpenStreetMap + cálculo próprio (motor cityseer 5.8)",
        where: ["Mapa público", "Polígonos", "Cenários"],
        legend: <Ramp low="menos escolhido" high="mais escolhido" />,
      },
      {
        id: "raios",
        name: "Raios",
        what: "Até onde a medida “olha” a partir de cada trecho, sempre em distância métrica pela rede.",
        read: `${RADII.map((r) => `${r.label} (${WALK[r.key] ?? ""})`).join(" · ")}. Raios curtos mostram centralidades de bairro; o raio n mostra a estrutura da cidade.`,
        unit: "Metros pela rede (n = sem limite).",
        source: "Metodologia v1 (pré-registrada)",
        where: ["Mapa público", "Polígonos", "Cenários"],
      },
      {
        id: "classes",
        name: "Classes de cor",
        what: "Os valores viram 7 classes por percentil ponderado pela extensão, só com os trechos da cidade.",
        read: "Cada cor cobre a mesma quantidade de quilômetros de rua. Trechos mais integrados ficam mais grossos e por cima. A faixa externa de 7 km aparece em cinza: serve só ao cálculo.",
        unit: "Classe 1 (mais segregada) a 7 (mais integrada).",
        source: "Simbologia da metodologia v1",
        where: ["Mapa público", "Polígonos", "Cenários"],
        legend: <Swatches items={[["#4A5155", "faixa externa (sem classe)"]]} line />,
      },
    ],
  },
  {
    id: "poligonos",
    title: "Camadas do polígono (N1–N7)",
    intro:
      "Ao desenhar uma área num cenário, o painel empilha sete camadas sobre ela. Dados por setor censitário entram pela fração dos domicílios do setor que cai dentro do polígono (interpolação dasimétrica com o CNEFE); só sem domicílio georreferenciado usamos a fração de área.",
    items: [
      {
        id: "n1",
        tag: "N1",
        name: "Território",
        what: "A forma da área desenhada.",
        read: "Base para as densidades das outras camadas.",
        unit: "km², km e contagem.",
        metrics: ["Área", "Perímetro", "Vértices"],
        source: "Geometria do polígono, medida em SIRGAS 2000 / UTM 22S",
        where: ["Polígonos"],
      },
      {
        id: "n2",
        tag: "N2",
        name: "Rede viária",
        what: "Os trechos da cidade que cruzam a área, recortados por ela.",
        read: "A barra mostra quantos km de rua há em cada classe de cor; a média resume a área no raio escolhido.",
        unit: "Trechos, km, média de NAIN/NACH.",
        metrics: [
          "Trechos que cruzam o polígono",
          "Km de rua recortados pelo polígono",
          "Média de NAIN ou NACH ponderada pela extensão recortada, por raio",
          "Km por classe de cor",
        ],
        source: "Análise sintática publicada",
        where: ["Polígonos"],
      },
      {
        id: "n3",
        tag: "N3",
        name: "População e renda",
        what: "Quem mora na área, estimado a partir dos setores censitários.",
        read: "Densidade e renda média do responsável pelo domicílio. Não ocupados = vagos mais uso ocasional (veraneio etc.), na definição do IBGE.",
        unit: "Habitantes, hab/km², domicílios, R$ por mês.",
        metrics: [
          "Habitantes e hab/km²",
          "Domicílios ocupados e % não ocupados",
          "Renda média do responsável e a faixa entre os setores",
          "Setores envolvidos e quantos têm renda sigilosa",
          "Idade em 4 faixas (barra) e alfabetização das pessoas com 15 anos ou mais",
        ],
        source: "IBGE Censo 2022 + CNEFE 2022 (pesos)",
        where: ["Polígonos"],
      },
      {
        id: "n4",
        tag: "N4",
        name: "Entorno urbano",
        what: "Como são as faces de quadra onde ficam os domicílios.",
        read: "Percentual dos domicílios cuja face de quadra tem cada item.",
        unit: "% dos domicílios pesquisados.",
        metrics: [
          "Calçada, iluminação e arborização (em destaque)",
          "Rampa, ponto de ônibus, ciclovia e obstáculo na calçada",
          "Pavimentação, bueiro, árvores a cada 5 m e via com trânsito pesado (na exportação GeoJSON)",
          "Saneamento dos domicílios: água da rede, esgoto na rede geral ou pluvial e lixo coletado",
        ],
        source: "IBGE Censo 2022, entorno dos domicílios",
        where: ["Polígonos"],
      },
      {
        id: "n5",
        tag: "N5",
        name: "Equipamentos e uso",
        what: "O que existe na área além de moradia.",
        read: "Escolas, saúde e a parcela de endereços com outros usos (comércio, serviço, indústria…).",
        unit: "Contagens e %.",
        metrics: [
          "Escolas (endereços de ensino do CNEFE)",
          "Estabelecimentos de saúde e quantos atendem SUS",
          "% de endereços não residenciais",
          "Obras em andamento em 2022 e templos",
          "Lugares com nome (Overture) por grupo: comércio, serviços, alimentação…",
        ],
        source: "IBGE CNEFE 2022 + CNES + Overture places",
        where: ["Polígonos"],
      },
      {
        id: "n6",
        tag: "N6",
        name: "Risco",
        what: "Exposição da área a risco geológico e a inundação.",
        read: "Setores de risco tocados e a pior categoria; pessoas em risco estimadas pela área do setor dentro do polígono; parte da área em cada classe de suscetibilidade.",
        unit: "Setores, pessoas (estimativa), % da área.",
        metrics: [
          "Setores de risco e a pior categoria (baixo a muito alto)",
          "Pessoas e domicílios em risco (estimativa)",
          "% da área com suscetibilidade alta, média e baixa a inundação",
          "% da área com suscetibilidade alta a movimento de massa",
        ],
        source: "SGB 2018–2019 e cartas IPT/SGB 2013",
        where: ["Polígonos"],
      },
      {
        id: "n7",
        tag: "N7",
        name: "Forma construída",
        what: "As edificações dentro da área, pela pegada no chão.",
        read: "Taxa de ocupação é a área no chão dividida pela área do polígono (ruas incluídas). A barra mostra de onde vem cada pegada: OSM ou detecção por satélite.",
        unit: "Contagem, % e m².",
        metrics: [
          "Edificações (cada uma contada uma vez, pelo ponto interno da pegada)",
          "Taxa de ocupação",
          "Área no chão (recortada pelo polígono)",
          "Parte detectada por satélite (Google, Microsoft) e parte mapeada no OSM",
        ],
        source: "Overture Maps, release 2026-10-21.0",
        where: ["Polígonos"],
      },
    ],
  },
  {
    id: "abertas",
    title: "Camadas abertas no mapa",
    intro: "Liga e desliga na lateral do mapa. Cores fora da escala sintática, para não confundir com integração e escolha. Clique num ponto ou área para ver os detalhes.",
    items: [
      {
        id: "risco",
        name: "Áreas de risco",
        what: "Setores de risco geológico mapeados pelo SGB.",
        read: "Mais opaco = risco muito alto.",
        unit: "Áreas (polígonos).",
        source: "SGB 2018–2019",
        where: ["Mapa público", "Polígonos"],
        legend: <Swatches items={[[OVERLAY_COLOR.risco, "setor de risco"]]} />,
      },
      {
        id: "inundacao",
        name: "Inundação (suscetibilidade)",
        what: "Terrenos propensos a inundar.",
        read: "Mais forte = suscetibilidade alta.",
        unit: "Áreas (polígonos).",
        source: "Cartas IPT/SGB 2013",
        where: ["Mapa público", "Polígonos"],
        legend: <Swatches items={[[OVERLAY_COLOR.inundacao, "suscetível a inundação"]]} />,
      },
      {
        id: "saude",
        name: "Saúde",
        what: "Estabelecimentos de saúde.",
        read: "Cor cheia = atende SUS; esmaecido = não atende.",
        unit: "Pontos.",
        source: "CNES",
        where: ["Mapa público", "Polígonos"],
        legend: <Swatches items={[[OVERLAY_COLOR.saude, "estabelecimento de saúde"]]} />,
      },
      {
        id: "escolas",
        name: "Escolas",
        what: "Endereços de ensino.",
        read: "Um ponto por endereço.",
        unit: "Pontos.",
        source: "CNEFE 2022",
        where: ["Mapa público", "Polígonos"],
        legend: <Swatches items={[[OVERLAY_COLOR.escolas, "escola"]]} />,
      },
      {
        id: "lugares",
        name: "Comércio e serviços",
        what: "Estabelecimentos com nome: lojas, restaurantes, salões, oficinas, clínicas, escritórios…",
        read: "Um ponto por lugar. Clique para ver o nome e a categoria.",
        unit: "Pontos.",
        source: "Overture Maps (places)",
        where: ["Mapa público", "Polígonos"],
        legend: <Swatches items={[[OVERLAY_COLOR.lugares, "lugar com nome"]]} />,
      },
      {
        id: "predios",
        name: "Edificações",
        what: "A pegada no chão de cada prédio. Aparece a partir do zoom 13, por baixo da malha sintática.",
        read: "Clique num prédio para ver a área no chão, de onde veio (OSM ou satélite) e a confiança da detecção.",
        unit: "Áreas (polígonos).",
        source: "Overture Maps (OSM, Microsoft, Google)",
        where: ["Mapa público", "Polígonos"],
        legend: <Swatches items={[["rgba(var(--fg-rgb), 0.45)", "edificação"]]} />,
      },
      {
        id: "relevo",
        name: "Relevo",
        what: "Sombreamento das encostas e, em beta, o terreno em 3D (Ctrl + arrastar para inclinar).",
        read: "Ajuda a ler morros e o vale do Itajaí-Mirim junto da rede.",
        unit: "—",
        source: "Terrain Tiles (SRTM/USGS)",
        where: ["Mapa público", "Polígonos"],
      },
      {
        id: "base",
        name: "Malha, entorno e limite",
        what: "A própria rede sintática, a faixa externa de 7 km e o limite do município.",
        read: "Desligar a malha deixa ver só o fundo e as outras camadas.",
        unit: "—",
        source: "OpenStreetMap",
        where: ["Mapa público", "Polígonos"],
      },
    ],
  },
  {
    id: "cenarios",
    title: "Cenários “e se…”",
    intro:
      "Num cenário você edita a rede e recalcula os raios que escolher. Sem o raio n, só a região que a edição pode alterar é recalculada, com resultado igual ao da cidade inteira; com o n, a cidade inteira. O resultado é uma mudança na configuração da malha, nunca uma previsão.",
    items: [
      {
        id: "edicoes",
        name: "Edições da rede",
        what: "Remover uma via, interditá-la, criar uma via nova ou redesenhar o traçado de uma existente.",
        read: "Interditar tem o mesmo efeito de remover na sintaxe; muda só o rótulo. Uma via nova se conecta pelas pontas, encaixadas na rua mais próxima até 30 m; cruzar uma rua no meio não cria cruzamento.",
        unit: "—",
        source: "Desenho do usuário",
        where: ["Cenários"],
        legend: (
          <Swatches
            line
            items={[
              [EDIT_COLORS.remove, "via removida ou redesenhada"],
              [EDIT_COLORS.close, "via interditada"],
              [EDIT_COLORS.add, "via nova"],
            ]}
          />
        ),
      },
      {
        id: "diferenca",
        name: "Diferença de classe",
        what: "Quantas classes cada trecho ganhou ou perdeu em relação ao mapa atual.",
        read: "As classes do cenário usam os cortes do mapa publicado; assim ganhos e perdas aparecem. O resumo diz quantos km de rua da cidade subiram ou caíram de classe (raios n e 800 m).",
        unit: "Classes (−6 a +6) e km.",
        source: "Recálculo com o mesmo motor e a mesma metodologia",
        where: ["Cenários"],
        legend: (
          <Swatches
            line
            items={[
              [DELTA_COLORS.gainStrong, "ganhou 2+ classes"],
              [DELTA_COLORS.gain, "ganhou 1 classe"],
              [DELTA_COLORS.same, "sem mudança"],
              [DELTA_COLORS.loss, "perdeu 1 classe"],
              [DELTA_COLORS.lossStrong, "perdeu 2+ classes"],
              [DELTA_COLORS.removed, "trecho removido"],
              [DELTA_COLORS.added, "rua nova"],
            ]}
          />
        ),
      },
    ],
  },
];

function Indicators() {
  return (
    <>
      <nav className="ct-jump" aria-label="Grupos de indicadores">
        {GROUPS.map((g) => (
          <a key={g.id} href={`#grupo-${g.id}`}>
            {g.title}
          </a>
        ))}
      </nav>
      {GROUPS.map((g) => (
        <section key={g.id} id={`grupo-${g.id}`} className="ct-group" aria-labelledby={`titulo-${g.id}`}>
          <h2 id={`titulo-${g.id}`} className="ct-group-title">
            {g.title}
          </h2>
          <p className="ct-group-intro">{g.intro}</p>
          <div className="ct-grid">
            {g.items.map((item) => (
              <IndicatorCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      ))}
      <p className="muted small ct-note">
        Potencial de movimento estimado pela configuração da malha; não mede preço. Detalhes do cálculo na{" "}
        <Link to="/metodologia">metodologia</Link>.
      </p>
    </>
  );
}

function IndicatorCard({ item }: { item: Indicator }) {
  return (
    <article className="ct-card" aria-labelledby={`ind-${item.id}`}>
      <div className="ct-card-head">
        {item.tag && <span className="ct-tag mono">{item.tag}</span>}
        <h3 id={`ind-${item.id}`}>{item.name}</h3>
      </div>
      <p>{item.what}</p>
      {item.formula && <code className="ct-formula">{item.formula}</code>}
      {item.legend}
      {item.metrics && <Block title="O QUE MOSTRA" items={item.metrics} />}
      <dl className="ct-dl">
        <dt>Como ler</dt>
        <dd>{item.read}</dd>
        <dt>Unidade</dt>
        <dd>{item.unit}</dd>
        <dt>Fonte</dt>
        <dd>{item.source}</dd>
      </dl>
      <div className="ct-card-foot">
        <span className="ct-chips">
          {item.where.map((w) => (
            <span key={w} className="ct-chip">
              {w}
            </span>
          ))}
        </span>
      </div>
    </article>
  );
}
