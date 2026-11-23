import React, { useMemo } from "react";
import { Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { Efeito, Palavra } from "./tipos";

// Música que abaixa enquanto a voz fala e sobe nas pausas (e some no fim).
export const MusicaDeFundo: React.FC<{
  src: string;
  palavras: Palavra[];
  baixo: number; // volume com a voz falando
  alto: number; // volume nas pausas
}> = ({ src, palavras, baixo, alto }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const volumes = useMemo(() => {
    // quadros com fala (pausas menores que 0,7 s contam como fala: evita a música "bombear")
    const fala = new Uint8Array(durationInFrames);
    let fimAnterior = -Infinity;
    for (const w of palavras) {
      const de = w.inicioMs / 1000 - fimAnterior < 0.7 ? fimAnterior : w.inicioMs / 1000 - 0.15;
      const ate = w.fimMs / 1000 + 0.25;
      for (let f = Math.max(0, Math.floor(de * fps)); f < Math.min(durationInFrames, Math.ceil(ate * fps)); f++) {
        fala[f] = 1;
      }
      fimAnterior = w.fimMs / 1000;
    }
    // desce rápido (0,25 s) e sobe devagar (0,8 s)
    const descer = (alto - baixo) / (0.25 * fps);
    const subir = (alto - baixo) / (0.8 * fps);
    const v = new Float32Array(durationInFrames);
    let atual = fala[0] ? baixo : alto;
    for (let f = 0; f < durationInFrames; f++) {
      const alvo = fala[f] ? baixo : alto;
      atual = alvo < atual ? Math.max(alvo, atual - descer) : Math.min(alvo, atual + subir);
      // some nos últimos 1,5 s
      const fim = Math.min(1, (durationInFrames - f) / (1.5 * fps));
      v[f] = atual * fim;
    }
    return v;
  }, [palavras, baixo, alto, fps, durationInFrames]);

  return <Audio src={staticFile(src)} loop volume={(f) => volumes[Math.min(f, volumes.length - 1)] ?? baixo} />;
};

export const Efeitos: React.FC<{ efeitos: Efeito[] }> = ({ efeitos }) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {efeitos.map((e, i) => (
        <Sequence key={`${e.arquivo}-${i}`} from={Math.round(e.inicio * fps)} durationInFrames={fps * 2} name={`Efeito ${i + 1}`}>
          <Audio src={staticFile(e.arquivo)} volume={e.volume} />
        </Sequence>
      ))}
    </>
  );
};
