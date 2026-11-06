"""Dados nacionais (contexto `datasets`): cargas mensais de bases públicas para o ClickHouse.

Bruto (ZIPs como vieram) no RustFS; tratado no ClickHouse; o recorte de cada cidade vai para o
PostGIS pelo contexto `territory`. Decisão: docs/adr/0001-clickhouse-dados-nacionais.md.
"""
