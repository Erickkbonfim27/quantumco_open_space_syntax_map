# quantumco — registro de decisões

Resultado da sessão de design de 2026-11-05. Cada linha remete à pergunta (Q) em que foi decidida.
Mudanças futuras entram como ADR em `docs/adr/` e atualizam este arquivo.

## Produto

| Tema | Decisão | Q |
|---|---|---|
| Propósito | Mapa sintático (sintaxe espacial) de Brusque-SC, aberto e gratuito. Público: arquitetura/urbanismo e construtoras/incorporadoras. Também peça de portfólio. **Rigor metodológico alto.** | Q1 |
| MVP | Serviço web completo: mapa (a) + relatório do local (b) + cenários "e se..." (c), mais download dos dados | Q8, Q12 |
| Cenários | Só no **modo técnico**, com login; recálculo da **cidade inteira**, incluindo o raio n. Apresentados como "mudança na configuração da malha", nunca como previsão | Q23, Q31 |
| Modo padrão | Representação A, "facilidade de chegar" (NAIN) e "potencial de passagem" (NACH), seletor de raio com nomes humanos (400 m ≈ 5 min a pé…) | Q27 |
| Relatório do local | Uso pretendido (comercial/residencial/misto); perfil 2x2 (corte = 20% de cima, ponderado por extensão, pré-registrado); distância pela rede até o eixo top 10%; faixa de percentil sobre A, B e as variantes de sensibilidade com selo "estável"/"depende da representação"; percentil ponderado por extensão. **Sem nota única, sem linguagem de preço** | Q27, Q34 |
| Entrada do relatório | Endereço (índice próprio a partir do CNEFE 2022/IBGE) ou clique no mapa. Associação ao trecho = mais próximo **com nome de logradouro compatível**; candidatos exibidos para confirmar; esquina mostra 2. Lotes depois (pedir à GeoBrusque/SEPLAN, com licença) | Q46 |
| Erro na rede | Botão que cria uma **nota no OSM** (OSM Notes API) | Q34 |
| Upload de mapa axial manual | Pós-MVP | Q34 |
| Uso indevido | Rodapé fixo com release, data e "potencial de movimento estimado pela configuração da malha; não mede preço"; termos de uso proibindo uso como avaliação de imóvel | Q27 |
| Validação empírica | Fase 2: CNPJs ativos (Receita), filtrados por CNAE dependente de movimento, MEI tratado à parte, só agregados (LGPD), comparação dentro da mesma zona do Plano Diretor. Pedir ITBI/planta de valores via LAI | Q11, Q19, Q27 |

## Metodologia

| Tema | Decisão | Q |
|---|---|---|
| Fonte | Rede viária do OpenStreetMap, extrato datado | Q2 |
| Área | Seleção por **código IBGE 4202909 + relação OSM 296588**, nunca por nome (existe uma Brusque na França). Cálculo com **buffer de 7 km**; resultados e exibição com opacidade cheia só em Brusque; o entorno aparece esmaecido | Q5, Q14 |
| CRS | SIRGAS 2000 / UTM 22S (EPSG:31982) | doc. metodológico |
| Malha base | Vias veiculares públicas + `pedestrian`, `living_street` e `steps`; exclui `service` privado (driveway, parking_aisle…) e `access=private/no`; `track` só no buffer. Footway/path entram como **variante de sensibilidade** | Q7, Q13 |
| Representações do MVP | **A** = eixos de rua; **B** = Liu & Jiang (2012). **Turner fora do MVP** (porta `AxialGenerator` preparada para quando houver footprints de edificações) | Q6, Q32 |
| L&J | COINS com `angle_threshold=135` (deflexão < 45°), atrás da porta `StrokeBuilder`; corte recursivo por x e x/d com limiares head/tail da própria rede; limiar de fusão **derivado** de mean(x/d) (3,44° fica só como referência do paper); teste COINS × every-best-fit | Q21, Q38 |
| Limpeza | Regras documentadas e versionadas. Fusão de pista dupla só se: oneway em sentidos opostos + mesmo name/ref + distância < 30 m + **nenhuma água entre elas**; teste de regressão no trecho central do rio. Pontes e túneis: conexão só por nó OSM compartilhado | Q16 |
| Componentes | Só o **maior componente conectado** é analisado; os isolados aparecem em cinza e são contados no manifesto | Q44 |
| Formato de produção | Rede limpa → Douglas-Peucker (**2 m**, pré-registrado) → **explodida em retas** antes de qualquer motor | Q47 |
| Medidas | NAIN = NC^1,2/TD e NACH = log(CH+1)/log(TD+3) (Hillier, Yang & Turner 2012), calculados por **código próprio**, igual para qualquer motor | Q3, Q43 |
| Raios | 400, 800, 1200, 2000 m e n; sempre métricos | doc. metodológico |
| Larguras (para o Turner futuro) | Caixa de via da LC 419/2024, Art. 43, mapeada por classe OSM, em `backend/methodology/v1/widths.csv` | Q15, Q28 |
| Sensibilidade | Fusão de pista dupla com/sem; borda com/sem; vias pedonais com/sem; COINS 30/45/60°; tolerância de simplificação: nenhuma, 2 m, 5 m, reta por trecho | doc. metodológico, Q13, Q47 |
| Pré-registro | Estabilidade: Spearman ponderado ≥ 0,85 e Jaccard top-10% ≥ 0,70. Limiares presos à versão da metodologia (semver); o CI falha se mudarem sem bump | Q17, Q24 |

## Motor e verificação

| Tema | Decisão | Q |
|---|---|---|
| Motor de produção | **cityseer** (multithread, ~30 s para a cidade inteira) para A e B, nas releases e nos cenários; grafo montado direto da nossa rede limpa, sem a limpeza automática dele; versão fixada | Q43, Q47 |
| Juiz | **depthmapXcli v0.9.1** (GPLv3, via subprocess, binário fixado por hash no Docker). Raio n com `-st angular` (exato); raios métricos só existem em tulip → tolerância derivada das faixas, comparando antes o conjunto de segmentos incluídos | Q20, Q43, Q47 |
| Tolerâncias | Contagem de nós exata; TD e choice com 10⁻⁵ relativo, depois da conversão de unidade (90° = 1; sentido do choice); ranking idêntico | Q17, Q47 |
| CI em 3 níveis | PR (sintéticas com jitter, empates documentados, invariância, import-linter, regressão do rio, recorte pequeno) · noturno (recorte maior) · por versão da metodologia (Brusque inteira, raio n) | Q40, Q47 |
| Plano B | Se o cityseer reprovar: depthmapX com rede simplificada, cenários com ~12 min de espera | Q43 |

## Arquitetura

| Tema | Decisão | Q |
|---|---|---|
| Linguagem | Python 3.13 no backend (FastAPI); React + TypeScript + Vite + MapLibre no frontend | Q4, Q30 |
| Estilo | **DDD** + hexagonal/clean, num **monólito modular**; entrypoints `api`, `worker`, `scheduler`, `cli` sobre o mesmo código | Q38, Q50 |
| Contextos | Rede Viária · **Análise Sintática** (núcleo) · Releases · **Cenários** (núcleo) · Relatório do Local · Identidade. Contextos não importam o domínio uns dos outros (import-linter) | Q49 |
| Pureza do domínio | O domínio pode usar shapely/numpy/networkx; nada de I/O, geopandas IO, FastAPI, Redis, SQL, subprocess ou motores | Q39 |
| Modelo tático | Agregados `NetworkSnapshot`, `NetworkErrorReport`, `AnalysisRun`, `Release`, `Scenario`, `User`; política `QuotaPolicy`; Relatório do Local só de leitura | Q52 |
| Eventos | Shared kernel mínimo; outbox transacional no PostGIS → RQ; CQRS leve (PMTiles, GeoParquet em memória, projeção `requests`) | Q53 |
| Língua do código | Inglês, com glossário PT↔EN em `docs/glossary.md`; interface em português | Q51 |

## Mudanças após a sessão (2026-11-05)

| Tema | Decisão |
|---|---|
| API desde já | A **API FastAPI serve a rede** (`/api/v1/network/*`, gzip + ETag); o frontend consome só a API. O **CLI fica para cold start** e reprocessamento (`snapshot build`). O antigo `export-web` foi removido |
| Simbologia | Paleta de 7 classes do design "Quantumco App" no espectro dos mapas de Londres (azul = segregado → vermelho = integrado), sobre fundo escuro; classes por percentil ponderado por extensão; integrados por cima (`backend/methodology/v1/symbology.yaml`). Camadas não sintáticas em tons neutros |
| Armazenamento servido | **PostGIS** é a fonte da API: schemas `road_network` e `syntax_analysis` (um por contexto), gravação por `COPY` e publicação atômica (`is_current` trocado na mesma transação). Arquivos locais só como fallback de desenvolvimento. RustFS fica para arquivar releases (ajusta a Q33) |
| Marca | Identidade do Claude Design ("Quantumco Brand"/"Quantumco App"): Vácuo `#050607`, Grafite `#0F1213`, Branco `#F4F6F5`, Feixe verde `#2BD46B`, Feixe azul `#3B8CFF`; Outfit 200–400 (sem negrito pesado) e IBM Plex Mono para dados e rótulos; mapa escuro com painel de vidro |
| E-mail | API do Resend, remetente `spacesyntax@erickkbonfim.com.br` |

## Infra e operação

| Tema | Decisão | Q |
|---|---|---|
| Hospedagem | VPS Hostinger **KVM 2** (2 vCPU, 8 GB, 100 GB NVMe) com Easypanel | Q25 |
| Containers | web (Caddy), api, worker, scheduler, redis (AOF em volume), postgis, rustfs | Q35, Q45 |
| Armazenamento | PostGIS para o que muda (usuários, cenários, pedidos, outbox); **RustFS** (S3) para os arquivos imutáveis das releases, atrás da porta `ReleaseStore` | Q33 |
| Fila e agenda | **RQ 2.12.x** (fixado); `CronScheduler` do RQ, agenda no código, `America/Sao_Paulo`, pipeline domingo 03:00; upgrade para 3.0 via ADR | Q35, Q36 |
| Releases | Semanais via scheduler: A + B + diff; publica só se a rede mudou. Sensibilidade completa mensal ou a cada versão da metodologia. Manifestos para sempre; dados semanais por 3 meses; 1 mensal permanente | Q10, Q24 |
| Capacidade | 1 cenário por vez; 1 em andamento por usuário, 10/dia, fila máx. 20; cache Redis por hash(release + edições normalizadas); pipeline semanal pausa os cenários | Q45 |
| Login | E-mail + senha (Argon2id), confirmação de e-mail e recuperação de senha via **API do Resend** (remetente `spacesyntax@erickkbonfim.com.br`, chave só com permissão de envio; sem chave, os e-mails vão para o log), Cloudflare Turnstile no cadastro. Tipos: arquitetura/urbanismo, construtora/incorporadora, pesquisa, poder público, outro. Papéis: `user`, `admin` | Q37, Q48, Q55 |
| Acompanhamento | Tabela `requests` + página de admin + painel do RQ atrás do login. Nada além disso | Q41 |
| Mapa de fundo | Protomaps auto-hospedado (PMTiles da região); OpenFreeMap como fallback | Q30 |
| Licenças | Código AGPL-3.0; dados ODbL 1.0 (© OpenStreetMap contributors); relatório metodológico CC BY 4.0; atribuição IBGE/CNEFE | Q22 |
| Repositório | Público no GitHub desde o início; CI no GitHub Actions; imagens no GHCR; deploy no Easypanel | Q40, Q56 |

## Ordem de construção (Q57)

1. Esqueleto: monorepo, CI do PR, `backend/methodology/v1/`, contexto Rede Viária (OSM → limpeza → snapshot)
2. Análise A no cityseer + juiz depthmapX no CI ← **maior risco técnico**
3. Release + mapa (PMTiles, RustFS, MapLibre, deploy)
4. B (Liu & Jiang) + comparação + sensibilidade + mapa de discordância
5. Relatório do local (CNEFE, associação ao trecho, perfil 2x2, faixa de percentil)
6. Identidade + Cenários + fila + cache
7. Página de admin, termos de uso, relatório metodológico publicado

## Fatos levantados na sessão

- OSM de Brusque-SC (2026-11-05): 4.978 vias; 510 edificações; `width` em 1 via; 3.610 vias na malha base; ~9,6 mil no buffer de 7 km.
- Benchmark (M3 Pro): 10.632 trechos entre cruzamentos (2.115 km). depthmapX: núcleo único; raio n na geometria completa (80.611 segmentos) ≈ 2,7 h; uma reta por trecho ≈ 64 s. cityseer 5.8.0: 26 s com 2 threads, 375 MB.
- cityseer acumula em f64 e grava a saída em f32; soma o ângulo ao longo da geometria curva da aresta. Licença AGPL-3.0.
- depthmapXcli: NAIN/NACH não são calculados; o modo metric só existe em tulip; a issue #437 não se reproduz na v0.9.1.
- CNEFE 2022 de Brusque: 65.812 endereços, 91% com a coordenada original do censo, com nome de logradouro.
- Lotes de Brusque: Portal Geo só para visualização; não há download nem licença.
