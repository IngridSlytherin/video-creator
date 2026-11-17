"""Sons da natureza sintetizados por computador (sem direitos autorais de terceiros).

Uso direto (gera amostras para ouvir):
    python -I pipeline/sons.py amostras            -> saida/amostras-sons/*.mp3 (30 s cada)
    python -I pipeline/sons.py chuva_fraca 240 x.wav

Cada som é uma função (segundos, semente) -> matriz estéreo float32 (n, 2) entre -1 e 1.
Para criar um som novo (mar, fogueira...), escreva outra função e registre em SONS.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

TAXA = 44100
RAIZ = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- blocos básicos
def filtro(x, tipo, freq, ordem=4):
    sos = butter(ordem, freq, btype=tipo, fs=TAXA, output="sos")
    return sosfilt(sos, x, axis=0).astype(np.float32)


def ruido_branco(n, rng, canais=2):
    return rng.standard_normal((n, canais)).astype(np.float32)


def ruido_marrom(n, rng, canais=2):
    """Ruído grave e 'macio' (integração do branco, com vazamento para não derivar)."""
    b = ruido_branco(n, rng, canais)
    sos = butter(1, 20, btype="lowpass", fs=TAXA, output="sos")  # ~ integração suave
    m = sosfilt(sos, b, axis=0)
    return (m / (np.abs(m).max() + 1e-9)).astype(np.float32)


def ondulacao(n, rng, freq_max=0.2, minimo=0.6, maximo=1.0, canais=1):
    """Envelope lento e aleatório (rajadas, intensidade variando), entre minimo e maximo."""
    passos = max(4, int(n / TAXA * freq_max * 4))
    pontos = rng.random((passos, canais))
    x = np.linspace(0, passos - 1, n)
    env = np.empty((n, canais), dtype=np.float32)
    for c in range(canais):
        env[:, c] = np.interp(x, np.arange(passos), pontos[:, c])
    env = filtro(env, "lowpass", freq_max, ordem=2)
    env = (env - env.min()) / (env.max() - env.min() + 1e-9)
    return (minimo + (maximo - minimo) * env).astype(np.float32)


def reverb(x, rng, segundos=0.8, mistura=0.25):
    """Reverberação simples: ruído com decaimento exponencial como 'sala' (mata, céu aberto)."""
    t = np.arange(int(segundos * TAXA)) / TAXA
    saida = np.empty_like(x)
    for c in range(x.shape[1]):
        ir = rng.standard_normal(len(t)).astype(np.float32) * np.exp(-t / (segundos / 5))
        ir = filtro(ir[:, None], "lowpass", 6000)[:, 0]
        ir /= np.sqrt((ir**2).sum()) + 1e-9
        molhado = fftconvolve(x[:, c], ir)[: len(x)]
        saida[:, c] = (1 - mistura) * x[:, c] + mistura * molhado
    return saida


def normalizar(x, pico=0.9):
    return (x * (pico / (np.abs(x).max() + 1e-9))).astype(np.float32)


# ---------------------------------------------------------------- chuva
def gotas(n, rng, por_segundo, volume, freq=(1800, 7000), duracao_ms=(2, 9)):
    """Pingos: pequenos 'tics' agudos que somem rápido, em momentos aleatórios, em cada canal."""
    saida = np.zeros((n, 2), dtype=np.float32)
    total = rng.poisson(por_segundo * n / TAXA)
    inicios = rng.integers(0, n - TAXA // 10, total)
    for ini in inicios:
        tau = rng.uniform(*duracao_ms) / 1000
        tam = int(tau * 6 * TAXA)
        t = np.arange(tam) / TAXA
        f = rng.uniform(*freq)
        queda = 1 - rng.uniform(0, 0.25) * t / t[-1]  # alguns pingos 'caem' de tom (plink)
        som = np.sin(2 * np.pi * f * queda * t) * np.exp(-t / tau)
        amp = volume * rng.lognormal(0, 0.6)
        lado = rng.random()  # posição no estéreo
        saida[ini:ini + tam, 0] += som * amp * (1 - lado)
        saida[ini:ini + tam, 1] += som * amp * lado
    return saida


def chuva(segundos, semente, intensidade):
    """intensidade 0..1: 0.3 = chuva fraca, 0.7 = chuva média."""
    rng = np.random.default_rng(semente)
    n = int(segundos * TAXA)
    branco = ruido_branco(n, rng)
    # Som 'quente': a maior parte da energia entre 250 Hz e 4 kHz, agudos suaves (senão vira chiado de TV).
    chiado = filtro(branco, "bandpass", (600, 6500)) * (0.05 + 0.10 * intensidade)
    corpo = filtro(ruido_branco(n, rng), "bandpass", (150, 1800)) * (0.12 + 0.35 * intensidade)
    variacao = ondulacao(n, rng, freq_max=0.08, minimo=0.75, maximo=1.0)
    base = (chiado + corpo) * variacao
    pingos = gotas(n, rng, por_segundo=10 + 120 * intensidade, volume=0.04 + 0.07 * intensidade,
                   freq=(1400, 4500))
    # pingos mais graves e espaçados (água caindo de folhas/telhado)
    respingos = gotas(n, rng, por_segundo=0.6 + 2 * intensidade, volume=0.12,
                      freq=(450, 1200), duracao_ms=(8, 25))
    mistura = base + filtro(pingos, "highpass", 1000) + respingos
    mistura = filtro(mistura, "lowpass", 7000)  # tira o 'brilho' digital
    return normalizar(reverb(mistura, rng, segundos=0.5, mistura=0.15), 0.8)


def chuva_fraca(segundos, semente=1):
    return chuva(segundos, semente, 0.25)


def chuva_media(segundos, semente=2):
    return chuva(segundos, semente, 0.7)


# ---------------------------------------------------------------- vento e pássaros
def vento(n, rng):
    marrom = ruido_marrom(n, rng)
    rajadas = ondulacao(n, rng, freq_max=0.12, minimo=0.25, maximo=1.0)
    # sem os graves profundos (< 80 Hz): no celular viram só 'ronco' e somem
    grave = filtro(marrom, "bandpass", (80, 600)) * rajadas
    corpo = filtro(ruido_branco(n, rng), "bandpass", (150, 900)) * rajadas * 0.10
    # 'assobio' do vento: faixa média que acompanha as rajadas mais fortes
    assobio = filtro(ruido_branco(n, rng), "bandpass", (400, 1200)) * (rajadas**3) * 0.05
    # folhas balançando: chiado suave, só nas rajadas
    folhas = filtro(ruido_branco(n, rng), "bandpass", (2000, 6000)) * (rajadas**4) * 0.025
    v = normalizar(grave + corpo, 0.6) + assobio + folhas
    return v.astype(np.float32)


def silaba(dur, f0, f1, forma="linear", vibrato=0.0, vib_freq=0.0):
    t = np.arange(int(dur * TAXA)) / TAXA
    p = t / dur
    if forma == "curva":
        p = np.sin(p * np.pi / 2)
    f = f0 + (f1 - f0) * p
    if vibrato:
        f = f + vibrato * np.sin(2 * np.pi * vib_freq * t)
    fase = 2 * np.pi * np.cumsum(f) / TAXA
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return ((np.sin(fase) + 0.15 * np.sin(2 * fase)) * env).astype(np.float32)


def canto(especie, rng):
    """Frases de 4 'espécies' inventadas, com variação a cada canto."""
    var = rng.uniform(0.92, 1.08)
    partes = []
    if especie == 0:  # assobio descendente, 2-3 vezes ("piu piu")
        for _ in range(rng.integers(2, 4)):
            partes += [silaba(0.13, 4600 * var, 3100 * var, "curva"), np.zeros(int(0.12 * TAXA))]
    elif especie == 1:  # trinado rápido
        for i in range(rng.integers(8, 16)):
            partes += [silaba(0.028, 5000 * var, 5600 * var), np.zeros(int(0.03 * TAXA))]
    elif especie == 2:  # duas notas "fi-uu"
        partes += [silaba(0.16, 3000 * var, 4300 * var, "curva"), np.zeros(int(0.05 * TAXA)),
                   silaba(0.30, 4200 * var, 2700 * var, "curva")]
    else:  # gorjeio com vibrato
        partes += [silaba(rng.uniform(0.35, 0.6), 3400 * var, 3900 * var, vibrato=500, vib_freq=28)]
    return np.concatenate(partes)


def passaros(n, rng, quantidade=5):
    saida = np.zeros((n, 2), dtype=np.float32)
    for ave in range(quantidade):
        especie = ave % 4
        lado = rng.uniform(0.1, 0.9)
        distancia = rng.uniform(0.25, 1.0)  # 1 = perto
        t = rng.uniform(0, 6)
        while t < n / TAXA - 2:
            som = canto(especie, rng) * 0.35 * distancia
            ini = int(t * TAXA)
            fim = min(n, ini + len(som))
            saida[ini:fim, 0] += som[: fim - ini] * (1 - lado)
            saida[ini:fim, 1] += som[: fim - ini] * lado
            t += rng.uniform(4, 14)  # cada ave canta de tempos em tempos
    saida = filtro(saida, "lowpass", 9000)
    return reverb(saida, rng, segundos=1.2, mistura=0.35)


def vento_passaros(segundos, semente=3):
    rng = np.random.default_rng(semente)
    n = int(segundos * TAXA)
    return normalizar(vento(n, rng) * 0.8 + passaros(n, rng) * 1.0, 0.8)


SONS = {"chuva_fraca": chuva_fraca, "chuva_media": chuva_media, "vento_passaros": vento_passaros}


# ---------------------------------------------------------------- arquivos
def salvar_wav(x, destino):
    wavfile.write(destino, TAXA, (np.clip(x, -1, 1) * 32767).astype(np.int16))


def gerar(nome, segundos, destino, semente=None):
    """Gera em blocos de 60 s com transição suave entre eles (para não ocupar muita memória)."""
    funcao = SONS[nome]
    bloco, cruz = 60.0, 2.0
    partes, i = [], 0
    feito = 0.0
    while feito < segundos:
        dur = min(bloco, segundos - feito) + cruz
        partes.append(funcao(dur, (semente or 0) * 1000 + i))
        feito += dur - cruz
        i += 1
    nc = int(cruz * TAXA)
    rampa = np.linspace(0, 1, nc, dtype=np.float32)[:, None]
    resultado = partes[0]
    for p in partes[1:]:
        junta = resultado[-nc:] * (1 - rampa) + p[:nc] * rampa
        resultado = np.concatenate([resultado[:-nc], junta, p[nc:]])
    resultado = resultado[: int(segundos * TAXA)]
    salvar_wav(resultado, destino)
    return destino


def amostras():
    pasta = RAIZ / "saida" / "amostras-sons"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in SONS:
        wav = pasta / f"{nome}.wav"
        gerar(nome, 30, wav, semente=7)
        mp3 = pasta / f"{nome}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                        "-af", "afade=t=in:d=1,afade=t=out:st=28:d=2", "-b:a", "192k", str(mp3)], check=True)
        wav.unlink()
        print("amostra:", mp3.relative_to(RAIZ), flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["amostras"]:
        amostras()
    elif len(sys.argv) == 4:
        gerar(sys.argv[1], float(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(__doc__)
