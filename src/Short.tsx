import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Legendas } from "./Legendas";
import { CORES, FONTE, PropsVideo } from "./tipos";

// Clipe com leve zoom, para não ficar parado (efeito "Ken Burns").
const ClipeComZoom: React.FC<{
  src: string;
  frames: number;
  sentido: number;
  inicioFrames: number;
  volume?: number;
  semZoom?: boolean;
}> = ({ src, frames, sentido, inicioFrames, volume = 0, semZoom = false }) => {
  const frame = useCurrentFrame();
  const escala = semZoom
    ? 1
    : interpolate(frame, [0, frames], sentido > 0 ? [1.05, 1.15] : [1.15, 1.05], {
        extrapolateRight: "clamp",
      });
  return (
    <AbsoluteFill style={{ transform: `scale(${escala})` }}>
      <OffthreadVideo
        src={staticFile(src)}
        muted={!volume}
        volume={volume}
        startFrom={inicioFrames}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

export const Short: React.FC<PropsVideo> = ({
  narracao,
  marca = "",
  musica,
  clipes,
  palavras,
  volumeOriginal = 0,
  semZoom = false,
  semLegendas = false,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {clipes.map((c, i) => {
        const de = Math.round(c.inicio * fps);
        // o último clipe vai até o fim do vídeo
        const ate =
          i === clipes.length - 1 ? durationInFrames : Math.round((c.inicio + c.duracao) * fps);
        return (
          <Sequence key={`${c.arquivo}-${i}`} from={de} durationInFrames={ate - de} name={`Clipe ${i + 1}`}>
            <ClipeComZoom
              src={c.arquivo}
              frames={ate - de}
              sentido={i % 2 ? -1 : 1}
              inicioFrames={Math.round((c.inicioNoClipe ?? 0) * fps)}
              volume={volumeOriginal}
              semZoom={semZoom}
            />
          </Sequence>
        );
      })}

      {/* escurece um pouco o centro para a legenda ler bem */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 35%, rgba(0,0,0,0.35) 50%, rgba(0,0,0,0) 70%)",
        }}
      />

      {/* marca discreta no topo */}
      <div
        style={{
          position: "absolute",
          top: 90,
          width: "100%",
          textAlign: "center",
          fontFamily: FONTE,
          fontSize: 34,
          letterSpacing: 2,
          color: CORES.creme,
          opacity: 0.85,
          textShadow: "0 2px 8px rgba(0,0,0,0.6)",
        }}
      >
        {marca}
      </div>

      {semLegendas ? null : <Legendas palavras={palavras} />}

      {/* barra de progresso fina, ajuda a pessoa a ficar até o fim */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          height: 10,
          width: `${(frame / durationInFrames) * 100}%`,
          backgroundColor: CORES.destaque,
        }}
      />

      {narracao ? <Audio src={staticFile(narracao)} /> : null}
      {musica ? <Audio src={staticFile(musica)} volume={0.08} loop /> : null}
    </AbsoluteFill>
  );
};
