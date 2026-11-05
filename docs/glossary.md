# Glossário (linguagem ubíqua) PT ↔ EN

| Português (interface) | Inglês (código) | Definição |
|---|---|---|
| Área de estudo | `StudyArea` | Município (código IBGE + relação OSM) mais a faixa externa |
| Faixa externa / buffer | `Zone.BUFFER` | Área fora do município usada só para reduzir o efeito de borda |
| Zona de resultado | `Zone.RESULT` | Dentro do município; entra nos resultados |
| Trecho | `RoadLink` / segment | Rua entre dois cruzamentos |
| Snapshot da rede | `NetworkSnapshot` | Rede analisável numa data registrada do OSM |
| Relatório de limpeza | `CleaningReport` | Contagens do que entrou, saiu e por quê |
| Facilidade de chegar | NAIN (`nain`) | Integração angular normalizada (Hillier, Yang & Turner 2012) |
| Potencial de passagem | NACH (`nach`) | Escolha angular normalizada |
| Raio | `Radius` | Distância métrica (400, 800, 1200, 2000 m) ou n (cidade inteira) |
| Representação | `Representation` | A = eixos de rua; B = Liu & Jiang |
| Release | `Release` | Conjunto publicado e imutável de resultados + manifesto |
| Cenário | `Scenario` | Edições sobre uma release base e o recálculo resultante |
