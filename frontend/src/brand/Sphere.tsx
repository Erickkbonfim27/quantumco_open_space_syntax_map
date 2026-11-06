import { useEffect, useRef } from "react";

import { cssToken, useTheme } from "../lib/theme";

/**
 * Esfera de partículas da marca (Quantumco Brand): síncrotron com os feixes verde e azul.
 * Respeita prefers-reduced-motion (desenha um quadro só). As partículas neutras usam a tinta do
 * tema (--fg-rgb): claras no escuro, grafite no claro; os feixes ficam verde e azul.
 */
const POINTS = (() => {
  const n = 1600;
  const golden = Math.PI * (3 - Math.sqrt(5));
  return Array.from({ length: n }, (_, i) => {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = golden * i;
    return [Math.cos(th) * r, y, Math.sin(th) * r] as const;
  });
})();

function draw(canvas: HTMLCanvasElement, t: number, ink: string) {
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth * dpr;
  const H = canvas.clientHeight * dpr;
  if (!W) return;
  if (canvas.width !== W) {
    canvas.width = W;
    canvas.height = H;
  }
  const g = canvas.getContext("2d");
  if (!g) return;
  g.clearRect(0, 0, W, H);
  const cx = W / 2;
  const cy = H / 2;
  const R = W * 0.34;
  const cs = Math.cos(t);
  const sn = Math.sin(t);
  const st = Math.sin(0.42);
  const ct = Math.cos(0.42);
  const ring = (front: boolean) => {
    for (let i = 0; i < 220; i++) {
      const a = (i / 220) * Math.PI * 2;
      const x = Math.cos(a) * 1.32;
      const zz = Math.sin(a) * 1.32;
      const y2 = -zz * st;
      if (zz * ct > 0 !== front) continue;
      g.fillStyle = front ? "rgba(43,212,107,.85)" : "rgba(43,212,107,.25)";
      g.fillRect(cx + x * R, cy + y2 * R, 1.6 * dpr, 1.6 * dpr);
    }
    for (const [a, color] of [
      [t * 3, "#2BD46B"],
      [-t * 3 + Math.PI, "#3B8CFF"],
    ] as const) {
      const x = Math.cos(a) * 1.32;
      const zz = Math.sin(a) * 1.32;
      if (zz * ct > 0 !== front) continue;
      g.fillStyle = color;
      g.beginPath();
      g.arc(cx + x * R, cy - zz * st * R, 4 * dpr, 0, 7);
      g.fill();
    }
  };
  ring(false);
  for (const [px, py, pz] of POINTS) {
    const x = px * cs - pz * sn;
    const z = px * sn + pz * cs;
    const d = (z + 1) / 2;
    const rr = Math.hypot(x, py);
    g.fillStyle =
      rr > 0.9 && z > -0.2
        ? x < -0.1
          ? `rgba(59,140,255,${0.5 + d * 0.5})`
          : py < 0.2
            ? `rgba(43,212,107,${0.5 + d * 0.5})`
            : `rgba(${ink},${0.15 + d * 0.6})`
        : `rgba(${ink},${0.06 + d * 0.7})`;
    const s = (0.7 + d * 1.1) * dpr;
    g.fillRect(cx + x * R, cy + py * R, s, s);
  }
  ring(true);
}

export function Sphere({ className, speed = 0.0025 }: { className?: string; speed?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const angle = useRef(0.6); // continua girando de onde parou quando o tema muda
  const { theme } = useTheme();
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // a tinta é lida já no quadro: ao trocar o tema, o <html data-theme> só muda no efeito do
    // ThemeProvider, que roda depois deste
    let ink = "";
    const paint = () => {
      ink ||= cssToken("--fg-rgb", "244, 246, 245");
      draw(canvas, angle.current, ink);
    };
    let frame = 0;
    const loop = () => {
      angle.current += speed;
      paint();
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(reduced ? paint : loop);
    return () => cancelAnimationFrame(frame);
  }, [speed, theme]);
  return <canvas ref={ref} className={className} aria-hidden="true" />;
}
