import { useId } from "react";

/** Selo com o anel de Bohr (Quantumco Brand). Acima de 64 px. */
export function Seal({ size = 72 }: { size?: number }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className="brand-icon" aria-hidden="true">
      <defs>
        <path id={`bohr-${id}`} d="M50,9 a41,41 0 1,1 -0.01,0" />
      </defs>
      <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" strokeWidth=".9" />
      <circle cx="50" cy="50" r="34" fill="none" stroke="currentColor" strokeWidth=".9" />
      <text fontFamily="Outfit" fontSize="4.3" fill="currentColor">
        <textPath href={`#bohr-${id}`} textLength="254" lengthAdjust="spacing">
          OMNIA QUAE REALIA VOCAMUS EX REBUS CONSTANT QUAE UT REALIA HABERI NON POSSUNT ·
        </textPath>
      </text>
      <g transform="translate(18 18) scale(.64)">
        <circle cx="50" cy="46" r="20" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="50" cy="72" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
        <line x1="32" y1="78" x2="50" y2="78" stroke="currentColor" strokeWidth="2" />
        <circle cx="64.1" cy="31.9" r="3.4" fill="var(--beam-green)" />
        <circle cx="35.9" cy="60.1" r="3.4" fill="var(--beam-blue)" />
      </g>
    </svg>
  );
}
