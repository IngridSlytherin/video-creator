import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Clipe } from "./tipos";

const SUAVE = Easing.bezier(0.65, 0, 0.35, 1);

// O clipe novo entra por cima do anterior nos primeiros `frames` quadros:
// wipe (cortina da direita), deslize (empurra de lado), íris (círculo que abre)
// e zoom (vem de perto, desfocado, e assenta).
export const Entrada: React.FC<{
  tipo?: Clipe["transicao"];
  frames: number;
  children: React.ReactNode;
}> = ({ tipo, frames, children }) => {
  const frame = useCurrentFrame();
  if (!tipo || frames <= 0 || frame >= frames) {
    return <AbsoluteFill>{children}</AbsoluteFill>;
  }
  const p = interpolate(frame, [0, frames], [0, 1], { easing: SUAVE, extrapolateRight: "clamp" });
  let estilo: React.CSSProperties = {};
  if (tipo === "wipe") {
    estilo = { clipPath: `inset(0 0 0 ${(1 - p) * 100}%)` };
  } else if (tipo === "deslize") {
    estilo = { transform: `translateX(${(1 - p) * 100}%)`, boxShadow: "-30px 0 60px rgba(0,0,0,0.5)" };
  } else if (tipo === "iris") {
    estilo = { clipPath: `circle(${p * 76}% at 50% 50%)` };
  } else if (tipo === "zoom") {
    estilo = {
      transform: `scale(${1.5 - 0.5 * p})`,
      filter: `blur(${(1 - p) * 18}px)`,
      opacity: Math.min(1, p * 2.5),
    };
  }
  return <AbsoluteFill style={estilo}>{children}</AbsoluteFill>;
};
