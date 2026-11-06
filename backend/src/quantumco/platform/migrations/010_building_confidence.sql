-- Confiança do modelo que detectou a edificação (Google Open Buildings traz 0..1; OSM não tem).
-- Guardada para filtrar depois sem reimportar (docs/specs/camadas-fase-b.md, F1).
alter table territory.buildings add column confidence real;
