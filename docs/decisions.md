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
| Laboratório de cenários | `quantumco scenario run --name … --remove <trecho> --add "lon,lat;…"`: aplica as edições, recalcula a **cidade inteira** (todos os raios) com o mesmo motor e compara trecho a trecho com a análise publicada. Classes do cenário pelos **cortes da base** (percentis do próprio cenário reescalonariam e esconderiam o efeito). Ruas novas se conectam pelas pontas, encaixadas até 30 m na rede (o trecho atingido é dividido). Resultado no PostGIS (`syntax_analysis.scenarios*`), na API (`/api/v1/scenarios`) e no mapa (`/?cenario=nome`, cores de mudança fora da escala sintática). Sem login nem fila ainda (passo 6) |
| Plataforma (design "Quantumco Plataforma") | Rotas: `/` landing · `/map` mapa público · `/entrar` e `/criar-conta` · `/painel` (cenários do usuário) · `/painel/cenario/:id` (mapa com polígonos e camadas). Conta com nome, instituição (opcional), e-mail e senha (Argon2id, ≥ 8 caracteres); sessão em cookie `HttpOnly` + `SameSite=Lax` + `Secure`, token só como hash sha256 no banco, 30 dias. Login não revela se o e-mail existe. Cenário do usuário = espaço de trabalho (nome, medida, status, polígonos); camadas por polígono calculadas no PostGIS com trechos **recortados** pelo polígono: N2 Rede viária e N1 Território. População, relevo e uso do solo depois. Pendentes: confirmação de e-mail (Resend), Turnstile, limite de tentativas de login |
| Cenários com edição da rede | No cenário do usuário: **remover**, **interditar** (mesmo efeito de remover na sintaxe; outro rótulo), **nova via** (pontas encaixam a até 30 m; só as pontas conectam) e **redesenhar** (remove a original e cria o traçado novo). Edições guardadas no cenário (`scenarios.workspaces.edits`) e congeladas em cada pedido de cálculo |
| Fila de cálculo | **Redis + RQ 2.12** (fila `scenarios`), `quantumco worker` com pool de 2–4 processos (`QC_WORKERS`), um "work horse" por cálculo; estado e etapas (fila, carga, edições, motor, comparação, gravação) com horário em `scenarios.runs` (PostGIS); a tela consulta a cada 2–3 s. Limites: 2 ativos por usuário, 10 por dia (o `OWNER_EMAIL` não tem limite diário), 20 na fila, 60 min por cálculo. Resultado privado, um por cenário (`ws-<id>`), fora da rota pública. Medido: motor ~7,4 min sozinho (M3 Pro, 2 threads) e ~12,7 min com 2 em paralelo; na VPS de 2 vCPU, mais workers não aumentam a vazão |
| Tema e fundos do mapa | Tema claro e escuro (padrão: o do sistema), salvo no perfil. Fundos: automático (segue o tema), escuro, claro, ruas (OSM/OpenFreeMap), satélite (Esri World Imagery) e topográfico (OpenTopoMap), todos no mesmo estilo (troca sem recarregar a rede) |
| Busca de endereço | Índice próprio do **CNEFE 2022** (`territory.addresses`, ~31 mil números e logradouros), sem serviço externo; enquadra o mapa com um pin. No cenário, a busca alterna entre polígono e endereço |
| Dados e metodologia | Páginas internas (`/dados` com abas Fontes e Indicadores; `/metodologia`), sem links para o GitHub. Downloads de polígonos (GeoJSON) removidos; abas "Comparar" e "Relatórios" removidas até existirem |
| Marca | Identidade do Claude Design ("Quantumco Brand"/"Quantumco App"): Vácuo `#050607`, Grafite `#0F1213`, Branco `#F4F6F5`, Feixe verde `#2BD46B`, Feixe azul `#3B8CFF`; Outfit 200–400 (sem negrito pesado) e IBM Plex Mono para dados e rótulos; mapa escuro com painel de vidro |
| E-mail | API do Resend, remetente `noreply@quantumco.com.br` (era `spacesyntax@erickkbonfim.com.br`; domínio precisa estar verificado no Resend) |
| Conta por e-mail | Confirmação de e-mail no cadastro, troca de e-mail e troca de senha **só por link no e-mail** (uso único, sha256 no banco; 48 h para e-mail, 1 h para senha; 1 envio por minuto por tipo). E-mail novo só vale depois de confirmado (o antigo recebe aviso). Senha nova encerra todas as sessões e manda aviso. "Esqueci a senha" responde igual exista ou não a conta. E-mails em HTML no design da marca (tabelas, estilos inline, Vácuo/Grafite/Branco, feixes verde e azul, Outfit e IBM Plex Mono) com versão em texto. Links usam `QC_PUBLIC_BASE_URL` (em dev, a origem `localhost` do pedido) |
| Foto de perfil | Arquivo no **RustFS** (bucket privado `QC_S3_BUCKET_AVATARS`, cliente MinIO, chave `avatars/{usuário}/{instante}.{ext}`); o banco guarda só a chave. Tipo pelo conteúdo (PNG/JPEG/WebP, ≤ 512 KB, reduzida no navegador). A API entrega a foto ao dono (`/me/avatar?v=…`, cache imutável); sem armazenamento, o envio responde 503 |

## Infra e operação

| Tema | Decisão | Q |
|---|---|---|
| Hospedagem | VPS Hostinger **KVM 2** (2 vCPU, 8 GB, 100 GB NVMe) com Easypanel | Q25 |
| Containers | web (Caddy), api, worker, scheduler, redis (AOF em volume), postgis, rustfs | Q35, Q45 |
| Armazenamento | PostGIS para o que muda (usuários, cenários, pedidos, outbox); **RustFS** (S3) para os arquivos imutáveis das releases, atrás da porta `ReleaseStore` | Q33 |
| Fila e agenda | **RQ 2.12.x** (fixado); `CronScheduler` do RQ, agenda no código, `America/Sao_Paulo`, pipeline domingo 03:00; upgrade para 3.0 via ADR | Q35, Q36 |
| Releases | Semanais via scheduler: A + B + diff; publica só se a rede mudou. Sensibilidade completa mensal ou a cada versão da metodologia. Manifestos para sempre; dados semanais por 3 meses; 1 mensal permanente | Q10, Q24 |
| Capacidade | 1 cenário por vez; 1 em andamento por usuário, 10/dia, fila máx. 20; cache Redis por hash(release + edições normalizadas); pipeline semanal pausa os cenários | Q45 |
| Login | E-mail + senha (Argon2id), confirmação de e-mail e recuperação de senha via **API do Resend** (remetente `noreply@quantumco.com.br`, chave só com permissão de envio; sem chave, os e-mails vão para o log), Cloudflare Turnstile no cadastro. Tipos: arquitetura/urbanismo, construtora/incorporadora, pesquisa, poder público, outro. Papéis: `user`, `admin` | Q37, Q48, Q55 |
| Acompanhamento | Tabela `requests` + página de admin + painel do RQ atrás do login. Nada além disso | Q41 |
| Homologação (2026-11-06) | Banco `quantumco_homolog` **no mesmo Postgres** da produção, atualizado **sob demanda** com `quantumco db sync-homolog`: aplica exatamente as migrações da produção e copia **todos** os dados por `postgres_fdw`, dentro do servidor (~14 s). **Sem replicação contínua**: exigiria `wal_level=logical` (reinício da prod), não replica DDL, conflita com migrações e importações testadas antes na homologação, e um slot parado encheria o disco da prod. Com `QC_USE_HOMOLOG=1`: banco de homologação, fila RQ `scenarios-homolog` (longe dos workers da prod) e e-mails desviados para `OWNER_EMAIL` (há contas reais na cópia). Fluxo: sync → migração/importação nova com `QC_USE_HOMOLOG=1` → conferir local → aplicar na prod | — |
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
