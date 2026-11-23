"""
Efeitos sonoros curtos feitos por código (sem direitos autorais), como os sons relaxantes de sons.py:
- "whoosh": vento rápido que passa de um lado para o outro (nas transições entre cenas);
- "pop": estalo curto e redondo (quando aparece um número ou gráfico na tela).

Os arquivos ficam em public/efeitos/ e são gerados uma vez só (na primeira vez que um vídeo usa).

Uso (para ouvir): python -I pipeline/efeitos.py
"""
from pathlib import Path

import numpy as np
from scipy.io import wavfile

TAXA = 44100
RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "public" / "efeitos"
VERSAO = "v1"  # mude ao alterar o som, para os arquivos serem refeitos
WHOOSHES = 3


def _salvar(x, destino):
    x = x / (np.abs(x).max() + 1e-9) * 0.85
    wavfile.write(str(destino), TAXA, (x * 32767).astype(np.int16))


def _passa_banda(x, centro, q=2.5):
    """Filtro de estado variável com a frequência mudando a cada amostra (o 'vuuush' que sobe e desce)."""
    saida = np.empty_like(x)
    baixo = banda = 0.0
    f = 2 * np.sin(np.pi * np.minimum(centro, TAXA / 6) / TAXA)
    amort = 1 / q
    for i in range(len(x)):
        baixo += f[i] * banda
        alto = x[i] - baixo - amort * banda
        banda += f[i] * alto
        saida[i] = banda
    return saida


def whoosh(semente, segundos=0.7):
    rng = np.random.default_rng(semente)
    n = int(segundos * TAXA)
    t = np.linspace(0, 1, n)
    pico = 0.5 + 0.1 * rng.random()  # o ponto mais forte fica perto do meio (o corte da cena)
    # sobe devagar e some rápido, como algo passando perto
    env = np.where(t < pico, (t / pico) ** 2.2, np.exp(-(t - pico) / (0.12 + 0.05 * rng.random())))
    f_baixa, f_alta = 250 + 150 * rng.random(), 2200 + 1200 * rng.random()
    centro = f_baixa * (f_alta / f_baixa) ** env  # a frequência acompanha a força
    ruido = rng.standard_normal(n)
    som = _passa_banda(ruido, centro) * env
    # um pouco de "corpo" grave por baixo
    grave = _passa_banda(rng.standard_normal(n), np.full(n, 120.0), q=1.2) * env * 0.5
    mono = som + grave
    # passa da esquerda para a direita (ou ao contrário)
    lado = t if semente % 2 else 1 - t
    esquerda = mono * np.sqrt(1 - 0.7 * lado)
    direita = mono * np.sqrt(0.3 + 0.7 * lado)
    return np.stack([esquerda, direita], axis=1)


def pop(segundos=0.18):
    n = int(segundos * TAXA)
    t = np.arange(n) / TAXA
    freq = 480 + 900 * np.exp(-t / 0.018)  # a altura cai rápido: "bóp"
    fase = 2 * np.pi * np.cumsum(freq) / TAXA
    env = np.minimum(1, t / 0.002) * np.exp(-t / 0.035)
    som = (np.sin(fase) + 0.25 * np.sin(2 * fase)) * env
    return np.stack([som, som], axis=1)


def arquivos():
    """Garante os arquivos em public/efeitos/ e devolve os caminhos relativos a public/."""
    PASTA.mkdir(parents=True, exist_ok=True)
    nomes = {"whoosh": [f"whoosh-{VERSAO}-{i + 1}.wav" for i in range(WHOOSHES)], "pop": f"pop-{VERSAO}.wav"}
    for i, nome in enumerate(nomes["whoosh"]):
        if not (PASTA / nome).exists():
            _salvar(whoosh(i + 1), PASTA / nome)
    if not (PASTA / nomes["pop"]).exists():
        _salvar(pop(), PASTA / nomes["pop"])
    return {"whoosh": [f"efeitos/{n}" for n in nomes["whoosh"]], "pop": f"efeitos/{nomes['pop']}"}


if __name__ == "__main__":
    print(arquivos())
