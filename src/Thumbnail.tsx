import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { CORES, FONTE, PropsVideo } from "./tipos";

// Thumbnail do vídeo longo (1280x720): foto à direita, texto grande à esquerda.
export const Thumbnail: React.FC<PropsVideo> = ({ capa, tituloTela, marca = "" }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: CORES.marca }}>
      {capa ? (
        <Img src={staticFile(capa)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : null}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0.45) 45%, rgba(0,0,0,0) 70%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 60,
          top: 0,
          bottom: 0,
          width: 640,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          fontFamily: FONTE,
          fontSize: 104,
          lineHeight: 1.0,
          textTransform: "uppercase",
          color: CORES.texto,
          WebkitTextStroke: `10px ${CORES.contorno}`,
          paintOrder: "stroke fill",
          transform: "rotate(-2deg)",
        }}
      >
        {tituloTela.split(" ").map((p, i, arr) => (
          <span key={i} style={{ color: i === arr.length - 1 ? CORES.destaque : CORES.texto }}>
            {p}
          </span>
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          left: 64,
          bottom: 40,
          fontFamily: FONTE,
          fontSize: 28,
          color: CORES.creme,
          letterSpacing: 2,
        }}
      >
        {marca}
      </div>
    </AbsoluteFill>
  );
};
