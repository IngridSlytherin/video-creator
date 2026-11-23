---
name: radar
description: Radar de temas em alta para o canal configurado em dados/canal.json. Roda pipeline/radar.py (Wikipedia, Google Notícias, Google Trends, YouTube), lê o relatório e sugere 5 temas de vídeo da categoria do canal, com título e gancho. Use quando o usuário pedir /radar, "o que está em alta", "ideias de vídeo" ou "próximo tema".
---

# Radar de temas

0. Leia `dados/canal.json` (nome e categoria do canal). Se não existir, pergunte ao usuário o
   **nome do canal** e a **categoria** e salve com
   `python -I -c "import importlib.util as u;s=u.spec_from_file_location('c','pipeline/canal.py');c=u.module_from_spec(s);s.loader.exec_module(c);c.salvar(c.montar('NOME','CATEGORIA','DESCRIÇÃO'))"`
   (ou peça para ele abrir o painel, que tem essa tela). Todo tema sugerido precisa ser da categoria.

**Se o pedido já traz um tema** (ex.: "/radar Quero um vídeo sobre: orca ..."), pule os passos 1–3:
leia só `dados/aprendizados.md` (se existir) e `historico.json` (se existir), sugira 2 ou 3 ângulos
(título, formato, gancho, por que agora) e siga para o passo 4.

1. Se ainda não existe `dados/radar/<hoje AAAA-MM-DD>.md`, rode (leva ~1–2 min):
   `python -I pipeline/radar.py`
   Se já existe, use o de hoje (não rode de novo).
2. Leia o relatório `.md` do dia, `dados/aprendizados.md` (se existir) e `historico.json` (se existir).
   Não leia o `.json` do radar, a menos que precise de um link de notícia.
3. Sugira **5 temas**, em português, numa lista curta. Para cada um:
   - **Título** (varie: nem tudo "Por que..."; use número, contraste, MAIÚSCULA em 1–2 palavras)
   - **Formato**: Short (`curto`/`padrao`/`longo`) ou vídeo longo + Shorts
   - **Gancho dos 3 primeiros segundos** (abre a curiosidade sem entregar a resposta)
   - **Por que agora**: o sinal do radar (notícia, pico na Wikipedia, vídeo bombando)
   Regras:
   - Só temas da categoria do canal. Nada que dependa de imagens de terceiros (jogos, filmes,
     marcas, pessoas famosas): as imagens vêm do Pexels.
   - Siga as "Regras do canal" de `dados/aprendizados.md` (tiradas dos números do canal).
   - Nunca repita uma pergunta que está em `dados/videos-do-canal.json` (vídeos já publicados):
     o vídeo repetido rende bem menos. O mesmo animal pode voltar com um ângulo novo.
   - Varie o formato dos títulos entre as sugestões (no máximo 1 começando com "Por que").
   - Confira se há imagens reais do assunto no Pexels (busca em inglês) antes de sugerir.
   - Vídeos do YouTube servem para ver formato e título que funcionam. Nunca copie o roteiro.
   - Dê atenção à seção "Vídeos que estouraram" (3× ou mais o normal do próprio canal): é o sinal
     mais forte de que **o assunto ou o formato** puxou público. Diga em "Por que agora" quando um
     tema vier dela (ex.: "um vídeo sobre isso fez 15× o normal do canal").
4. Pergunte qual tema o usuário quer. Quando ele escolher, escreva o roteiro em
   `roteiros/<slug>.json` seguindo os modelos (`exemplos/short-exemplo.json` para Short,
   `exemplos/longo-exemplo.json` para longo), com fatos verificáveis e fontes em
   `publicacao.fontes`, e gere o vídeo com `python -I pipeline/gerar_video.py roteiros/<slug>.json`.
