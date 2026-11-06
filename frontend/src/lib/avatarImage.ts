/**
 * Prepara a foto de perfil no navegador: recorta o centro em quadrado e reduz para 256 px,
 * em WebP (ou JPEG, se o navegador não gerar WebP). Fica com ~10–40 KB.
 */
export async function squareAvatar(file: File, size = 256): Promise<Blob> {
  if (!file.type.startsWith("image/")) throw new Error("Escolha um arquivo de imagem.");
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const g = canvas.getContext("2d");
  if (!g) throw new Error("Seu navegador não conseguiu ler a imagem.");
  g.imageSmoothingQuality = "high";
  g.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, size, size);
  bitmap.close();
  const encode = (type: string, quality: number) =>
    new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, quality));
  const webp = await encode("image/webp", 0.86);
  const blob = webp && webp.type === "image/webp" ? webp : await encode("image/jpeg", 0.88);
  if (!blob) throw new Error("Não foi possível preparar a imagem.");
  return blob;
}
