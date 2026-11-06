// Relevo: Terrain Tiles da AWS (Mapzen; SRTM, USGS, ETOPO1), dados abertos, codificação terrarium.
// Usado pelo mapa (sombreamento e terreno 3D) e pela maquete de relevo do painel de camadas.
export const DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
export const DEM_ATTRIBUTION =
  '<a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noreferrer">Terrain Tiles (AWS · SRTM/USGS)</a>';

/** Altitude (m) de um pixel terrarium. */
export const terrarium = (r: number, g: number, b: number) => r * 256 + g + b / 256 - 32768;
