-- Índice de busca de endereços (CNEFE 2022, Q46): um ponto por número de logradouro e um por
-- logradouro. Coordenadas em WGS84 (só para enquadrar o mapa; nada de geometria pesada).
create table territory.addresses (
    address_id  bigserial primary key,
    street      text not null,             -- "Rua Hercílio Luz"
    number      integer,                   -- null = o logradouro inteiro
    locality    text,
    cep         text,
    units       integer not null,          -- endereços do CNEFE representados
    search_key  text not null,             -- minúsculas, sem acento, abreviações expandidas
    lon         double precision not null,
    lat         double precision not null
);
create index addresses_street on territory.addresses (street, number);

-- trigramas aceleram o "contém" da busca; sem a extensão a busca funciona igual (65 mil linhas)
do $$
begin
    create extension if not exists pg_trgm;
    create index addresses_search on territory.addresses using gin (search_key gin_trgm_ops);
exception when others then
    raise notice 'pg_trgm indisponível: busca de endereços sem índice de trigramas';
end
$$;
