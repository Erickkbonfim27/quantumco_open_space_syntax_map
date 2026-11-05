export function Footer() {
  return (
    <footer className="panel-section footer">
      <p>
        Potencial de movimento estimado pela configuração da malha; <strong>não mede preço</strong>.
      </p>
      <p>
        Dados ©{" "}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
          OpenStreetMap
        </a>{" "}
        (ODbL) · Código{" "}
        <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer">
          AGPL-3.0
        </a>
      </p>
    </footer>
  );
}
