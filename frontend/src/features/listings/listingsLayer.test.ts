import { describe, expect, it } from "vitest";
import { listingIcon, listingPopupHtml, safeUrl, typeLabel } from "./listingsLayer";

const APARTMENT = {
  property_type: "APARTMENT",
  bedrooms: 2,
  suites: 1,
  bathrooms: 2,
  parking_spaces: 1,
  usable_area_m2: 70,
  price_brl: 450000,
  condo_fee_brl: 350,
  iptu_brl: 1200,
  street: "Rua Hercílio Luz",
  neighborhood: "Centro <b>",
  url: "https://www.vivareal.com.br/imovel/apartamento-2-quartos-id-1/",
  photo_url: "https://resizedimgs.vivareal.com/img/vr-listing/eb50/imovel.jpg?action=fit-in&dimension=640x480",
  portal: "vivareal",
  seen: "2026-11-07",
};

describe("imóveis à venda no mapa", () => {
  it("usa o pino de prédio para apartamento e o de casa para o resto", () => {
    expect(listingIcon("APARTMENT")).toBe("qc-imovel-predio");
    expect(listingIcon("PENTHOUSE")).toBe("qc-imovel-predio");
    expect(listingIcon("HOME")).toBe("qc-imovel-casa");
    expect(listingIcon("RESIDENTIAL_ALLOTMENT_LAND")).toBe("qc-imovel-casa");
    expect(listingIcon(undefined)).toBe("qc-imovel-casa");
  });

  it("dá nome aos tipos do portal", () => {
    expect(typeLabel("APARTMENT")).toBe("Apartamento");
    expect(typeLabel("RESIDENTIAL_ALLOTMENT_LAND")).toBe("Terreno");
    expect(typeLabel("SOME_NEW_TYPE")).toBe("Some new type");
    expect(typeLabel(null)).toBe("Imóvel");
  });

  it("só aceita links https do portal", () => {
    const hosts = ["vivareal.com.br"];
    expect(safeUrl("https://www.vivareal.com.br/imovel/1/", hosts)).toBe("https://www.vivareal.com.br/imovel/1/");
    expect(safeUrl("http://www.vivareal.com.br/imovel/1/", hosts)).toBeNull();
    expect(safeUrl("javascript:alert(1)", hosts)).toBeNull();
    expect(safeUrl("https://golpe.com/www.vivareal.com.br", hosts)).toBeNull();
    expect(safeUrl("https://vivareal.com.br.golpe.com/", hosts)).toBeNull();
    expect(safeUrl(42, hosts)).toBeNull();
  });

  it("monta a janela com foto, preço, cômodos, taxas e link, com o texto escapado", () => {
    const html = listingPopupHtml(APARTMENT);
    expect(html).toContain("Apartamento · 2 quartos");
    expect(html).toMatch(/R\$\s?450\.000/);
    expect(html).toMatch(/R\$\s?6\.429\/m²/);
    expect(html).toContain("70 m² · 1 suíte · 2 banheiros · 1 vaga");
    expect(html).toMatch(/Condomínio R\$\s?350\/mês · IPTU R\$\s?1\.200\/ano/);
    expect(html).toContain("Centro &#60;b&#62;");
    expect(html).not.toContain("<b>");
    expect(html).toContain('src="https://resizedimgs.vivareal.com/img/vr-listing/eb50/imovel.jpg?action=fit-in&#38;dimension=640x480"');
    expect(html).toContain('href="https://www.vivareal.com.br/imovel/apartamento-2-quartos-id-1/"');
    expect(html).toContain("Ver anúncio no Viva Real");
    expect(html).toContain("visto em 07/11/2026");
  });

  it("sem preço, foto ou link a janela continua legível", () => {
    const html = listingPopupHtml({ property_type: "HOME", url: "https://outro-site.com/x", photo_url: "nada" });
    expect(html).toContain("Casa");
    expect(html).toContain("Preço sob consulta");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<a ");
  });
});
