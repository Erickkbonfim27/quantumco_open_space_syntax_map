# ADR 0001 — ClickHouse para dados nacionais, na mesma VPS

Data: 2026-11-06 · Status: **aceito**

## Contexto

O CNPJ da Receita (e, depois, o CNEFE nacional) só é publicado em arquivos nacionais: cerca de
5,7 GB zipados por mês só para o que usamos (Estabelecimentos e Simples), ~65 milhões de
estabelecimentos. O projeto vai crescer de Brusque para o país. O dono pediu que **nenhum dado da
Receita passe pela máquina de desenvolvimento** e que **nada pesado rode localmente**.

Alternativas consideradas:

| Opção | Por que não (agora) |
|---|---|
| Baixar local, filtrar Brusque e apagar | tráfego e disco na máquina do desenvolvedor; recusado |
| Espelho não oficial (Parquet no Hugging Face) | não é a fonte oficial; pode atrasar ou ter erro de conversão |
| DuckDB/pyarrow sobre Parquet no RustFS | leve e sem servidor; bom para lote, mas o dono preferiu um serviço analítico próprio |
| Elasticsearch | feito para busca de texto, não para agregação; JVM pesada (2–4 GB só de heap) |
| ClickHouse numa VPS separada / VPS maior | isola melhor, mas custa mais; fica para quando entrar o 2º dado nacional pesado |

## Decisão

**ClickHouse 26.3 (imagem `clickhouse/clickhouse-server:26.3.9.8`) na mesma VPS (KVM 2), com
limites**, e o fluxo:

```
Receita (WebDAV oficial) ──► worker-dados (VPS) ──► RustFS: bruto (ZIPs como vieram)
                                                  └► ClickHouse: tratado (sem contatos)
ClickHouse ──► recorte da cidade, localizado pelo CNEFE ──► PostGIS ──► mapa
```

- **Bruto** no RustFS, bucket `quantumco-dados`, chave `receita/cnpj/AAAA-MM/arquivo.zip`.
  Reprocessar não baixa da Receita de novo.
- **Tratado** no banco `dados` do ClickHouse; esquema versionado em
  `backend/src/quantumco/platform/clickhouse_migrations/`. Uma partição por competência; a carga
  refaz a competência inteira (idempotente).
- **LGPD**: nome fantasia, telefone, e-mail e sócios não entram no tratado. O endereço entra só
  para localizar; o mapa mostra agregados, nunca empresas de MEI como ponto.
- **Onde roda**: serviço `worker-dados` no Easypanel (`QC_ROLE=worker-dados`, fila RQ `dados`,
  1 processo). A trava `QC_ALLOW_RECEITA_DOWNLOAD=1` só existe nesse serviço: em qualquer outra
  máquina o download recusa rodar.
- **Limites** (KVM 2: 2 vCPU, 8 GB): contêiner com 3 GB de RAM e 1 núcleo; servidor ClickHouse
  para em 2,5 GB (`infra/clickhouse/config.d/quantumco-limits.xml`); consultas com até 2 threads e
  GROUP BY/ORDER BY grandes em disco (`infra/clickhouse/users.d/quantumco-profile.xml`). A carga
  usa 1 thread e roda fora do horário de uso.
- **Acesso**: só pela rede interna do Easypanel (sem porta pública), usuário `quantumco` com
  senha no `QC_CLICKHOUSE_URL`.

## Consequências

- Mais um serviço para acompanhar (memória e disco). Revisar quando: o uso de RAM da VPS passar
  de 85% por períodos longos, o disco passar de 70%, ou entrar o CNEFE nacional. Próximo passo
  nesse caso: VPS separada para dados (opção B).
- Disco: bruto ~6 GB/mês + tratado (estimativa: alguns GB); política inicial: manter o bruto
  dos últimos 3 meses no RustFS.
- Agendamento mensal ainda não existe: a carga é disparada com
  `quantumco dados cnpj --enfileirar` (ou no console do worker-dados).
