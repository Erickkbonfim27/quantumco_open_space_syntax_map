# Fontes de dados: view "Análise de polígonos"

Levantamento de 2026-11-05 para o design `Quantumco Polígonos.dc.html` (Claude Design).
Critério: fontes **gratuitas**, que cobrem Brusque (IBGE 4202909), de preferência as que a
Vizzion já integrava (ver o portfólio, "Plataforma de dados da Vizzion").

## Mapa de dados → fonte

| Camada (design) | Dado | Fonte | Acesso | Licença | Situação |
|---|---|---|---|---|---|
| N1 Território | área, perímetro, vértices | geometria do polígono (EPSG:31982) | cálculo próprio | – | pronto para implementar |
| Polígonos prontos | bairros de Brusque | **IBGE Bairros 2022** (27 bairros, `CD_BAIRRO` 4202909001–027) | `geoftp.ibge.gov.br/.../censo_2022/bairros/shp/UF/SC_bairros_CD2022.zip` | uso livre citando "Fonte: IBGE" (sem licença aberta formal) | verificado |
| | alternativa | OSM `boundary=administrative` admin_level 9/10 (32 polígonos) | Overpass | ODbL | verificado; diverge do IBGE |
| N5 Rede viária | trechos, km, integração/escolha, distribuição por classe | **snapshot + análise próprios** (OSM + cityseer) | API `/api/v1/syntax/*` | ODbL | **pronto** (preliminar até o juiz depthmapX) |
| N3 População | habitantes, hab/km², domicílios | **IBGE Grade Estatística 2022** (200 m urbano / 1 km rural; `TOTAL`, `TOTAL_DOM`) | `.../grade_estatistica/censo_2022/grade_estatistica/grade_id15.zip` | "Fonte: IBGE" | verificado |
| | conferência | IBGE Agregados por Setor 2022 (206 setores; `v0001` pessoas, `v0002` domicílios, `v0007` ocupados) | `ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/` | "Fonte: IBGE" | verificado (soma = 141.385 hab.) |
| | domicílios exatos | **CNEFE 2022** (65.812 endereços com coordenada; espécie 1 = domicílio) | `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/...` | "Fonte: IBGE" | verificado |
| N2 Relevo | altitude mín./máx., declividade | **SIGSC MDT 1 m** (levantamento SDS/SC 2010–2012, modelo de *terreno*) | WCS público `sigsc.sc.gov.br/sigserver/SIGSC/wcs`, cobertura `SIGSC__MDT-2012` | "acesso livre", sem licença de redistribuição → servir só estatísticas derivadas, citando SDE/SC | verificado |
| | alternativa | Copernicus DEM GLO-30 (modelo de *superfície*, inclui prédios/árvores) | `copernicus-dem-30m.s3.amazonaws.com`, tile `S28_W049` | licença Copernicus (livre, com aviso) | verificado |
| | alternativa | TOPODATA/INPE 30 m, tile `27S495` (já traz declividade pronta) | `dsr.inpe.br/topodata` | CC BY-SA 4.0 | verificado |
| N4 Uso do solo | áreas verdes | **ESA WorldCover 10 m** (2021) ou MapBiomas 30 m (Col. 10, via Earth Engine) | COG em S3 / GEE | CC BY 4.0 | verificado |
| | residencial / comercial / institucional | **CNEFE 2022** por espécie (domicílio · outras finalidades · ensino + saúde + religioso) | arquivo IBGE | "Fonte: IBGE" | verificado |
| | institucional (complemento) | INEP (escolas) e CNES/DataSUS (saúde), com coordenadas | APIs abertas (já integradas na Vizzion) | abertos | a integrar |
| | industrial | CNPJ ativos da Receita, CNAE seção C (geocodificar pelo CNEFE) | dados abertos da Receita | aberto | a integrar |
| | área construída | Microsoft Building Footprints (quadkeys 210313010 e 210311232) | `bfppub.blob.core.windows.net` | CDLA Permissive 2.0 | verificado |
| Busca | bairro, rua, endereço | IBGE Bairros + nomes de rua do OSM + logradouros do CNEFE | índice próprio | – | – |

## Não existe aberto (pedir via LAI à GeoBrusque/SEPLAN)

- Lotes / cadastro imobiliário (o Portal Geo da prefeitura é só visualização).
- Zoneamento da LC 419/2024 em formato geográfico.
- Bairros oficiais da prefeitura (uma fonte não oficial cita 33; o IBGE tem 27).

## Camadas extras possíveis (fontes já usadas na Vizzion)

- Risco geológico: setorização de risco do SGB-CPRM.
- Inundação (relevante no vale do Itajaí-Mirim): CEMADEN, S2iD/Defesa Civil, ANA.

## Camadas importadas (fase A, 2026-11-05)

`uv run quantumco territory import` (schema `territory` no PostGIS; `--only <fonte>` para uma só).
O perfil de cada polígono sai em `POST /api/v1/territory/polygon-profile`.

| Camada no painel | Fonte | Recorte no polígono | Registros |
|---|---|---|---|
| N3 População e renda | IBGE Censo 2022: malha de setores com agregados (V0001, V0003, V0007) + renda do responsável (V06001, V06004, V06006) | **dasimétrico**: parcela dos domicílios do CNEFE do setor que cai no polígono (fração de área só em setor sem domicílio) | 206 setores (141.385 hab.) |
| N4 Entorno urbano | IBGE Censo 2022: entorno dos domicílios (V05000–V05034) | idem; % dos domicílios em faces com calçada, iluminação, árvores, rampa, ponto de ônibus… | 186 setores pesquisados |
| N5 Equipamentos e uso | IBGE CNEFE 2022 (espécie do endereço, coordenada nível ≤ 3) + CNES (Ministério da Saúde) | contagem de pontos | 65.659 endereços · 506 estabelecimentos de saúde |
| N6 Risco | SGB: setores de risco geológico (2018–19) e cartas de suscetibilidade IPT/SGB (2013) | área recortada; pessoas em risco proporcionais à área do setor | 199 setores · 1.820 polígonos de suscetibilidade |
| N7 Forma construída (fase B, 2026-11-06) | Overture Maps, tema buildings, release `2026-10-21.0` (fixo em `territory/infrastructure/overture.py`), lido pela biblioteca `overturemaps` no retângulo da grade de 30 m | contagem pelo ponto interno da pegada; área no chão recortada; taxa de ocupação = área no chão ÷ área do polígono | 94.366 edificações (Google 66.417 · Microsoft 27.214 · OSM 735); 2 descartadas < 10 m²; altura em 8 |

Cuidados: o CNES traz telefone e e-mail de consultórios; guardamos só nome, tipo, SUS e coordenada.
O CNEFE mostra obras "em construção" **em 2022**, não hoje.
Edificações: licença do tema ODbL 1.0 (Microsoft ML Buildings: ODbL; Google Open Buildings: CC BY 4.0),
crédito "© OpenStreetMap contributors, Overture Maps Foundation" no mapa e no painel. Guardamos a
confiança da detecção (Google) para filtrar depois sem reimportar.

## Próximas fases

- **B. Empresas e obras**: CNPJ da Receita (mensal; Brusque = município 8055 da Receita) e CNO
  (Cadastro Nacional de Obras), localizados pelo CEP + número cruzados com o CNEFE. Licença dos
  arquivos da Receita não confirmada; MEI traz nome e endereço do dono → publicar só agregado.
- **C. Relevo**: MDT 1 m do SIGSC (só estatísticas derivadas). Prédios já entraram pelo Overture
  (acima); a altura do Google 2.5D Temporal fica de fora até confirmarmos acesso fora do Earth
  Engine (uso comercial do GEE é pago).
- Plano completo das fontes novas: `docs/specs/camadas-fase-b.md`.
- Descartados: RAIS e CAGED (só município; a RAIS de estabelecimentos tem CEP, sem endereço),
  Google Places (os termos proíbem guardar, usar em mapa que não seja do Google e fazer
  ponto-em-polígono), luz noturna VIIRS (500 m, grossa demais), GTFS (Brusque não tem).
