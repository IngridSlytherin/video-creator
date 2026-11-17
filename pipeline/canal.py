"""Configuração do canal de quem usa o sistema (nome, categoria e o que o radar acompanha).

Fica em dados/canal.json (não vai para o GitHub: cada pessoa tem o seu).
Na primeira vez, o painel pede o nome e a categoria; ou rode:
    python -I pipeline/canal.py
"""
import json
import sys
import unicodedata
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "dados" / "canal.json"

# Categorias com radar pronto. As outras usam termos gerais e, se o Claude Code estiver
# instalado, ele cria a lista de temas da categoria (dados/temas/<categoria>.json).
PREDEFINIDAS = {
    "Animais e natureza": {
        "temas": "dados/temas/animais.json",
        "hashtagsFim": ["curiosidadessobreanimais", "curiosidadesanimais", "mundoanimal",
                        "biologia", "animais", "vocesabia"],
        "buscasNoticias": ['"nova espécie"', "animal cientistas", "animais descoberta",
                           "biólogos animal", "zoológico filhote", "comportamento animal estudo"],
        "buscasYoutube": ["curiosidades animais", "animais incríveis", "mundo animal",
                          "você sabia animais", "animais selvagens"],
        # retenção por grupo de animal (ajuste com os dados do seu canal)
        "pesoGrupo": {"savana": 1.15, "marinho": 1.15, "ave": 1.1, "inseto": 0.95,
                      "pet": 0.85, "fazenda": 0.8},
    },
}
CATEGORIAS = ["Animais e natureza", "Ciência e espaço", "História", "Curiosidades gerais",
              "Culinária", "Viagem e lugares", "Tecnologia", "Esportes", "Saúde e bem-estar",
              "Sons relaxantes"]


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def montar(nome, categoria, descricao=""):
    """Cria a configuração completa a partir de nome + categoria."""
    nome, categoria, descricao = nome.strip(), categoria.strip(), descricao.strip()
    pre = PREDEFINIDAS.get(categoria, {})
    tag_cat = re.sub(r"[^a-z0-9]", "", slug(categoria))
    sobre = descricao or categoria.lower()
    return {
        "nome": nome,
        "categoria": categoria,
        "descricao": descricao,
        "hashtagsInicio": [re.sub(r"[^a-z0-9]", "", slug(nome))],
        "hashtagsFim": pre.get("hashtagsFim", [tag_cat, "curiosidades", "vocesabia"]),
        "chamada": f"🔔 Inscreva-se no {nome} para mais vídeos sobre {sobre}.",
        "chamadaFinal": f"Segue o {nome} para mais vídeos como este.",
        "pergunta": "💬 Você já sabia disso? Conta aqui nos comentários!",
        "avisoIA": "Narração com voz sintética. Imagens: Pexels (uso gratuito).",
        "radar": {
            "temas": pre.get("temas", f"dados/temas/{slug(categoria)}.json"),
            "buscasNoticias": pre.get("buscasNoticias", [categoria, f"{categoria} descoberta",
                                                         f"{categoria} estudo", f"{categoria} curiosidade"]),
            "buscasYoutube": pre.get("buscasYoutube", [f"curiosidades {categoria}", categoria,
                                                       f"você sabia {categoria}"]),
            "pesoGrupo": pre.get("pesoGrupo", {}),
        },
    }


def carregar(obrigatorio=True):
    """Lê dados/canal.json. Sem ele, explica como configurar e encerra."""
    if ARQUIVO.exists():
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    if obrigatorio:
        sys.exit("Canal ainda não configurado. Abra o painel (Abrir painel.bat) ou rode: "
                 "python -I pipeline/canal.py")
    return None


def salvar(cfg):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("Configurar o canal\n")
    nome = input("Nome do canal no YouTube: ").strip()
    print("\nCategorias:")
    for i, c in enumerate(CATEGORIAS, 1):
        print(f"  {i}. {c}")
    escolha = input("Número da categoria (ou escreva outra): ").strip()
    categoria = CATEGORIAS[int(escolha) - 1] if escolha.isdigit() and 0 < int(escolha) <= len(CATEGORIAS) else escolha
    descricao = input("Em uma frase, sobre o que é o canal? (opcional): ").strip()
    if not nome or not categoria:
        sys.exit("Nome e categoria são obrigatórios.")
    salvar(montar(nome, categoria, descricao))
    print(f"\nPronto! Configuração salva em {ARQUIVO.relative_to(RAIZ)}.")
