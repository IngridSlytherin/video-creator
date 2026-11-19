import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Legendas } from "./Legendas";
import { CORES, FONTE, Palavra } from "./tipos";

// Corte de um vídeo longo da pessoa (aba Cortes). O arquivo já chega em 1080x1920 (o vídeo deitado
// inteiro no meio e ele mesmo desfocado no fundo, feito pelo ffmpeg); aqui entram título e legenda.
export type PropsCorte = {
  duracaoSegundos: number;
  video: string;
  vertical?: boolean; // o vídeo original já é em pé: ocupa a tela toda
  tituloTela?: string;
  marca?: string;
  palavras: Palavra[];
  semLegendas?: boolean;
};

export const exemploCorte: PropsCorte = {
  duracaoSegundos: 5,
  video: "",
  tituloTela: "O POLVO TEM 3 CORAÇÕES?",
  marca: "SEU CANAL",
  palavras: [],
};

const LEGENDA_CORTE = {
  palavrasPorBloco: 3,
  tamanho: 84,
  contorno: 9,
  posicao: { top: "70%", left: 60, right: 60 } as React.CSSProperties,
};

export const Corte: React.FC<PropsCorte> = ({ video, vertical, tituloTela, marca, palavras, semLegendas }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  if (!video) return <AbsoluteFill style={{ backgroundColor: "black" }} />;
  const src = staticFile(video);

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {/* o fundo desfocado já vem pronto no arquivo (pipeline/cortes.py) */}
      <OffthreadVideo src={src} style={{ width: "100%", height: "100%", objectFit: "cover" }} />

      {marca ? (
        <div
          style={{
            position: "absolute", top: 90, width: "100%", textAlign: "center", fontFamily: FONTE,
            fontSize: 34, letterSpacing: 2, color: CORES.creme, opacity: 0.85,
            textShadow: "0 2px 8px rgba(0,0,0,0.6)",
          }}
        >
          {marca}
        </div>
      ) : null}

      {tituloTela ? (
        <div
          style={{
            position: "absolute", top: vertical ? 170 : 250, left: 70, right: 70, textAlign: "center",
            fontFamily: FONTE, fontSize: 76, lineHeight: 1.08, textTransform: "uppercase",
            color: CORES.destaque, WebkitTextStroke: `8px ${CORES.contorno}`, paintOrder: "stroke fill",
            textShadow: "0 6px 18px rgba(0,0,0,0.55)",
          }}
        >
          {tituloTela}
        </div>
      ) : null}

      {semLegendas || !palavras.length ? null : <Legendas palavras={palavras} estilo={LEGENDA_CORTE} />}

      <div
        style={{
          position: "absolute", bottom: 0, left: 0, height: 10,
          width: `${(frame / durationInFrames) * 100}%`, backgroundColor: CORES.destaque,
        }}
      />
    </AbsoluteFill>
  );
};
