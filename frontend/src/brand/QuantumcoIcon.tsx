/**
 * Ícone da marca (Quantumco Brand, Claude Design): anel externo + síncrotron com os dois
 * feixes, verde e azul, em sentidos opostos. Abaixo de 64 px usa-se só o ícone, sem o anel
 * de texto do selo.
 */
interface QuantumcoIconProps {
  size?: number;
  title?: string;
}

export function QuantumcoIcon({ size = 34, title }: QuantumcoIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      className="brand-icon"
    >
      <circle cx="50" cy="50" r="46" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="50" cy="46" r="20" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="50" cy="72" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
      <line x1="32" y1="78" x2="50" y2="78" stroke="currentColor" strokeWidth="2" />
      <circle cx="64.1" cy="31.9" r="3.4" fill="var(--beam-green)" />
      <circle cx="35.9" cy="60.1" r="3.4" fill="var(--beam-blue)" />
    </svg>
  );
}
