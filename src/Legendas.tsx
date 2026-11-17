import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CORES, FONTE, Palavra } from "./tipos";

// Agrupa as palavras em blocos curtos (estilo legenda de Short),
// quebrando também quando há pontuação ou pausa na fala.
function agrupar(palavras: Palavra[], PALAVRAS_POR_BLOCO: number): Palavra[][] {
  const blocos: Palavra[][] = [];
  let atual: Palavra[] = [];
  palavras.forEach((p, i) => {
    atual.push(p);
    const proxima = palavras[i + 1];
    const pausa = proxima ? proxima.inicioMs - p.fimMs > 250 : true;
    if (atual.length >= PALAVRAS_POR_BLOCO || pausa || /[.,!?:;]$/.test(p.texto)) {
      blocos.push(atual);
      atual = [];
    }
  });
  if (atual.length) blocos.push(atual);
  return blocos;
}

type Estilo = {
  palavrasPorBloco: number;
  tamanho: number;
  contorno: number;
  posicao: React.CSSProperties;
};

const ESTILO_SHORT: Estilo = {
  palavrasPorBloco: 3,
  tamanho: 92,
  contorno: 10,
  posicao: { top: "42%", left: 60, right: 60 },
};

export const ESTILO_LONGO: Estilo = {
  palavrasPorBloco: 6,
  tamanho: 58,
  contorno: 7,
  posicao: { bottom: 70, left: 200, right: 200 },
};

export const Legendas: React.FC<{ palavras: Palavra[]; estilo?: Estilo }> = ({
  palavras,
  estilo = ESTILO_SHORT,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;

  const blocos = React.useMemo(
    () => agrupar(palavras, estilo.palavrasPorBloco),
    [palavras, estilo.palavrasPorBloco],
  );
  const bloco = blocos.find((b, i) => {
    const fim = blocos[i + 1] ? blocos[i + 1][0].inicioMs : b[b.length - 1].fimMs + 400;
    return ms >= b[0].inicioMs && ms < fim;
  });
  if (!bloco) return null;

  const entrada = spring({
    frame: frame - Math.round((bloco[0].inicioMs / 1000) * fps),
    fps,
    config: { damping: 14, stiffness: 180 },
    durationInFrames: 8,
  });

  return (
    <div
      style={{
        position: "absolute",
        ...estilo.posicao,
        textAlign: "center",
        fontFamily: FONTE,
        fontSize: estilo.tamanho,
        lineHeight: 1.1,
        textTransform: "uppercase",
        transform: `scale(${0.85 + 0.15 * entrada})`,
      }}
    >
      {bloco.map((p, i) => {
        const falando = ms >= p.inicioMs && ms < p.fimMs + 80;
        return (
          <span
            key={i}
            style={{
              color: falando ? CORES.destaque : CORES.texto,
              WebkitTextStroke: `${estilo.contorno}px ${CORES.contorno}`,
              paintOrder: "stroke fill",
              textShadow: "0 6px 18px rgba(0,0,0,0.55)",
              marginRight: estilo.tamanho * 0.24,
              display: "inline-block",
            }}
          >
            {p.texto}
          </span>
        );
      })}
    </div>
  );
};
