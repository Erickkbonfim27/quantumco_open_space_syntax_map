-- CNPJ da Receita Federal (docs/adr/0001-clickhouse-dados-nacionais.md).
-- Uma partição por competência (AAAA-MM): a carga apaga e refaz a competência inteira.
-- Sem nome fantasia, telefone, e-mail nem sócios (LGPD).

CREATE TABLE IF NOT EXISTS cnpj_estabelecimentos (
    competencia        LowCardinality(String),
    cnpj_basico        String,
    cnpj_ordem         String,
    cnpj_dv            String,
    matriz_filial      UInt8,                      -- 1 matriz, 2 filial
    situacao           LowCardinality(String),     -- 01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada
    data_situacao      Nullable(Date32),
    motivo_situacao    LowCardinality(String),
    data_inicio        Nullable(Date32),
    cnae_principal     LowCardinality(String),
    cnaes_secundarios  Array(LowCardinality(String)),
    tipo_logradouro    LowCardinality(String),
    logradouro         String,
    numero             String,
    complemento        String,
    bairro             String,
    cep                String,
    uf                 LowCardinality(String),
    municipio_rf       UInt16,                     -- código da Receita (Brusque = 8055), não o do IBGE
    situacao_especial  LowCardinality(String)
) ENGINE = MergeTree
PARTITION BY competencia
ORDER BY (uf, municipio_rf, cnpj_basico, cnpj_ordem);

CREATE TABLE IF NOT EXISTS cnpj_simples (
    competencia        LowCardinality(String),
    cnpj_basico        String,
    simples            Bool,
    mei                Bool,
    data_opcao_mei     Nullable(Date32),
    data_exclusao_mei  Nullable(Date32)
) ENGINE = MergeTree
PARTITION BY competencia
ORDER BY cnpj_basico;

CREATE TABLE IF NOT EXISTS receita_municipios (
    competencia  LowCardinality(String),
    codigo       UInt16,
    nome         String
) ENGINE = MergeTree
PARTITION BY competencia
ORDER BY codigo;

CREATE TABLE IF NOT EXISTS receita_cnaes (
    competencia  LowCardinality(String),
    codigo       String,
    descricao    String
) ENGINE = MergeTree
PARTITION BY competencia
ORDER BY codigo;

CREATE TABLE IF NOT EXISTS carga_log (
    competencia  LowCardinality(String),
    arquivo      String,
    linhas       UInt64,
    bytes        UInt64,
    segundos     Float64,
    em           DateTime DEFAULT now()
) ENGINE = MergeTree
ORDER BY (competencia, arquivo, em);
