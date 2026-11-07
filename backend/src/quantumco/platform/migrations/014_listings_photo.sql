-- Imóveis à venda (docs/adr/0003): link da foto de capa para a janela do mapa.
-- Só o link: a imagem continua no servidor do portal. Fica fora da impressão digital.
alter table listings.sale_listings add column if not exists photo_url text;
