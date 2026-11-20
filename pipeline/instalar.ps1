# Instalador do video-creator (chamado pelo "Instalar.bat").
# Instala o que faltar (Node.js, Python, ffmpeg, Git) com o winget, baixa as dependências,
# liga as atualizações automáticas e abre o painel. Pode rodar de novo quando quiser: o que já
# está instalado é pulado.
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$repo = "https://github.com/IngridSlytherin/video-creator.git"

function Passo($n, $texto) { Write-Host ""; Write-Host "[$n/6] $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "  OK  $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "  !!  $texto" -ForegroundColor Yellow }
function Recarregar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}
function Tem($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Python-Ok {
    # O Windows tem um "python" falso que só abre a Microsoft Store: confere a versão de verdade.
    try { & python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null; return $LASTEXITCODE -eq 0 }
    catch { return $false }
}
function Instalar($id, $nome) {
    Write-Host "  Instalando $nome (pode levar alguns minutos; se o Windows pedir permissão, clique em Sim)..."
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements | Out-Host
    Recarregar-Path
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Instalador do gerador de vídeos" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

Passo 1 "Programas necessários"
if (-not (Tem "winget")) {
    Aviso "Não achei o winget (instalador de programas do Windows)."
    Aviso "Abra a Microsoft Store, procure 'Instalador de Aplicativo' (App Installer), instale e rode este instalador de novo."
    Read-Host "Aperte Enter para fechar"; exit 1
}
if (Tem "node") { Ok "Node.js" } else { Instalar "OpenJS.NodeJS.LTS" "Node.js" }
if (Python-Ok) { Ok "Python" } else { Instalar "Python.Python.3.13" "Python" }
if (Tem "ffmpeg") { Ok "ffmpeg" } else { Instalar "Gyan.FFmpeg" "ffmpeg" }
if (Tem "git") { Ok "Git" } else { Instalar "Git.Git" "Git" }
Recarregar-Path
$faltam = @()
if (-not (Tem "node")) { $faltam += "Node.js" }
if (-not (Python-Ok)) { $faltam += "Python" }
if (-not (Tem "ffmpeg")) { $faltam += "ffmpeg" }
if ($faltam.Count) {
    Aviso ("Ainda não achei: " + ($faltam -join ", ") + ". Feche esta janela, reinicie o computador e rode o Instalar.bat de novo.")
    Read-Host "Aperte Enter para fechar"; exit 1
}

Passo 2 "Atualizações automáticas"
if (Test-Path ".git") { Ok "já ligadas" }
elseif (Tem "git") {
    # Baixou como .zip: transforma a pasta numa cópia do GitHub (os arquivos continuam os mesmos),
    # para o botão "Atualizar agora" do painel funcionar.
    git init -q; git remote add origin $repo 2>$null
    git fetch -q origin main
    if ($LASTEXITCODE -eq 0) { git reset -q origin/main; git branch -q -M main; git branch -q -u origin/main 2>$null; Ok "ligadas" }
    else { Aviso "não consegui falar com o GitHub agora; o app funciona, só não vai avisar das versões novas" }
} else { Aviso "sem o Git, o painel não consegue se atualizar sozinho" }

Passo 3 "Peças da montagem de vídeo (npm install)"
npm install --no-audit --no-fund | Out-Host
if ($LASTEXITCODE -eq 0) { Ok "pronto" } else { Aviso "deu erro no npm install; rode o Instalar.bat de novo" }

Passo 4 "Peças do Python (voz, radar, transcrição, animações)"
python -m pip install --disable-pip-version-check -q -r requirements.txt | Out-Host
python -I -c "import edge_tts, requests, numpy, scipy" 2>$null
if ($LASTEXITCODE -ne 0) { python -s -m pip install --disable-pip-version-check -q -r requirements.txt | Out-Host }
python -I -c "import edge_tts, requests, numpy, scipy" 2>$null
if ($LASTEXITCODE -eq 0) { Ok "pronto" } else { Aviso "faltou alguma peça do Python; rode o Instalar.bat de novo" }

Passo 5 "Configurações"
if (-not (Test-Path ".env")) { Copy-Item ".env.exemplo" ".env"; Ok ".env criado (a chave do Pexels você cola no painel)" }
else { Ok ".env já existe" }
if (Tem "claude") { Ok "Claude Code encontrado" }
elseif (Get-ChildItem "$env:LOCALAPPDATA\Claude-Data\*\claude-code\*\*\claude.exe" -ErrorAction SilentlyContinue) { Ok "Claude Code (do app do Claude) encontrado" }
else { Aviso "Claude Code não encontrado: o app funciona, mas ideias, roteiros e cortes precisam dele (claude.com/claude-code)" }

Passo 6 "Tudo pronto!"
Write-Host ""
Write-Host "  Daqui pra frente, abra o app com dois cliques em 'Abrir painel.bat'." -ForegroundColor Green
Write-Host "  Na primeira vez, o painel pede o nome do canal e a chave do Pexels." -ForegroundColor Green
Write-Host ""
$r = Read-Host "Abrir o painel agora? (Enter = sim, n = não)"
if ($r -ne "n") { Start-Process -FilePath (Join-Path $raiz "Abrir painel.bat") -WorkingDirectory $raiz }
