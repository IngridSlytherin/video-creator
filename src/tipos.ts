export type Palavra = { texto: string; inicioMs: number; fimMs: number };

export type Clipe = {
  arquivo: string;
  inicio: number; // segundos
  duracao: number; // segundos
  inicioNoClipe?: number; // segundos: de que ponto do arquivo o trecho começa
  autor?: string;
  url?: string;
  animacao?: boolean; // cena feita com Manim: sem zoom (o desenho já está enquadrado)
  transicao?: "wipe" | "deslize" | "iris" | "zoom"; // como este clipe entra (src/Transicao.tsx)
};

// Efeito sonoro (whoosh, pop) num momento do vídeo.
export type Efeito = { arquivo: string; inicio: number; volume: number };

// Animação por cima do vídeo durante um trecho da fala (campo "grafico" no roteiro).
export type Grafico = {
  tipo: "numero" | "comparacao";
  inicio: number; // segundos
  duracao: number; // segundos
  // numero: conta de "de" até "valor"
  valor?: number;
  de?: number;
  prefixo?: string;
  sufixo?: string;
  rotulo?: string;
  // comparacao: barras proporcionais
  unidade?: string;
  itens?: { nome: string; valor: number }[];
};

export type PropsVideo = {
  duracaoSegundos: number;
  narracao: string;
  musica: string | null;
  tituloTela: string;
  marca?: string; // nome do canal (dados/canal.json), aparece no topo do vídeo e na thumbnail
  capa?: string | null; // só existe no vídeo longo
  clipes: Clipe[];
  palavras: Palavra[];
  capitulos?: { titulo: string; inicio: number; numero?: number | null }[];
  // Opções do "Dublar meu vídeo" (vídeo enviado pela pessoa):
  volumeOriginal?: number; // 0 = sem o som original; 0.15 = som original baixinho
  semZoom?: boolean; // não aplica o zoom lento (não corta as bordas)
  semLegendas?: boolean;
  graficos?: Grafico[];
  idioma?: string; // formato dos números (ex.: "pt-BR" usa vírgula decimal)
  efeitos?: Efeito[];
  duracaoTransicao?: number; // segundos
};

export const exemploProps: PropsVideo = {
  duracaoSegundos: 5,
  narracao: "",
  musica: null,
  tituloTela: "SEU CANAL",
  marca: "SEU CANAL",
  clipes: [],
  palavras: [
    { texto: "Gere", inicioMs: 0, fimMs: 600 },
    { texto: "um", inicioMs: 600, fimMs: 900 },
    { texto: "roteiro", inicioMs: 900, fimMs: 1500 },
    { texto: "primeiro", inicioMs: 1500, fimMs: 2200 },
  ],
};

// Identidade visual: tons naturais, sem neon, com cara de edição feita à mão.
export const CORES = {
  destaque: "#FFD23F", // amarelo quente para a palavra falada
  texto: "#FFFFFF",
  contorno: "#111111",
  marca: "#2F5D50", // verde musgo
  creme: "#F4EBD9",
};

export const FONTE = "'Arial Black', 'Segoe UI Black', 'Helvetica Neue', sans-serif";
