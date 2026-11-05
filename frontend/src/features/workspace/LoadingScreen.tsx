import { Sphere } from "../../brand/Sphere";

export function LoadingScreen({ name, progress, step }: { name: string; progress: number; step: string }) {
  return (
    <section className="loading-screen" aria-live="polite">
      <Sphere className="loading-sphere" speed={0.012} />
      <div className="loading-info">
        <span className="loading-name">{name}</span>
        <div className="progress" aria-hidden="true">
          <div className="progress-fill" style={{ width: `${Math.round(progress)}%` }} />
        </div>
        <span className="mono loading-step">{step}</span>
      </div>
    </section>
  );
}
