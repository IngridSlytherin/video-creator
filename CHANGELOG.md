# Novidades

Para atualizar: no painel, clique em **Atualizar agora** quando aparecer o aviso de versão nova.
Ou, na pasta do projeto: `git pull`.

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
