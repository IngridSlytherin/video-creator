import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ESTILO_LONGO, Legendas } from "./Legendas";
import { Graficos } from "./Graficos";
import { CORES, FONTE, PropsVideo } from "./tipos";

// Zoom bem lento: o vídeo longo pede ritmo mais calmo que o Short.
const ClipeLento: React.FC<{
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
    : interpolate(frame, [0, frames], sentido > 0 ? [1.0, 1.06] : [1.06, 1.0], {
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

// Cartão que entra no começo de cada capítulo: "#3  O panda".
const CartaoCapitulo: React.FC<{ numero?: number | null; titulo: string }> = ({ numero, titulo }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entrada = spring({ frame, fps, config: { damping: 16 } });
  const saida = interpolate(frame, [fps * 3, fps * 3.5], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div
      style={{
        position: "absolute",
        left: 90,
        top: 90,
        display: "flex",
        alignItems: "center",
        gap: 28,
        opacity: saida,
        transform: `translateX(${(1 - entrada) * -120}px)`,
        fontFamily: FONTE,
      }}
    >
      {numero ? (
        <div
          style={{
            background: CORES.destaque,
            color: CORES.contorno,
            fontSize: 110,
            padding: "0 34px",
            borderRadius: 18,
            transform: "rotate(-3deg)",
            boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
          }}
        >
          #{numero}
        </div>
      ) : null}
      <div
        style={{
          color: CORES.texto,
          fontSize: 84,
          textTransform: "uppercase",
          WebkitTextStroke: `8px ${CORES.contorno}`,
          paintOrder: "stroke fill",
          textShadow: "0 6px 18px rgba(0,0,0,0.5)",
        }}
      >
        {titulo}
      </div>
    </div>
  );
};

export const Longo: React.FC<PropsVideo> = ({
  narracao,
  marca = "",
  musica,
  clipes,
  palavras,
  capitulos = [],
  volumeOriginal = 0,
  semZoom = false,
  semLegendas = false,
  graficos = [],
  idioma = "pt-BR",
}) => {
  const { fps, durationInFrames } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {clipes.map((c, i) => {
        const de = Math.round(c.inicio * fps);
        const ate = i === clipes.length - 1 ? durationInFrames : Math.round((c.inicio + c.duracao) * fps);
        return (
          <Sequence key={`${c.arquivo}-${i}`} from={de} durationInFrames={ate - de} name={`Clipe ${i + 1}`}>
            <ClipeLento
              src={c.arquivo}
              frames={ate - de}
              sentido={i % 2 ? -1 : 1}
              inicioFrames={Math.round((c.inicioNoClipe ?? 0) * fps)}
              volume={volumeOriginal}
              semZoom={semZoom || Boolean(c.animacao)}
            />
          </Sequence>
        );
      })}

      {/* sombra embaixo para a legenda */}
      <AbsoluteFill
        style={{ background: "linear-gradient(180deg, rgba(0,0,0,0) 65%, rgba(0,0,0,0.55) 100%)" }}
      />

      {capitulos
        .filter((c) => c.numero)
        .map((c) => (
          <Sequence key={c.titulo} from={Math.round(c.inicio * fps)} durationInFrames={fps * 4} name={`Capítulo ${c.titulo}`}>
            <CartaoCapitulo numero={c.numero} titulo={c.titulo} />
          </Sequence>
        ))}

      <div
        style={{
          position: "absolute",
          top: 40,
          right: 60,
          fontFamily: FONTE,
          fontSize: 26,
          letterSpacing: 2,
          color: CORES.creme,
          opacity: 0.8,
          textShadow: "0 2px 8px rgba(0,0,0,0.6)",
        }}
      >
        {marca}
      </div>

      <Graficos graficos={graficos} formato="longo" idioma={idioma} />

      {semLegendas ? null : <Legendas palavras={palavras} estilo={ESTILO_LONGO} />}

      {narracao ? <Audio src={staticFile(narracao)} /> : null}
      {musica ? <Audio src={staticFile(musica)} volume={0.06} loop /> : null}
    </AbsoluteFill>
  );
};
