# Guia de uso — gerador de vídeos

Instalação e visão geral: veja o [README](README.md). Este guia detalha cada parte.

## Painel (interface no navegador)
Dê dois cliques em **`Abrir painel.bat`**. Abre `http://localhost:8765` no navegador; a janela preta
precisa ficar aberta enquanto você usa (fechar = desligar o painel).

- **Primeira vez**: o painel pede o **nome do canal**, a **categoria** e a **língua dos vídeos**
  (português do Brasil, inglês ou espanhol). Isso define a marca nos vídeos, o assunto do radar, das
  ideias e dos roteiros, a voz da narração e o país do radar. Para trocar depois, clique em **⚙ Canal**.
- **Novo vídeo**: escreva o tema e clique em **Pedir ideias**. O Claude sugere 3 ângulos (uns 30 s);
  clique em **Escrever este roteiro** (1–3 min, ele confere os fatos na internet). Leia a narração na
  prévia e clique em **Gerar vídeo agora**. Usa o Claude Code da sua conta (modelo Sonnet); para trocar,
  coloque `CLAUDE_MODELO=opus` no `.env`.
- **Novo vídeo › 📋 Já tenho o roteiro**: cole o seu texto, escolha o tamanho (**Short** em pé ou
  **vídeo longo** deitado) e a **voz** (clique em ▶ ouvir para escutar cada uma) e clique em
  **Criar vídeo**. O app usa as suas palavras como estão: só separa em cenas, escolhe as imagens e cria
  título, descrição e hashtags; depois monta o vídeo sozinho. Se algum fato parecer errado, ele avisa
  (sem mudar o seu texto). No vídeo longo, uma linha como `## O sapo` vira o título de um capítulo.
- **Animações automáticas**: nos roteiros (pedidos ao Claude ou colados), a IA decide se algum trecho
  fica melhor como desenho animado: comparação de tamanhos com barras, medidor de velocidade, linha do
  tempo ou porcentagem. A animação é feita no tempo exato da fala e entra no lugar dos clipes daquele
  trecho; o resto continua com vídeos de verdade. Para não usar, desmarque **✨ Usar animações**.
- **🔑 Chaves**: na primeira vez, o painel pede a chave grátis do Pexels (com o passo a passo) e confere
  se ela funciona; a do Pixabay é opcional. Para trocar depois, clique em **🔑 Chaves** no topo.
- **Voz reserva**: se a voz da Microsoft não responder nem depois de 8 tentativas, o app narra o vídeo
  inteiro com uma voz que roda no seu computador (Piper; baixa ~60 MB na primeira vez). O painel avisa.
- **✂️ Cortes**: envie um vídeo longo seu (com fala) e clique em **Encontrar os melhores momentos**.
  O app transcreve o que é dito (leva mais ou menos 1/3 do tempo do vídeo) e o Claude escolhe de 3 a 5
  trechos que funcionam sozinhos como Shorts. Em cada um: **▶ ver trecho**, título, frase na tela e
  início/fim (minutos:segundos) para ajustar. Marque os que quer e clique em **Criar Shorts
  selecionados**: eles aparecem em **Vídeos prontos**. Na primeira vez, baixa o modelo de transcrição
  (~500 MB). Só use vídeos seus ou que você tem direito de usar.
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
- **Tema escuro**: botão "🌙 Tema escuro" no topo (ao lado de ⚙ Canal). Na primeira vez segue o Windows.
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

## Legendas e outras línguas (automático)
No fim de cada vídeo, o gerador cria em `saida/<vídeo>/`:
- `legenda.<língua>.srt`: legenda da narração. Envie em **YouTube Studio → Legendas → Adicionar →
  Enviar arquivo → Com tempo**. O YouTube usa esse texto na busca e na tradução automática.
- Para as outras línguas (inglês/espanhol, se o canal for em português): **título e descrição
  traduzidos** (Studio → Idiomas → Adicionar idioma) e **áudio dublado** `audio.<língua>.mp3`, com a
  narração traduzida no mesmo tempo do vídeo, a mesma música e o mesmo volume. Onde o Studio mostrar
  **"Adicionar áudio"**, envie esse arquivo: quem assiste nos EUA ou na América Latina ouve na língua dele.
- Tudo aparece no painel em **Vídeos prontos → Legendas e outras línguas**, com botões para copiar e baixar.
  Para vídeos antigos, o botão **Gerar legendas e traduções** faz o mesmo.
- A legenda gravada na imagem continua na língua do canal.
- Para escolher as línguas, ponha em `dados/canal.json`: `"traducoes": ["en-US"]` (ou `[]` para nenhuma).
  Para pular num vídeo: `--sem-traducao`. Pelo terminal, num vídeo pronto: `python -I pipeline/traduzir.py <vídeo>`.

## Animações (número contando e comparação)
Num trecho do roteiro, o campo `"grafico"` mostra um cartão animado enquanto esse trecho é falado:
- Número contando: `"grafico": {"tipo": "numero", "valor": 80, "sufixo": " km/h", "rotulo": "velocidade do soco"}`
  (opcional: `"de": 0`, `"prefixo": "R$ "`).
- Comparação com barras: `"grafico": {"tipo": "comparacao", "rotulo": "comprimento", "unidade": "m",
  "itens": [{"nome": "Humano", "valor": 1.7}, {"nome": "Baleia-azul", "valor": 30}]}` (até 4 itens; o último fica em amarelo).
O Claude já usa isso sozinho nos roteiros (no máximo 2 por vídeo).

## Radar automático e lembrete de medir
- O painel roda o radar sozinho uma vez por dia (não usa o Claude), uns segundos depois de abrir.
  Para desligar: `"radarAutomatico": false` em `dados/canal.json`.
- Quando um vídeo marcado como "Já publiquei" fizer 7 dias e não houver medição nas últimas 2 semanas,
  o painel mostra o aviso **"Já dá para medir os resultados"**.

## Segunda fonte de vídeos: Pixabay (opcional, grátis)
Com a chave do Pixabay, o gerador busca clipes no Pexels **e** no Pixabay e mistura os resultados:
mais opções quando o Pexels tem pouco material de um assunto.
1. Crie uma conta em [pixabay.com](https://pixabay.com) e abra [pixabay.com/api/docs](https://pixabay.com/api/docs/):
   a chave aparece na seção "Parameters", no campo `key`.
2. Cole no `.env`: `PIXABAY_API_KEY=sua_chave`.

Licença do Pixabay: uso comercial liberado, sem precisar citar; não pode revender os vídeos como
banco de imagens. As buscas ficam guardadas por 24 h em `dados/cache-pixabay/` (regra da API).

## Conferência das imagens (automática)
- Depois de baixar os clipes, o gerador monta folhas com um quadro de cada clipe e pede ao Claude Code
  para apontar os que não servem: telão/prédio, brinquedo, desenho, comida, outro bicho, pessoas em
  destaque, ou só o fundo sem o assunto. Esses são trocados (até 3 conferências; cada uma só olha os novos).
- Os clipes reprovados vão para `dados/clipes-bloqueados.json` e não voltam em vídeos futuros.
- Sem o Claude Code instalado, o vídeo é gerado normalmente, sem conferência.
- Para pular (mais rápido): `python -I pipeline/gerar_video.py roteiros/x.json --sem-conferir`.

## Resultados: os vídeos do app estão funcionando?
Aba **Resultados** do painel (ou `python -I pipeline/medir.py arquivo.zip`):
1. YouTube Studio → **Insights** (ou "Estatísticas", no menu da esquerda) → **Modo avançado** → aba **Conteúdo** → período (ex.: últimos 365 dias).
2. Seta de download → **Valores separados por vírgula (.csv)**: o YouTube baixa um `.zip`.
3. Envie o `.zip` na aba Resultados.

O relatório compara % média assistida, tempo médio e views dos vídeos **feitos pelo app** (os que
estão no `historico.json`) com os **anteriores**, separando Shorts e vídeos longos. Vídeos com menos
de 7 dias ou 100 views ficam fora da média (os números ainda mudam). A conclusão é anotada em
`dados/aprendizados.md`, que o Claude lê antes de sugerir ideias. Repita de 2 em 2 semanas.

## Títulos já publicados (para não repetir)
- Em **⚙ Canal**, coloque o **link do canal no YouTube**. O painel busca uma vez por dia os vídeos
  publicados (feed oficial do canal e a página pública de Shorts/vídeos) e guarda os títulos em
  `dados/videos-do-canal.json`. A exportação do Studio (aba Resultados) completa a lista com todos.
- A lista **só cresce**: pode apagar a pasta `saida/` (os vídeos) e o histórico à vontade.
  Só não apague a pasta `dados/` (é onde ficam o canal, as regras e essa lista).
- Pelo terminal: `python -I pipeline/titulos_canal.py`.

## Atualizar o app
- O painel confere no GitHub, ao abrir e a cada 6 horas, se saiu versão nova. Se saiu, aparece a faixa
  **"Nova versão do app disponível"** com as novidades.
- **Atualizar agora**: baixa a versão nova (`git pull`), instala só o que mudou (`npm install` /
  `pip install`) e reinicia o painel sozinho. **Depois** esconde o aviso até a próxima versão.
- Seus dados (canal, `.env`, roteiros, vídeos) não fazem parte do GitHub e não são tocados.
- Se você mudou arquivos do app, o botão fica bloqueado para não apagar suas mudanças: peça ao
  Claude Code para atualizar com `git pull` mantendo as mudanças.
- O que mudou em cada versão: [CHANGELOG.md](CHANGELOG.md).

**Para quem publica versões novas** (dona do repositório): faça as mudanças, anote no `CHANGELOG.md`
e envie (`git push`). O título de cada commit aparece no aviso do painel de quem usa o app, então
escreva títulos claros, em português, do ponto de vista de quem usa ("Vídeos em inglês e espanhol").

## Ver/ajustar no Remotion Studio
```bash
npx remotion studio
```

## Língua dos vídeos
- Escolhida na configuração do canal: **português (Brasil)**, **inglês** ou **espanhol**.
- Muda: voz da narração, legendas, roteiros escritos pelo Claude, textos da descrição (capítulos,
  fontes, chamadas) e o país do radar (Google Notícias, Trends e YouTube). O painel continua em português.
- A lista pronta de 133 animais é em português; em inglês/espanhol o Claude cria a lista na língua certa.
- Para trocar a voz (ex.: masculina), mude `"voz"` em `dados/canal.json`. Vozes: `pt-BR-FranciscaNeural`,
  `pt-BR-AntonioNeural`, `en-US-JennyNeural`, `en-US-GuyNeural`, `es-MX-DaliaNeural`, `es-MX-JorgeNeural`.
- Os horários sugeridos ficam em `"horarios"` em `dados/canal.json`: troque pelos do seu público.

## Configurações
- `.env`: chave do Pexels e velocidade da fala (`VELOCIDADE_VOZ`).
- Música de fundo: coloque arquivos `.mp3` em `public/musica/` (ex.: da Biblioteca de áudio do
  YouTube Studio). O gerador escolhe uma automaticamente, em volume baixo.
- Cores e fonte: `src/tipos.ts`.

## Arquivos
- `historico.json` — lista dos vídeos já feitos (para não repetir temas).
- `public/projetos/` — narração e configurações de cada vídeo; os clipes baixados são apagados
  automaticamente depois de cada vídeo.
