# Guia de uso — gerador de vídeos

Instalação e visão geral: veja o [README](README.md). Este guia detalha cada parte.

## Painel (interface no navegador)
Dê dois cliques em **`Abrir painel.bat`**. Abre `http://localhost:8765` no navegador; a janela preta
precisa ficar aberta enquanto você usa (fechar = desligar o painel).

- **Primeira vez**: o painel pede o **nome do canal** e a **categoria**. Isso define a marca nos
  vídeos e o assunto do radar, das ideias e dos roteiros. Para trocar depois, clique em **⚙ Canal**.
- **Novo vídeo**: escreva o tema e clique em **Pedir ideias**. O Claude sugere 3 ângulos (uns 30 s);
  clique em **Escrever este roteiro** (1–3 min, ele confere os fatos na internet). Leia a narração na
  prévia e clique em **Gerar vídeo agora**. Usa o Claude Code da sua conta (modelo Sonnet); para trocar,
  coloque `CLAUDE_MODELO=opus` no `.env`.
- **Dublar meu vídeo**: envie um vídeo seu (arraste ou clique), cole o texto que a voz vai falar
  (cada linha = um trecho) e clique em **Dublar vídeo**. Vertical vira Short; horizontal, vídeo longo.
  Opções: som original (tirar / baixinho / normal), terminar quando o vídeo ou a narração acabar,
  legenda e música. Se a narração for maior que o vídeo, o vídeo repete. O vídeo enviado é apagado
  depois de pronto, para não ocupar espaço.
- **Vídeos prontos**: assiste, baixa, copia título/descrição/tags com um clique, baixa a thumbnail,
  vê o melhor horário e marca "Já publiquei".
- **Roteiros**: gera o vídeo de qualquer roteiro com um botão e mostra o andamento.
  "Só textos" refaz só o `publicacao.txt`.
- **Radar**: roda o radar e mostra os temas em alta em cartões. **Quero esse tema** leva o tema
  (e os sinais do radar) para a aba Novo vídeo e já pede as ideias.
- Atalhos: `http://localhost:8765/#radar` (ou `#novo`, `#dublar`, `#roteiros`) abre direto na aba;
  `#configurar` abre a configuração do canal.

Depois de atualizar o projeto, feche a janela preta e abra o `Abrir painel.bat` de novo.

## Radar de temas em alta
No Claude Code, digite **`/radar`**: ele confere o que está em alta (Wikipedia, Google Notícias,
Google Trends e vídeos da semana no YouTube) e sugere 5 temas com título e gancho.

Só a coleta, sem o Claude:

```bash
python -I pipeline/radar.py
```

- O relatório fica em `dados/radar/AAAA-MM-DD.md`.
- A lista de temas acompanhados fica em `dados/temas/<categoria>.json`. Para "Animais e natureza"
  ela já vem pronta (133 animais). Para outras categorias, o painel pede ao Claude Code para criar
  (2–4 min). Sem a lista, o radar mostra as notícias e vídeos da semana, só sem pontuar temas.
- As buscas de notícias e do YouTube ficam em `dados/canal.json`, em `radar`.

## Gerar um vídeo pelo terminal
1. Crie um roteiro em `roteiros/` (copie `exemplos/short-exemplo.json`).
   - `animal`: o **assunto principal em inglês** (mesmo que não seja um animal). É o que filtra os
     clipes do Pexels: a palavra precisa aparecer no endereço do vídeo no Pexels.
   - `segmentos`: cada trecho da fala + palavras de busca em inglês.
   - `duracao`: `curto` (30–45 s, um fato só), `padrao` (50–65 s) ou `longo` (75–120 s).
     O gerador avisa se a narração ficar fora da faixa.
2. Rode:

```bash
python -I pipeline/gerar_video.py roteiros/meu-video.json
```

3. O resultado fica em `saida/<nome-do-video>/`:
   - `video.mp4` — o vídeo pronto
   - `thumbnail.png` — a capa (só no vídeo longo; no Short o YouTube não deixa escolher)
   - `publicacao.txt` — título, descrição, tags, horário sugerido e créditos

## Vídeo longo (horizontal) + Shorts
- Use `"formato": "longo"` e divida o roteiro em `capitulos` (modelo: `exemplos/longo-exemplo.json`).
- Capítulos com `animal` (assunto) entram na contagem regressiva (#7 ... #1) com cartão na tela.
- O primeiro trecho de cada capítulo deve ser só a apresentação ("Número três: o panda.").
  Ele é tirado quando o capítulo vira Short.
- Capítulos com o bloco `short` (título, descrição, hashtags) viram Shorts verticais
  automaticamente, cada um na sua pasta `saida/<slug>-short-<assunto>/`.
- A descrição do longo já sai com os capítulos (00:00 Introdução, ...).
- Opções: `--sem-shorts` (só o longo) e `--manter-clipes` (não apaga os clipes baixados,
  útil para abrir no Remotion Studio).

## Vídeos de sons relaxantes (10 min a horas)
Chuva, vento, pássaros... com imagens de natureza do Pexels. O som é **sintetizado por computador**
(`pipeline/sons.py`), então não tem direitos autorais de terceiros.

```bash
python -I pipeline/sons.py amostras
python -I pipeline/relaxante.py relax/chuva-vento-passaros-12min.json
```

- O primeiro gera amostras de 30 s de cada som em `saida/amostras-sons/` para você ouvir.
- O segundo gera o vídeo (12 min levam uns 20 minutos). Cada vídeo é um arquivo em `relax/`:
  partes em ordem, com título, som, minutos, volume e o que buscar no Pexels.

## Descrição e hashtags
- No roteiro, `publicacao.hashtags` traz as hashtags **do tema**.
- `dados/canal.json` guarda o que se repete em todo vídeo: hashtags do início e do fim,
  a pergunta para os comentários, a chamada para se inscrever, a frase do fim do Short e o aviso de IA.
  Pode editar à mão.
- Para refazer só o `publicacao.txt` (sem renderizar o vídeo de novo):

```bash
python -I pipeline/gerar_video.py roteiros/meu-video.json --so-publicacao
```

## O que funciona no seu canal (opcional, recomendado)
Copie `dados/aprendizados.exemplo.md` para `dados/aprendizados.md` e anote os números do seu
YouTube Studio (retenção, horários do público, o que deu certo). O Claude lê esse arquivo antes
de sugerir ideias e escrever roteiros.

## Ver/ajustar no Remotion Studio
```bash
npx remotion studio
```

## Configurações
- `.env`: chave do Pexels, voz (`VOZ`) e velocidade da fala (`VELOCIDADE_VOZ`).
  Outras vozes em português: `pt-BR-AntonioNeural` (masculina), `pt-BR-ThalitaMultilingualNeural`.
- Música de fundo: coloque arquivos `.mp3` em `public/musica/` (ex.: da Biblioteca de áudio do
  YouTube Studio). O gerador escolhe uma automaticamente, em volume baixo.
- Cores e fonte: `src/tipos.ts`.

## Arquivos
- `historico.json` — lista dos vídeos já feitos (para não repetir temas).
- `public/projetos/` — narração e configurações de cada vídeo; os clipes baixados são apagados
  automaticamente depois de cada vídeo.
