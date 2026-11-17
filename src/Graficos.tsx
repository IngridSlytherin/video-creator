import React from "react";
import { Easing, interpolate, Sequence, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CORES, FONTE, Grafico } from "./tipos";

type Formato = "short" | "longo";

const formatar = (n: number, idioma: string) =>
  new Intl.NumberFormat(idioma, { maximumFractionDigits: Number.isInteger(n) ? 0 : 1 }).format(n);

// Cartão escuro que entra com um pulinho e some no fim do trecho.
const Cartao: React.FC<{ frames: number; formato: Formato; children: React.ReactNode }> = ({
  frames,
  formato,
  children,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entrada = spring({ frame, fps, config: { damping: 14 } });
  const saida = interpolate(frame, [frames - fps * 0.4, frames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const posicao: React.CSSProperties =
    formato === "short"
      ? { top: 230, left: 70, right: 70, alignItems: "center" }
      : { top: 150, right: 90, width: 720, alignItems: "stretch" };
  return (
    <div
      style={{
        position: "absolute",
        display: "flex",
        flexDirection: "column",
        gap: 14,
        padding: formato === "short" ? "28px 36px" : "24px 32px",
        background: "rgba(17,17,17,0.72)",
        borderRadius: 26,
        boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
        border: `3px solid ${CORES.destaque}`,
        fontFamily: FONTE,
        color: CORES.texto,
        opacity: saida,
        transform: `scale(${0.6 + 0.4 * entrada}) rotate(${(1 - entrada) * -4}deg)`,
        ...posicao,
      }}
    >
      {children}
    </div>
  );
};

const Numero: React.FC<{ g: Grafico; frames: number; formato: Formato; idioma: string }> = ({
  g,
  frames,
  formato,
  idioma,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const de = g.de ?? 0;
  const valor = g.valor ?? 0;
  const atual = interpolate(frame, [fps * 0.2, fps * 1.4], [de, valor], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const mostrado = Number.isInteger(valor) ? Math.round(atual) : Math.round(atual * 10) / 10;
  return (
    <Cartao frames={frames} formato={formato}>
      {g.rotulo ? (
        <div style={{ fontSize: formato === "short" ? 40 : 34, textTransform: "uppercase", letterSpacing: 1.5, opacity: 0.9, textAlign: "center" }}>
          {g.rotulo}
        </div>
      ) : null}
      <div
        style={{
          fontSize: formato === "short" ? 150 : 120,
          lineHeight: 1,
          color: CORES.destaque,
          textAlign: "center",
          WebkitTextStroke: `6px ${CORES.contorno}`,
          paintOrder: "stroke fill",
        }}
      >
        {g.prefixo ?? ""}
        {formatar(mostrado, idioma)}
        <span style={{ fontSize: "0.45em" }}>{g.sufixo ?? ""}</span>
      </div>
    </Cartao>
  );
};

const Comparacao: React.FC<{ g: Grafico; frames: number; formato: Formato; idioma: string }> = ({
  g,
  frames,
  formato,
  idioma,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const itens = (g.itens ?? []).slice(0, 4);
  const maior = Math.max(...itens.map((i) => i.valor), 1);
  const tamanho = formato === "short" ? 40 : 34;
  return (
    <Cartao frames={frames} formato={formato}>
      {g.rotulo ? (
        <div style={{ fontSize: tamanho, textTransform: "uppercase", letterSpacing: 1.5, textAlign: "center" }}>{g.rotulo}</div>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap: 16, width: "100%" }}>
        {itens.map((item, i) => {
          // cada barra cresce depois da anterior
          const p = interpolate(frame, [fps * (0.3 + i * 0.35), fps * (1.1 + i * 0.35)], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.out(Easing.cubic),
          });
          const largura = Math.max(3, (item.valor / maior) * 100) * p;
          return (
            <div key={item.nome} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: tamanho * 0.85 }}>
                <span>{item.nome}</span>
                <span style={{ color: CORES.destaque, opacity: p }}>
                  {formatar(item.valor, idioma)} {g.unidade ?? ""}
                </span>
              </div>
              <div style={{ height: formato === "short" ? 34 : 28, background: "rgba(255,255,255,0.15)", borderRadius: 17 }}>
                <div
                  style={{
                    height: "100%",
                    width: `${largura}%`,
                    background: i === itens.length - 1 ? CORES.destaque : CORES.creme,
                    borderRadius: 17,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Cartao>
  );
};

export const Graficos: React.FC<{ graficos?: Grafico[]; formato: Formato; idioma?: string }> = ({
  graficos = [],
  formato,
  idioma = "pt-BR",
}) => {
  const { fps } = useVideoConfig();
  return (
    <>
      {graficos.map((g, i) => {
        const frames = Math.max(fps, Math.round(g.duracao * fps));
        return (
          <Sequence key={i} from={Math.round(g.inicio * fps)} durationInFrames={frames} name={`Gráfico ${i + 1}`}>
            {g.tipo === "comparacao" ? (
              <Comparacao g={g} frames={frames} formato={formato} idioma={idioma} />
            ) : (
              <Numero g={g} frames={frames} formato={formato} idioma={idioma} />
            )}
          </Sequence>
        );
      })}
    </>
  );
};
