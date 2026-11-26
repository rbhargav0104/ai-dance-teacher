/** Stage options shared by the Learn Mode shell and the (lazily loaded) three.js stage. */

export type CameraView = "front" | "three-quarter" | "side";

export const CAMERA_VIEWS: { id: CameraView; label: string }[] = [
  { id: "front", label: "Front" },
  { id: "three-quarter", label: "3/4" },
  { id: "side", label: "Side" },
];

/** WebGL availability; the stage falls back to the 2-D skeleton (and says so) without it. */
export function hasWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}
