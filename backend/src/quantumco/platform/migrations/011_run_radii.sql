-- Alcance do cálculo de cenário: os raios pedidos. Sem "n", só a região afetada é recalculada
-- (exato; syntax_analysis/domain/scope.py). Pedidos anteriores foram da cidade inteira.
alter table scenarios.runs
    add column radii text[] not null default '{400,800,1200,2000,n}';
