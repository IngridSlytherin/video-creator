# Novidades

Para atualizar: no painel, clique em **Atualizar agora** quando aparecer o aviso de versão nova.
Ou, na pasta do projeto: `git pull`.

## 1.21 — 28/11/2026
- **Sons relaxantes pelo painel**: em Novo vídeo, a opção **🌧️ Sons relaxantes**. Escolha os sons
  (chuva fraca, chuva, vento e pássaros; botão ▶ para ouvir), a duração (30 min a 3 horas) e clique em
  Criar vídeo. O Claude escreve título, descrição e hashtags; o resto é automático.
  Deixe os sons desmarcados e escreva para que é o vídeo (ex.: "para meditar"): o Claude pesquisa como são
  os vídeos mais vistos desse tema, escolhe os sons e o título e conta no painel o que escolheu.
- Vídeos de sons de **horas** ficam prontos bem mais rápido e sem pesar no computador: o som é feito em
  blocos de 6 min que se repetem sem emenda, e as imagens formam um ciclo que se repete. O arquivo também
  ficou mais leve (compressão maior; o YouTube recomprime de qualquer jeito).
- **Só vídeo longo**: em Pedir ideias, a opção nova faz o vídeo longo sem os Shorts tirados dele.

## 1.20 — 26/11/2026
- **Legenda pronta para o TikTok**: o `publicacao.txt` de cada Short ganha a seção "PARA O TIKTOK"
  (e o painel, um botão para copiar): o título sem as hashtags do YouTube, a pergunta do canal e
  poucas hashtags (3 do assunto + 1 do nicho + #fyp). Também avisa se o vídeo passa de 1 minuto
  (o TikTok só paga vídeos acima disso) e lembra de marcar "Conteúdo gerado por IA".
  Para vídeos já feitos: botão **Só textos** na aba Vídeos.

## 1.19 — 24/11/2026
- Nada de sobra no disco: quando um vídeo dá erro no meio (ou é cancelado), os clipes baixados
  também são apagados. Antes eles ficavam na pasta e podiam somar centenas de MB.

## 1.18 — 23/11/2026
- As transições ficam **sem o whoosh** (o som chamava atenção demais). O pop dos números e
  gráficos continua. Quem quiser o whoosh de volta: `WHOOSH=1` no `.env`.

## 1.17 — 23/11/2026
- **Vídeos com acabamento de edição**:
  - **Transições** quando a fala muda de trecho: cortina, deslize, círculo que abre e zoom com
    desfoque, sem repetir a mesma duas vezes seguidas. Dentro do mesmo trecho o corte continua seco.
  - **Efeitos sonoros**: um "whoosh" em cada transição e um "pop" quando aparece um número ou
    gráfico. São feitos por código, como os sons relaxantes, então não têm direitos autorais.
  - **Música que abaixa sob a voz**: fica baixinha enquanto a narração fala, sobe nas pausas e some
    no final. Vale também para o áudio dublado em inglês e espanhol.
- **Radar: vídeos que estouraram**. Para os vídeos mais vistos da semana no seu nicho, o radar olha os
  vídeos recentes do mesmo canal (feed público do YouTube, sem chave) e calcula o normal dele (a mediana
  das views). Os que fizeram **3× ou mais** o normal aparecem numa tabela nova: vídeo, canal, views,
  normal do canal e quantas vezes acima. Isso mostra quando foi **o assunto ou o formato** que puxou o
  público, e não só o tamanho do canal. O tema desses vídeos ganha pontos no ranking.
- Um trecho sem nenhum clipe não para mais o vídeo: ele usa clipes parecidos já baixados (ex.: o
  Pexels chama o jacaré de "crocodile", e a busca por "caiman" não achava nada).
- Vídeo longo com mais imagens: quando o assunto tem pouca filmagem deitada, entram também filmagens
  em pé, no meio da tela com fundo desfocado. Roteiros novos buscam onça-preta como "black panther".

## 1.16 — 20/11/2026
- **Instalar.bat**: dois cliques instalam tudo (Node.js, Python, ffmpeg, Git, dependências), ligam as
  atualizações automáticas mesmo para quem baixou o .zip e abrem o painel. Pode rodar de novo sem medo.
- **Chaves pelo painel**: na primeira vez, o painel pede a chave grátis do Pexels (com o passo a passo)
  e confere se ela funciona. Para trocar depois: **🔑 Chaves** no topo. Ninguém precisa abrir o `.env`.
- **Voz reserva**: se a voz da Microsoft cair de vez, o vídeo é narrado por uma voz neural que roda no
  seu computador, sem internet (Piper). O vídeo inteiro usa a mesma voz, para não misturar.
- **Cortes com legenda revisada**: o Claude corrige palavras que a transcrição ouviu errado (nomes,
  números, espécies) nos trechos escolhidos.
- **Render mais rápido**: o pacote do Remotion é feito uma vez só e reaproveitado (antes, cada vídeo
  refazia o pacote e copiava a pasta `public/` inteira); clipes em 30 fps têm preferência.

## 1.15 — 19/11/2026
- **Aba ✂️ Cortes**: envie um vídeo longo seu e receba Shorts prontos. O app transcreve a fala no seu
  computador (Whisper, grátis) e o Claude escolhe de 3 a 5 trechos que funcionam sozinhos, com título,
  frase na tela, descrição e hashtags. Você confere cada trecho (▶ ver trecho), ajusta início e fim e
  cria os Shorts: vídeo deitado no meio, fundo desfocado, título em cima e legenda animada embaixo.
- Na primeira vez, o app baixa o modelo de transcrição (~500 MB). Para errar menos (e demorar mais),
  ponha `WHISPER_MODELO=medium` no `.env`.

## 1.14 — 19/11/2026
- **Já tenho o roteiro**: na aba Novo vídeo, cole um roteiro pronto, escolha **Short** (em pé) ou
  **vídeo longo** (deitado) e a **voz** (com botão para ouvir cada uma) e clique em **Criar vídeo**.
  O texto fica do jeito que você escreveu; o app separa as cenas, escolhe as imagens, cria título,
  descrição e hashtags e já monta o vídeo. Fatos duvidosos aparecem como aviso.
- **Animações automáticas (Manim)**: quando o texto tem tamanhos, números, datas ou porcentagens, a IA
  pode transformar aquele trecho numa cena animada (comparação com barras, medidor, linha do tempo ou
  quadradinhos de porcentagem), feita no tempo exato da narração. Ela só usa quando ajuda; o resto
  continua com vídeos de verdade. Dá para desligar em "Já tenho o roteiro" (✨ Usar animações).
- Clipe em formato que o Remotion não lê (alguns 60 fps/2K) é convertido e o render tenta de novo.
- A voz tenta até 8 vezes (cerca de 1 minuto) quando o serviço da Microsoft falha, e agora também
  percebe quando o áudio de uma frase vem cortado no meio (antes passava e a fala sumia no vídeo).
- Cada roteiro pode ter a sua própria voz (campo `"voz"`); sem ele, vale a voz do canal.
- A lista `"evitar"` no topo de um roteiro de Short agora vale para todos os trechos.

## 1.13 — 19/11/2026
- Narração protegida: quando o serviço de voz da Microsoft falha (sem áudio) ou devolve a frase
  cortada, o app percebe e tenta de novo (até 4 vezes) antes de desistir com um aviso claro.

## 1.12 — 19/11/2026
- Internet muito mais rápida em redes com IPv6 com defeito: o app passa a usar só IPv4 (cada conexão
  esperava ~21 s antes; o radar caiu de 18 minutos para 18 segundos, e os downloads de clipes também aceleram).

## 1.11 — 19/11/2026
- Radar não trava mais quando a Wikipedia está lenta: depois de 90 s ele segue com as outras fontes
  (notícias, Trends e YouTube) e avisa.

## 1.10 — 17/11/2026
- Download de clipes mais resistente: quando o Pixabay/Pexels pede para esperar (erro 429) o app
  espera e tenta de novo; se um clipe não baixar, ele é pulado e outro entra no lugar (o vídeo não para).

## 1.9 — 17/11/2026
- **Títulos do canal guardados**: com o link do canal em ⚙ Canal, o painel busca 1x por dia os vídeos
  publicados (feed oficial e página pública do canal) e guarda os títulos em `dados/videos-do-canal.json`.
  A lista só cresce: pode apagar os vídeos e o histórico do computador que o app não esquece o que
  já foi publicado (e não repete perguntas).

## 1.8 — 17/11/2026
- **Tema escuro**: botão "🌙 Tema escuro" / "☀️ Tema claro" no topo do painel. Na primeira vez
  segue o tema do Windows; depois lembra a sua escolha.

## 1.7 — 17/11/2026
- **O que dá certo no canal**: a aba Resultados analisa formato do título, duração, dia da
  publicação, assunto e perguntas repetidas, e transforma isso em **regras do canal** que o Claude
  passa a seguir nas ideias e roteiros (atualizadas a cada medição).
- O app guarda a lista de todos os vídeos já publicados e evita repetir uma pergunta
  (o mesmo animal pode voltar com um ângulo novo).
- O radar deixou de penalizar forte animais que já têm vídeo (os números mostram que repetir o
  animal não atrapalha; repetir a mesma pergunta, sim).

## 1.6 — 17/11/2026
- **Visual novo do painel**, mais claro e amigável: fundo verde-menta, cartões brancos, fonte
  arredondada (Nunito), abas em pílula com ícones e rótulos sem letras maiúsculas.
- Resultados: lê a exportação padrão do YouTube Studio (calcula a retenção pelo tempo de exibição).

## 1.5 — 17/11/2026
- **Legenda .srt** de cada vídeo, pronta para enviar no YouTube Studio (ajuda na busca).
- **Outras línguas**: título, descrição e **áudio dublado** em inglês e espanhol (no mesmo tempo
  do vídeo), para o recurso de várias faixas de áudio do YouTube. Botões no painel para copiar e baixar.
- **Animações**: número contando ("0 → 80 km/h") e comparação com barras ("Humano × Baleia").
- **Radar automático** uma vez por dia ao abrir o painel e **aviso para medir** os resultados.

## 1.4 — 17/11/2026
- **Pixabay como segunda fonte de vídeos** (opcional): com `PIXABAY_API_KEY` no `.env`, o gerador
  busca no Pexels e no Pixabay e mistura os resultados. Vale também para os vídeos relaxantes.

## 1.3 — 17/11/2026
- **Conferência das imagens**: antes de montar, o Claude olha um quadro de cada clipe e troca os que
  não servem (telão, brinquedo, bicho errado, pessoas em destaque, só fundo sem o assunto).
  Os ruins entram numa lista de bloqueados e não voltam em vídeos futuros.
- **Aba Resultados**: envie a exportação do YouTube Studio e veja se os vídeos do app seguram mais
  o público do que os antigos. A conclusão vai para `dados/aprendizados.md`, que o Claude lê.

## 1.2 — 17/11/2026
- O painel avisa quando sai uma versão nova e atualiza com um clique (reinicia sozinho).
- Para isso funcionar, abra o painel pelo `Abrir painel.bat` atualizado.

## 1.1 — 17/11/2026
- Vídeos em **português, inglês ou espanhol**: voz, legenda, roteiro, descrição e radar do país.
- Os horários sugeridos para postar ficam em `dados/canal.json` (`"horarios"`).
- README em inglês.

## 1.0 — 17/11/2026
- Primeira versão: Shorts e vídeos longos, radar de temas, painel com ideias e roteiros pelo
  Claude Code, dublagem do seu vídeo e vídeos de sons relaxantes.
- Na primeira vez, o painel pede o nome e a categoria do canal.
