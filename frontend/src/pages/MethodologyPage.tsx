import "./content.css";

import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router";

import { Footer } from "../components/Footer";
import { PlatformBar } from "../components/PlatformBar";
import { SYNTAX_PALETTE } from "../features/map/syntaxPalette";
import { apiCached } from "../lib/api";
import type { AnalysisManifest, Manifest } from "../lib/types";

/**
 * Página "Metodologia": como o mapa é feito, em linguagem simples. Fonte da verdade:
 * docs/decisions.md e backend/methodology/v1/. O que ainda não existe aparece como "em breve".
 */

const SECTIONS: [string, string][] = [
  ["visao", "Visão geral"],
  ["area", "Área de estudo"],
  ["malha", "Rede viária"],
  ["representacao", "Representações"],
  ["medidas", "Medidas"],
  ["raios", "Raios"],
  ["motor", "Motor e verificação"],
  ["classes", "Classes e cores"],
  ["cenarios", "Cenários “e se…”"],
  ["camadas", "Camadas territoriais"],
  ["preregistro", "Pré-registro e sensibilidade"],
  ["limites", "Limitações e uso indevido"],
  ["licencas", "Licenças e como citar"],
];

const Soon = () => <span className="ct-soon">em breve</span>;
const Done = () => <span className="ct-done">em uso</span>;

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="ct-section" aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`}>{title}</h2>
      {children}
    </section>
  );
}

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });

export function MethodologyPage() {
  const [network, setNetwork] = useState<Manifest | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisManifest | null>(null);
  const [active, setActive] = useState(SECTIONS[0]?.[0] ?? "");

  useEffect(() => {
    let alive = true;
    apiCached<Manifest>("network/manifest")
      .then((v) => alive && setNetwork(v))
      .catch(() => undefined);
    apiCached<AnalysisManifest>("syntax/manifest")
      .then((v) => alive && setAnalysis(v))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  // índice: marca a seção que está na tela
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -65% 0px" },
    );
    for (const [id] of SECTIONS) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  const version = network?.methodology_version ?? analysis?.methodology_version;
  const today = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="platform content-page">
      <PlatformBar active="metodologia" />
      <main className="ct-main">
        <header className="ct-hero">
          <span className="label">METODOLOGIA{version ? ` · v${version}` : ""}</span>
          <h1>Como o mapa sintático é feito</h1>
          <p className="ct-lead">
            Da rede de ruas do OpenStreetMap às cores do mapa: cada escolha, o porquê dela e o que
            ainda falta. As regras ficam versionadas; mudar uma delas exige subir a versão.
          </p>
          {(network || analysis) && (
            <div className="ct-meta mono small">
              {network && <span>OSM de {day(network.osm_base_timestamp)}</span>}
              {analysis && (
                <span>
                  motor {analysis.engine} {analysis.engine_version}
                </span>
              )}
              {analysis?.preliminary && <span className="ct-soon">preliminar</span>}
            </div>
          )}
        </header>

        <div className="ct-doc">
          <nav className="ct-toc" aria-label="Nesta página">
            <span className="label">NESTA PÁGINA</span>
            <ol>
              {SECTIONS.map(([id, title]) => (
                <li key={id}>
                  <a href={`#${id}`} aria-current={active === id ? "true" : undefined} className={active === id ? "ct-toc-on" : undefined}>
                    {title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          <article className="ct-article">
            <Section id="visao" title="Visão geral">
              <p>
                O quantumco é um mapa sintático aberto e gratuito de Brusque-SC. A sintaxe espacial lê a
                cidade pela forma da sua rede de ruas: quais trechos são fáceis de alcançar e por quais
                passa mais gente atravessando. É feito para arquitetura e urbanismo, construtoras e
                incorporadoras, pesquisa e poder público.
              </p>
              <p>
                O rigor vem antes da velocidade: fontes datadas, regras escritas antes do cálculo e
                limites pré-registrados. Enquanto o cálculo não for conferido contra o depthmapX (a
                referência da área), o mapa leva o selo <strong>preliminar</strong>.
              </p>
            </Section>

            <Section id="area" title="Área de estudo">
              <p>
                Brusque é escolhida pelo <strong>código IBGE 4202909</strong> e pela{" "}
                <strong>relação OSM 296588</strong>, nunca pelo nome (existe uma Brusque na França).
              </p>
              <p>
                O cálculo usa uma <strong>faixa externa de 7 km</strong> em volta do município, para que
                as ruas da borda não pareçam isoladas só porque o mapa acabou ali (efeito de borda). Os
                resultados contam só dentro de Brusque; a faixa aparece esmaecida, em cinza.
              </p>
              <p>
                Todas as distâncias e áreas são medidas em <strong>SIRGAS 2000 / UTM 22S</strong>{" "}
                (EPSG:31982), em metros.
              </p>
            </Section>

            <Section id="malha" title="Rede viária">
              <p>
                A rede vem de um extrato datado do OpenStreetMap, baixado pela Overpass API. A data
                fica no manifesto de cada publicação.
              </p>
              <h3>O que entra</h3>
              <ul>
                <li>
                  Vias veiculares públicas (de motorway a residential, unclassified e road) e também{" "}
                  <code>pedestrian</code>, <code>living_street</code> e <code>steps</code>.
                </li>
                <li>
                  Ficam de fora: <code>service</code> privado (garagem, estacionamento, drive-thru,
                  acesso de emergência) e qualquer via com <code>access=private</code> ou{" "}
                  <code>access=no</code>.
                </li>
                <li>
                  Estradas rurais (<code>track</code>) só na faixa externa. Calçadas e trilhas
                  (footway, path, cycleway) ficam para uma variante de sensibilidade.
                </li>
              </ul>
              <h3>Limpeza</h3>
              <ul>
                <li>
                  Pontes e túneis só se conectam por nó compartilhado no OSM, nunca por cruzarem no
                  desenho. <Done />
                </li>
                <li>
                  Só o <strong>maior componente conectado</strong> é analisado; pedaços isolados
                  aparecem em cinza e são contados no manifesto. <Done />
                </li>
                <li>
                  Fusão de pistas duplas (sentidos opostos, mesmo nome, menos de 30 m, sem água entre
                  elas) e simplificação de rotatórias. <Soon />
                </li>
              </ul>
              <h3>Formato de cálculo</h3>
              <p>
                Cada trecho entre cruzamentos é simplificado por <strong>Douglas-Peucker com 2 m</strong>{" "}
                de tolerância e depois <strong>explodido em retas</strong>. Todo motor recebe exatamente
                essas retas. O valor de um trecho é a média dos valores das suas retas, ponderada pela
                extensão.
              </p>
            </Section>

            <Section id="representacao" title="Representações">
              <dl className="ct-dl ct-dl-wide">
                <dt>A · eixos de rua</dt>
                <dd>
                  A rede como está no OSM, trecho a trecho. É a representação do mapa hoje. <Done />
                </dd>
                <dt>B · Liu &amp; Jiang (2012)</dt>
                <dd>
                  Linhas naturais (ruas que seguem quase retas por vários cruzamentos), para comparar
                  com A e marcar onde o resultado “depende da representação”. <Soon />
                </dd>
                <dt>Mapa axial (Turner)</dt>
                <dd>Fora por enquanto: precisa do contorno das edificações, que Brusque não tem aberto.</dd>
              </dl>
            </Section>

            <Section id="medidas" title="Medidas">
              <p>
                As duas medidas seguem Hillier, Yang &amp; Turner (2012) e são calculadas por código
                próprio a partir dos valores brutos do motor, do mesmo jeito para qualquer motor. A
                profundidade é <strong>angular</strong>: virar 90° conta 1; seguir reto conta 0.
              </p>
              <div className="ct-formulas">
                <div>
                  <span className="label">INTEGRAÇÃO · NAIN</span>
                  <code className="ct-formula">NAIN = NC^1,2 ÷ TD</code>
                  <p className="small soft">“Facilidade de chegar”: quão perto, em mudanças de direção, o trecho está de todos os outros no raio.</p>
                </div>
                <div>
                  <span className="label">ESCOLHA · NACH</span>
                  <code className="ct-formula">NACH = log(CH + 1) ÷ log(TD + 3)</code>
                  <p className="small soft">“Potencial de passagem”: quantos caminhos mais simples entre pares de trechos passam por ele.</p>
                </div>
              </div>
              <p className="small muted">
                NC = número de trechos alcançados no raio (incluindo o próprio) · TD = profundidade angular
                total · CH = escolha angular bruta.
              </p>
            </Section>

            <Section id="raios" title="Raios">
              <p>
                Sempre métricos, pela rede: <strong>400 m</strong> (≈ 5 min a pé), <strong>800 m</strong>,{" "}
                <strong>1,2 km</strong>, <strong>2 km</strong> e <strong>n</strong> (a cidade inteira com a
                faixa externa). Raios curtos mostram centralidades de bairro; o raio n mostra a estrutura da
                cidade.
              </p>
            </Section>

            <Section id="motor" title="Motor e verificação">
              <p>
                O cálculo de produção usa o <strong>cityseer 5.8</strong> (versão fixada), com o grafo
                montado direto da nossa rede limpa, sem a limpeza automática dele.
              </p>
              <p>
                O juiz é o <strong>depthmapXcli v0.9.1</strong>, a referência da sintaxe espacial: a
                conferência compara contagem de nós (exata), profundidade e escolha (tolerância de 10⁻⁵) e o
                ranking (idêntico). Essa conferência automática ainda não roda <Soon />, por isso o mapa
                mostra o selo <strong>preliminar</strong>. Se o cityseer não passar, o plano B é o próprio
                depthmapX, com espera maior nos cenários.
              </p>
            </Section>

            <Section id="classes" title="Classes e cores">
              <div className="ct-ramp-wrap">
                <div className="ct-ramp" aria-hidden="true">
                  {SYNTAX_PALETTE.map((c) => (
                    <span key={c} style={{ background: c }} />
                  ))}
                </div>
                <div className="ct-ramp-labels muted small">
                  <span>classe 1 · mais segregado</span>
                  <span>classe 7 · mais integrado</span>
                </div>
              </div>
              <p>
                Os valores viram <strong>7 classes por percentil ponderado pela extensão</strong>,
                calculado só com os trechos de Brusque: cada cor cobre a mesma quantidade de quilômetros
                de rua. Assim dá para comparar raios e datas (o depthmapX usa faixas de largura igual
                entre o mínimo e o máximo, que mudam a cada mapa).
              </p>
              <p>
                A paleta segue o espectro dos mapas sintáticos de Londres, do azul (segregado) ao vermelho
                (integrado). Os mais integrados são desenhados mais grossos e por cima. Essas cores são
                exclusivas das medidas sintáticas: nenhuma outra camada usa a mesma escala.
              </p>
            </Section>

            <Section id="cenarios" title="Cenários “e se…”">
              <p>
                Num cenário você <strong>remove</strong>, <strong>interdita</strong>,{" "}
                <strong>cria</strong> ou <strong>redesenha</strong> vias. O pedido entra numa fila e é
                recalculado com o mesmo motor e a mesma metodologia do mapa publicado, nos raios que você
                escolher: <strong>Caminhada</strong> (400 e 800 m), <strong>Bairro</strong> (400 m a 2 km),{" "}
                <strong>Cidade</strong> (todos, inclusive n) ou uma escolha sua. A tela mostra a posição na
                fila e cada etapa.
              </p>
              <p>
                Sem o raio n, só a <strong>região que a edição pode alterar</strong> é recalculada, e o
                resultado é <strong>igual</strong> ao da cidade inteira, não uma aproximação. No raio r, a
                integração de um trecho só muda se a edição estiver a até r dele, e a escolha, a até 2r. Por
                isso o cálculo recalcula os trechos a até 2r da edição, usando como origem tudo o que está a
                até r deles (a rede inteira continua disponível para os caminhos), e o resto mantém o valor
                publicado. Com o raio n, toda a rede muda, e o cálculo é da cidade inteira (leva minutos).
              </p>
              <ul>
                <li>Interditar tem o mesmo efeito de remover na sintaxe (a via sai do grafo); muda só o rótulo.</li>
                <li>
                  Uma via nova se conecta pelas <strong>pontas</strong>, encaixadas no ponto mais próximo da
                  rede até <strong>30 m</strong>. Se a ponta cai no meio de um trecho, ele é dividido ali e
                  vira cruzamento. Cruzar uma rua no meio da via nova não conecta (como uma ponte).
                </li>
                <li>Redesenhar = remover o traçado antigo e criar o novo.</li>
                <li>
                  As classes do cenário usam os <strong>cortes do mapa publicado</strong>. Percentis do
                  próprio cenário reescalonariam tudo e esconderiam o efeito.
                </li>
                <li>
                  O resumo conta os quilômetros de rua de Brusque que subiram ou caíram de classe, nos raios n
                  e 800 m.
                </li>
              </ul>
              <p>
                O resultado descreve uma <strong>mudança na configuração da malha</strong>, nunca uma
                previsão de movimento ou de valor.
              </p>
            </Section>

            <Section id="camadas" title="Camadas territoriais">
              <p>
                Num polígono desenhado, o painel junta a sintaxe com população, renda, entorno,
                equipamentos e risco, a partir do IBGE (Censo e CNEFE 2022), do SGB e do CNES. Detalhes de
                cada fonte em <Link to="/dados">Dados</Link>.
              </p>
              <p>
                Dados por setor censitário entram por <strong>interpolação dasimétrica</strong>: cada setor
                contribui com a fração dos seus domicílios (endereços do CNEFE com coordenada) que cai
                dentro do polígono. Só quando o setor não tem domicílio georreferenciado usamos a fração de
                área. Isso evita dar população a um morro vazio só porque ele ocupa metade do setor.
              </p>
              <p>
                Pessoas em risco são estimadas pela parte da área de cada setor de risco que fica dentro do
                polígono. A suscetibilidade é a parte da área do polígono em cada classe.
              </p>
            </Section>

            <Section id="preregistro" title="Pré-registro e sensibilidade">
              <p>Os limites abaixo foram fixados antes de qualquer resultado e só mudam com nova versão da metodologia:</p>
              <dl className="ct-dl ct-dl-wide">
                <dt>Estabilidade</dt>
                <dd>Spearman ponderado ≥ 0,85 e Jaccard dos 10% mais integrados ≥ 0,70 entre variantes.</dd>
                <dt>Eixo principal</dt>
                <dd>Os 10% de cima, por extensão.</dd>
                <dt>Perfil 2×2</dt>
                <dd>Corte nos 20% de cima, ponderado por extensão.</dd>
                <dt>Equivalência de motores</dt>
                <dd>Contagem de nós exata; profundidade e escolha com tolerância relativa de 10⁻⁵; ranking idêntico.</dd>
              </dl>
              <p>
                Variantes de sensibilidade a rodar: com e sem fusão de pistas duplas, com e sem a faixa de
                borda, com e sem vias pedonais, limiares de 30°, 45° e 60° na representação B e tolerâncias
                de simplificação de 0, 2 e 5 m e reta por trecho. <Soon />
              </p>
            </Section>

            <Section id="limites" title="Limitações e uso indevido">
              <div className="ct-callout">
                Potencial de movimento estimado pela configuração da malha; <strong>não mede preço</strong>.
              </div>
              <ul>
                <li>O mapa não é avaliação de imóvel e não deve ser usado como tal. Não há nota única nem linguagem de preço.</li>
                <li>A rede depende do mapeamento do OSM; erros podem ser reportados pelo botão do trecho.</li>
                <li>A sintaxe mede a forma da rede, não o movimento observado. A validação com dados reais (empresas ativas por tipo de atividade) é uma fase futura. <Soon /></li>
                <li>Dados do Censo e do CNEFE são de 2022; os setores de risco, de 2018–2019; as cartas de suscetibilidade, de 2013.</li>
                <li>Valores em polígonos desenhados são estimativas por interpolação, não contagens.</li>
              </ul>
            </Section>

            <Section id="licencas" title="Licenças e como citar">
              <dl className="ct-dl ct-dl-wide">
                <dt>Código</dt>
                <dd>AGPL-3.0-or-later</dd>
                <dt>Dados derivados do OSM</dt>
                <dd>ODbL 1.0 · © OpenStreetMap contributors</dd>
                <dt>Relatório metodológico</dt>
                <dd>CC BY 4.0</dd>
                <dt>Camadas territoriais</dt>
                <dd>Fonte: IBGE, Censo Demográfico 2022 e CNEFE 2022 · SGB/CPRM · Ministério da Saúde (CNES)</dd>
              </dl>
              <span className="label">COMO CITAR</span>
              <blockquote className="ct-cite">
                BONFIM, Erick K. <em>quantumco: mapa sintático aberto de Brusque-SC</em>. Metodologia v
                {version ?? "1.0.0-dev"}. Dados © OpenStreetMap contributors (ODbL). Disponível em:
                https://quantumco.com.br. Acesso em: {today}.
              </blockquote>
            </Section>
          </article>
        </div>
      </main>
      <div className="ct-footer">
        <Footer />
      </div>
    </div>
  );
}
