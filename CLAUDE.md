# Gerador de vídeos para YouTube (Shorts e vídeos longos)

Sistema local e gratuito: roteiro → narração (edge-tts) → clipes do Pexels → montagem no Remotion
→ `saida/<slug>/` com `video.mp4`, `publicacao.txt` (título, descrição, tags, horário) e
`thumbnail.png` (só no vídeo longo). A pessoa publica manualmente no YouTube.

## Antes de tudo: o canal de quem está usando

- Leia `dados/canal.json`. Ele diz o **nome do canal** e a **categoria** (ex.: Animais e natureza,
  História, Culinária). **Todo tema, ideia e roteiro precisa ser da categoria do canal.**
- Se `dados/canal.json` não existir, pergunte ao usuário:
  1. o nome do canal no YouTube;
  2. a categoria do canal (sugira: Animais e natureza, Ciência e espaço, História, Curiosidades
     gerais, Culinária, Viagem e lugares, Tecnologia, Esportes, Saúde e bem-estar, Sons relaxantes,
     ou outra);
  3. a língua dos vídeos: `pt-BR` (português do Brasil), `en-US` (inglês) ou `es-MX` (espanhol);
  4. em uma frase, sobre o que é o canal (opcional).
  Depois salve com `pipeline/canal.py` (`montar(nome, categoria, descricao, idioma)` + `salvar(...)`) ou
  peça para a pessoa abrir o painel (`Abrir painel.bat`), que tem essa tela.
- **Escreva roteiros, títulos, descrições e hashtags na língua do canal** (`idioma` em
  `dados/canal.json`). A voz da narração e o país do radar seguem essa língua automaticamente.
  Converse com a pessoa em português (o painel e as instruções são em português).
- Se não existir o arquivo de temas indicado em `radar.temas` (`dados/canal.json`), crie a lista
  no mesmo formato de `dados/temas/animais.json` (80–120 itens: pt = nome na língua do canal, en,
  wiki_<língua> e wiki_en, grupo, busca na língua do canal) e ajuste `radar.buscasNoticias` /
  `radar.buscasYoutube` (na língua do canal). A lista pronta de animais só vale para `pt-BR`.
- `dados/aprendizados.md` (se existir) traz o que funciona no canal da pessoa: siga.

## Onde fica cada coisa

| Caminho | O que é |
|---|---|
| `pipeline/gerar_video.py` | Gera Short/longo a partir de `roteiros/<slug>.json` |
| `pipeline/radar.py` | Temas em alta (Wikipedia, Google Notícias, Trends, YouTube) |
| `pipeline/painel.py` + `painel/index.html` | Interface local em http://localhost:8765 |
| `pipeline/dublar.py` | Narração + legenda sobre um vídeo enviado pela pessoa |
| `pipeline/relaxante.py` + `pipeline/sons.py` | Vídeos longos de sons relaxantes (som sintetizado) |
| `pipeline/canal.py` | Configuração do canal |
| `src/` | Composições Remotion (Short, Longo, Thumbnail, Legendas) |
| `exemplos/` | Modelos de roteiro (Short e longo) |
| `relax/` | Roteiros de vídeos relaxantes |

## Regras

- Roteiros: siga a estrutura de `exemplos/short-exemplo.json` (Short) ou `exemplos/longo-exemplo.json`
  (longo com capítulos). Campos `animal`, `busca`, `exigir`, `evitar` em inglês (são o assunto que
  filtra os clipes do Pexels, mesmo que não seja um animal); o resto na língua do canal.
- Confira os fatos (WebSearch) e coloque fontes em `publicacao.fontes`.
- Animações (opcional, até 2 por vídeo): num trecho com número marcante ou comparação de tamanho, use
  `"grafico": {"tipo": "numero", "valor": 80, "sufixo": " km/h", "rotulo": "..."}` ou
  `"grafico": {"tipo": "comparacao", "rotulo": "...", "unidade": "m", "itens": [{"nome": "...", "valor": 1.7}, ...]}`.
- Imagens só do Pexels: não proponha temas que dependem de jogos, filmes, marcas ou pessoas famosas.
- Rode Python com `python -I`. A chave do Pexels fica em `.env` (nunca mostre).
- Comando `/radar` (`.claude/skills/radar`) sugere temas a partir do radar.
