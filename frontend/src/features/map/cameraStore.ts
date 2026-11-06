/** Rotação e inclinação do mapa, para quem quer acompanhar a câmera sem re-renderizar a página. */
export interface Camera {
  /** graus, contínuo (não volta de 180 para -180: a pilha de camadas não dá a volta inteira) */
  bearing: number;
  pitch: number;
}

export class CameraStore {
  private value: Camera = { bearing: 0, pitch: 0 };
  private raw = 0;
  private unwrapped = 0;
  private readonly listeners = new Set<() => void>();

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  get = (): Camera => this.value;

  set(bearing: number, pitch: number): void {
    this.unwrapped += ((bearing - this.raw + 540) % 360) - 180;
    this.raw = bearing;
    const same =
      Math.abs(this.unwrapped - this.value.bearing) < 0.01 && Math.abs(pitch - this.value.pitch) < 0.01;
    if (same) return;
    this.value = { bearing: this.unwrapped, pitch };
    for (const fn of this.listeners) fn();
  }
}
