import React from "react";
import { CalculateMetadataFunction, Composition, Still } from "remotion";
import { Corte, exemploCorte, PropsCorte } from "./Corte";
import { Longo } from "./Longo";
import { Short } from "./Short";
import { Thumbnail } from "./Thumbnail";
import { exemploProps, PropsVideo } from "./tipos";

const FPS = 30;

const calcular: CalculateMetadataFunction<PropsVideo> = ({ props }) => ({
  durationInFrames: Math.max(1, Math.ceil(props.duracaoSegundos * FPS)),
});

const calcularCorte: CalculateMetadataFunction<PropsCorte> = ({ props }) => ({
  durationInFrames: Math.max(1, Math.floor(props.duracaoSegundos * FPS)),
});

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Short"
      component={Short}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={150}
      defaultProps={exemploProps}
      calculateMetadata={calcular}
    />
    <Composition
      id="Longo"
      component={Longo}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={150}
      defaultProps={exemploProps}
      calculateMetadata={calcular}
    />
    <Composition
      id="Corte"
      component={Corte}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={150}
      defaultProps={exemploCorte}
      calculateMetadata={calcularCorte}
    />
    <Still id="Thumbnail" component={Thumbnail} width={1280} height={720} defaultProps={exemploProps} />
  </>
);
