# video-creator

🇺🇸 [English](README.md) · 🇧🇷 **Português**

Gerador **gratuito** de vídeos para YouTube, feito para rodar no seu computador com o
[Claude Code](https://claude.com/claude-code). Você informa o **nome do seu canal**, a **categoria**
(animais, história, ciência, culinária...) e a **língua dos vídeos** (português, inglês ou espanhol). O sistema acha temas em alta, escreve o roteiro, grava a
narração com voz neural, busca clipes no Pexels, monta o vídeo com legendas e entrega tudo pronto
para publicar: vídeo, título, descrição, tags, thumbnail e o melhor horário de postar.

- **Shorts** verticais (30 s a 2 min) e **vídeos longos** horizontais, que viram vários Shorts automaticamente
- **Radar de temas em alta**: Wikipedia, Google Notícias, Google Trends e YouTube, mais os **vídeos que estouraram**: os do seu nicho que fizeram 3× ou mais o normal do próprio canal
- **Ideias e roteiros pelo painel**: o Claude sugere ângulos, confere os fatos e escreve o roteiro
- **Legendas e outras línguas**: legenda `.srt`, título e descrição traduzidos e **áudio dublado** (inglês/espanhol) para o recurso de várias faixas de áudio do YouTube
- **Já tenho o roteiro**: cole o seu texto, escolha Short ou vídeo longo e a voz, e o vídeo sai com as suas palavras
- **Animações automáticas (Manim)**: onde o texto tem tamanhos, números, datas ou porcentagens, a IA pode trocar os clipes por uma cena animada (barras, medidor, linha do tempo); também há número contando por cima dos clipes
- **Conferência das imagens**: antes de montar, o Claude olha um quadro de cada clipe e troca os ruins (telão, brinquedo, bicho errado)
- **Resultados**: envie a exportação do YouTube Studio e veja se os vídeos do app seguram mais o público do que os antigos
- **Instalação de dois cliques** (`Instalar.bat`) e chave do Pexels colada no próprio painel
- **Voz reserva offline**: se a voz da Microsoft cair, o vídeo sai com uma voz neural que roda no seu computador
- **Cortes dos seus vídeos longos**: envie um vídeo longo seu; o app transcreve a fala no seu computador (Whisper) e o Claude escolhe os 3 a 5 melhores momentos, que viram Shorts verticais com título e legenda
- **Dublar o seu próprio vídeo**: cole um texto e ele ganha narração e legenda
- **Vídeos de sons relaxantes** (chuva, vento, pássaros) de 10 minutos a horas, com som sintetizado
- Vídeos em **português, inglês ou espanhol**: voz, legenda, roteiro, descrição e radar do país mudam juntos
- Tudo numa interface no navegador; você só publica no YouTube

![Painel: vídeos prontos](docs/prints/videos.png)

## Novidades

**1.17 — Acabamento de edição e radar mais esperto:** transições entre as cenas, efeitos sonoros
(whoosh e pop, feitos por código) e música que abaixa quando a voz fala. No radar, os **vídeos que
estouraram**: os do seu nicho que fizeram 3× ou mais o normal do próprio canal.

**1.16 — Mais fácil e mais confiável:** instalação com dois cliques (`Instalar.bat`), chave do Pexels
pelo painel, voz reserva sem internet, legenda dos cortes revisada pelo Claude e render mais rápido.

**1.15 — Aba ✂️ Cortes:** envie um vídeo longo seu e receba Shorts prontos. O app transcreve a fala no
seu computador (Whisper, grátis) e o Claude escolhe de 3 a 5 trechos que funcionam sozinhos, com título,
frase na tela, descrição e hashtags. Confira cada um (▶ ver trecho), ajuste início e fim e crie os
Shorts: o vídeo deitado fica no meio, sobre uma cópia desfocada dele mesmo, com o título em cima e a
legenda animada embaixo.

![Aba Cortes](docs/prints/cortes.png)

**1.14**

- **📋 Já tenho o roteiro**: na aba Novo vídeo, cole um texto pronto, escolha **Short** (em pé) ou
  **vídeo longo** (deitado) e a **voz** (Francisca, Antônio ou Thalita, com ▶ ouvir) e clique em
  **Criar vídeo**. As suas palavras ficam exatamente como estão.
- **✨ Animações automáticas**: a IA lê o texto e decide sozinha se algum trecho fica melhor como
  desenho animado: comparação de tamanhos, medidor de velocidade, linha do tempo ou porcentagem. Texto
  sem dados = vídeo só com clipes. Dá para desligar.
- **Narração mais confiável**: o app percebe quando o serviço de voz devolve uma frase cortada e grava
  de novo.

![Animações automáticas no vídeo](docs/prints/animacoes.png)

## Prints

| Novo vídeo: ideias do Claude | Novo vídeo: já tenho o roteiro |
|---|---|
| ![Novo vídeo](docs/prints/novo.png) | ![Já tenho o roteiro](docs/prints/pronto.png) |

| Radar de temas em alta | Roteiros: gerar com um clique |
|---|---|
| ![Radar](docs/prints/radar.png) | ![Roteiros](docs/prints/roteiros.png) |

| Dublar o seu vídeo | Primeira vez: configure o seu canal |
|---|---|
| ![Dublar](docs/prints/dublar.png) | ![Configurar canal](docs/prints/configurar.png) |

| Resultados: os vídeos novos estão funcionando? | |
|---|---|
| ![Resultados](docs/prints/resultados.png) | |

## Instalação (Windows)

### Jeito mais fácil: Instalar.bat (sem digitar comandos)

1. Nesta página do GitHub, clique no botão verde **Code** › **Download ZIP**.
2. Clique com o botão direito no arquivo baixado › **Extrair tudo**.
3. Abra a pasta e dê dois cliques em **`Instalar.bat`**. Se aparecer "O Windows protegeu o
   computador", clique em **Mais informações** › **Executar assim mesmo**.
4. Espere (na primeira vez, uns 10 a 20 minutos). Se o Windows pedir permissão para instalar algum
   programa, clique em **Sim**. No fim, o painel abre sozinho.
5. No painel, digite o nome do canal e cole a **chave grátis do Pexels** (o painel mostra o passo a passo).

Pronto. Daí em diante, abra o app com dois cliques em **`Abrir painel.bat`**. Para ter ideias,
roteiros e cortes, instale também o [Claude Code](https://claude.com/claude-code).

### Instalação manual (para quem prefere o terminal)

### 1. Programas necessários (todos gratuitos)

| Programa | Para quê | Como instalar |
|---|---|---|
| [Node.js](https://nodejs.org) 18 ou mais novo | Remotion (montagem do vídeo) | `winget install OpenJS.NodeJS.LTS` |
| [Python](https://www.python.org) 3.11 ou mais novo | Narração, radar, painel | `winget install Python.Python.3.13` |
| [ffmpeg](https://ffmpeg.org) | Áudio e vídeo | `winget install Gyan.FFmpeg` |
| [Git](https://git-scm.com) | Baixar o projeto | `winget install Git.Git` |
| [Claude Code](https://claude.com/claude-code) | Ideias, roteiros e o comando `/radar` | Opcional, mas recomendado |

Depois de instalar, feche e abra o terminal de novo para os comandos funcionarem.

### 2. Baixar o projeto e instalar as dependências

```bash
git clone https://github.com/IngridSlytherin/video-creator.git
```

```bash
cd video-creator
```

```bash
npm install
```

```bash
python -m pip install -r requirements.txt
```

### 3. Chave gratuita do Pexels (imagens)

1. Crie uma conta em [pexels.com/api](https://www.pexels.com/api/) e copie a sua chave.
2. Copie o arquivo `.env.exemplo` com o nome `.env` e cole a chave em `PEXELS_API_KEY=`.

```bash
copy .env.exemplo .env
```

Opcional: uma [chave grátis do Pixabay](https://pixabay.com/api/docs/) em `PIXABAY_API_KEY=` acrescenta
o Pixabay como segunda fonte de vídeos (mais opções quando o Pexels tem pouco material de um assunto).

### 4. Música de fundo (opcional)

Coloque arquivos `.mp3` de música **instrumental** em `public/musica/`. Uma boa fonte é o
YouTube Studio > Biblioteca de áudio, que tem músicas que você pode usar nos seus vídeos.
Sem música, o vídeo sai só com a narração. A música abaixa sozinha enquanto a voz fala e sobe nas pausas.

### 5. Skills do Remotion para o Claude Code (opcional)

Ensinam o Claude a mexer no visual dos vídeos (efeitos, legendas, mapas):

```bash
npx skills add remotion-dev/skills
```

## Como usar

### Abrir o painel

Dê dois cliques em **`Abrir painel.bat`**. O painel abre no navegador em `http://localhost:8765`.
A janela preta precisa ficar aberta enquanto você usa; fechar a janela desliga o painel.

**Na primeira vez**, o painel pede o **nome do seu canal**, a **categoria** e a **língua dos vídeos**.
É isso que faz o radar, as ideias e os roteiros seguirem o assunto do *seu* canal, a narração sair na
língua certa e o nome do canal aparecer nos vídeos. Para
categorias que não são "Animais e natureza", o Claude Code monta a lista de temas do radar (2 a 4 minutos).
Para mudar depois, clique em **⚙ Canal**.

### O caminho de um vídeo

1. **Radar**: clique em *Rodar radar agora* para ver os temas em alta. Em um tema que agradar,
   clique em **Quero esse tema**.
2. **Novo vídeo**: o Claude sugere 3 ângulos (título, gancho e por que deve funcionar).
   Clique em **Escrever este roteiro**. Ele confere os fatos na internet e salva o roteiro.
3. Leia a narração na prévia e clique em **Gerar vídeo agora**. Um Short leva uns 3 minutos;
   um vídeo longo com Shorts, uns 15.
4. **Vídeos prontos**: assista, copie título, descrição e tags com um clique, baixe a thumbnail
   e veja o melhor horário para postar. Publique no YouTube Studio e marque **Já publiquei**.

Também dá para escrever o tema direto na aba **Novo vídeo**, sem passar pelo radar.

**Já tem o roteiro?** Em **Novo vídeo**, escolha **📋 Já tenho o roteiro**, cole o texto, escolha o
tamanho (**Short**, em pé, ou **vídeo longo**, deitado) e a **voz** (clique em ▶ ouvir para escutar
cada uma) e clique em **Criar vídeo**. As suas palavras ficam como estão: o app só separa em cenas,
escolhe as imagens, cria título, descrição e hashtags e monta o vídeo. Se algum fato parecer errado,
ele avisa, sem mudar o seu texto.

**Animações automáticas (Manim):** quando o roteiro fala de tamanhos, números, datas ou porcentagens,
a IA pode transformar aquele trecho numa cena animada (comparação com barras, medidor, linha do tempo
ou quadradinhos de porcentagem), no tempo exato da narração. Ela só usa quando ajuda; o resto continua
com vídeos de verdade. Para desligar, desmarque **✨ Usar animações**.

### Dublar o seu próprio vídeo

Na aba **Dublar meu vídeo**: envie o vídeo, cole o texto (cada linha é um trecho da fala) e clique em
**Dublar vídeo**. Vertical vira Short; horizontal vira vídeo longo. Você escolhe se mantém o som
original (baixinho ou normal) e se quer legenda e música.

### Pelo Claude Code

Abra a pasta do projeto no Claude Code e digite **`/radar`**: ele mostra os temas em alta do seu canal,
você escolhe um e ele escreve o roteiro e gera o vídeo. Para mudar o visual dos vídeos, é só pedir
("legenda com fundo escuro", "mapa mostrando onde o animal vive"...).

### Vídeos de sons relaxantes

```bash
python -I pipeline/relaxante.py relax/chuva-vento-passaros-12min.json
```

Gera 12 minutos de chuva fraca → chuva → vento e pássaros, com imagens de natureza e thumbnail.
O som é sintetizado por computador, sem direitos autorais de terceiros. Cada vídeo é um arquivo
em `relax/`; copie e mude as partes e os minutos.

Guia completo, com roteiro à mão, vídeo longo, hashtags e configurações: **[COMO-USAR.md](COMO-USAR.md)**.

## Atualizações

Quando sai uma versão nova, o painel mostra a faixa **"Nova versão do app disponível"** com o que
mudou. Clique em **Atualizar agora**: ele baixa a versão nova, instala só o que mudou e reinicia o
painel sozinho. Seu canal, sua chave do Pexels, seus roteiros e vídeos continuam como estão.
O que mudou em cada versão: **[CHANGELOG.md](CHANGELOG.md)**. Também dá para atualizar pela pasta do
projeto com `git pull`.

## Dicas

- **Retenção**: copie `dados/aprendizados.exemplo.md` para `dados/aprendizados.md` e anote o que
  funciona no seu canal (YouTube Studio > Estatísticas). O Claude lê esse arquivo antes de sugerir
  ideias e escrever roteiros.
- **Ao publicar**: a narração é voz sintética, então marque "Conteúdo alterado ou sintético" como
  *Sim* no YouTube Studio.
- **Temas**: as imagens vêm do Pexels, então funcionam melhor temas que existem em banco de imagens
  (natureza, ciência, lugares, comida, objetos). Jogos, filmes e pessoas famosas não funcionam.

## Problemas comuns

| Problema | Solução |
|---|---|
| `ModuleNotFoundError` ao gerar | Rode `python -s -m pip install -r requirements.txt` (instala onde o `python -I` enxerga) |
| `ffmpeg` não encontrado | Instale o ffmpeg e abra o terminal de novo |
| Painel diz "não achei o Claude Code" | Instale o Claude Code; ou use o `/radar` direto no Claude Code |
| Mudou algo e o painel não mostra | Feche a janela preta e abra o `Abrir painel.bat` de novo |

## Créditos e licenças

- Este projeto usa a [Licença MIT](LICENSE): pode usar, modificar e compartilhar à vontade, mantendo o aviso de autoria.

- Montagem de vídeo com [Remotion](https://www.remotion.dev): gratuito para pessoas físicas e empresas
  de até 3 pessoas. Empresas maiores precisam de [licença](https://www.remotion.dev/license).
- Imagens do [Pexels](https://www.pexels.com) (uso gratuito).
- Narração com [edge-tts](https://github.com/rany2/edge-tts) (vozes neurais da Microsoft).
