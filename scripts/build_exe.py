# -*- coding: utf-8 -*-
"""
GERA O EXECUTAVEL WINDOWS.

MODO: `--onedir`, e a escolha nao e de conveniencia
------------------------------------------------------
`--onefile` empacota tudo num arquivo so e, a CADA execucao, extrai o conteudo
para uma pasta temporaria. Com 70 MB de banco de conhecimento isso significa
copiar 70 MB toda vez que o farmaceutico abre o programa — segundos de espera
no balcao, e um pico de disco que nada justifica.

`--onedir` produz uma pasta. O que ela da, e que este projeto precisa:

  ATUALIZACAO   trocar `conhecimento/conhecimento.db` nao exige regerar o
                `.exe` — que e exatamente o requisito da Fase 10
  DIAGNOSTICO   quando algo falha, os arquivos estao la para olhar; num
                `--onefile` estao dentro de um temporario que ja sumiu
  PARTIDA       sem extracao, o programa abre imediatamente
  ANTIVIRUS     executavel auto-extrator de 70 MB e o perfil classico de
                falso positivo em antivirus corporativo

CONSOLE, NAO JANELA
-------------------
`--console`. Um programa local de apoio clinico precisa poder dizer o que deu
errado; `--noconsole` engole toda saida e um erro de partida vira uma janela
que pisca. O console tambem mostra o endereco e a limitacao clinica a cada
abertura.

O QUE NAO ENTRA NO PACOTE
-------------------------
  pipeline/   reconstroi o banco a partir do acervo, que nao e distribuido
  ml/         treino e medicao; o motor le a view, nao roda modelo
  tests/      nao sao produto
  auditoria/  le o acervo
  docs/       exceto o guia de instalacao
  *.pkl       o motor nao abre artefato de modelo (Fase 8)

Uso: python scripts/build_exe.py [--limpar]
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))
import versao as ver                                       # noqa: E402

NOME = "SistemaConciliador"
DIST = RAIZ / "dist"
BUILD = RAIZ / "build"
ENTRADA = RAIZ / "app" / "principal.py"
CONHECIMENTO = RAIZ / "conhecimento" / "conhecimento.db"


def carimbar_data_build(valor: str) -> str:
    """Escreve DATA_BUILD em app/versao.py e devolve o conteudo anterior."""
    p = RAIZ / "app" / "versao.py"
    antes = p.read_text(encoding="utf-8")
    p.write_text(antes.replace('DATA_BUILD = ""', 'DATA_BUILD = "%s"' % valor),
                 encoding="utf-8")
    return antes


def main() -> int:
    print("=" * 74)
    print("BUILD — %s %s" % (ver.NOME, ver.APLICACAO))
    print("=" * 74)

    if not CONHECIMENTO.exists():
        print("O conhecimento para distribuição não existe.")
        print("Rode antes:  python scripts/preparar_conhecimento.py")
        return 1

    if "--limpar" in sys.argv:
        for d in (DIST, BUILD):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        print("dist/ e build/ removidos")

    sep = ";" if os.name == "nt" else ":"
    dados = [
        (RAIZ / "app" / "templates", "app/templates"),
        (RAIZ / "app" / "static", "app/static"),
        (RAIZ / "conhecimento", "conhecimento"),
        (RAIZ / "models" / "espaco_features.json", "models"),
        (RAIZ / "models" / "calibrador_m1.json", "models"),
        (RAIZ / "models" / "m1_1_0-boosting.json", "models"),
        (RAIZ / "models" / "m1_1_0-logistica.json", "models"),
        (RAIZ / "docs" / "GUIA_INSTALACAO.md", "docs"),
    ]
    faltando = [str(o) for o, _d in dados if not o.exists()]
    if faltando:
        print("arquivos que o build precisa e não existem:")
        for f in faltando:
            print("  ", f)
        return 1

    argumentos = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--console",
        "--name", NOME,
        "--distpath", str(DIST), "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--paths", str(RAIZ / "app"),
        "--paths", str(RAIZ / "rules"),
        "--paths", str(RAIZ / "pipeline"),
        # Modulos alcancados por sys.path em tempo de execucao, que o
        # analisador estatico do PyInstaller nao enxerga.
        "--hidden-import", "motor_conciliacao",
        "--hidden-import", "motor_horarios",
        "--hidden-import", "_prioridade",
        "--hidden-import", "normalizacao",
        "--hidden-import", "servicos", "--hidden-import", "busca",
        "--hidden-import", "relatorio", "--hidden-import", "rotulos",
        "--hidden-import", "caminhos", "--hidden-import", "instalacao",
        "--hidden-import", "versao", "--hidden-import", "web",
        "--hidden-import", "traducao_interacao",
        "--hidden-import", "traducao_atc",
        # Nada de ML no executavel: o motor le a view `vw_predicao_liberada`,
        # nao carrega modelo. E o que mantem o pacote leve (Fase 8).
        "--exclude-module", "numpy", "--exclude-module", "scipy",
        "--exclude-module", "sklearn", "--exclude-module", "pandas",
        "--exclude-module", "matplotlib", "--exclude-module", "PIL",
        "--exclude-module", "tkinter", "--exclude-module", "pytest",
        "--exclude-module", "openpyxl", "--exclude-module", "PyInstaller",
    ]
    for origem, destino in dados:
        argumentos += ["--add-data", "%s%s%s" % (origem, sep, destino)]
    argumentos.append(str(ENTRADA))

    carimbo = datetime.now().strftime("%Y-%m-%d %H:%M")
    antes = carimbar_data_build(carimbo)
    print("carimbo de build: %s\n" % carimbo)
    t0 = time.time()
    try:
        r = subprocess.run(argumentos, cwd=str(RAIZ))
    finally:
        (RAIZ / "app" / "versao.py").write_text(antes, encoding="utf-8")
    if r.returncode != 0:
        print("\nPyInstaller falhou (código %d)." % r.returncode)
        return 1

    pasta = DIST / NOME
    exe = pasta / ("%s.exe" % NOME)
    if not exe.exists():
        print("\nO executável não foi produzido em %s" % exe)
        return 1
    total = sum(p.stat().st_size for p in pasta.rglob("*") if p.is_file())
    n = sum(1 for p in pasta.rglob("*") if p.is_file())
    print("\n" + "=" * 74)
    print("BUILD CONCLUIDO em %.0fs" % (time.time() - t0))
    print("  executável:  %s (%.1f MB)" % (exe, exe.stat().st_size / 1024 ** 2))
    print("  pasta:       %s" % pasta)
    print("  conteúdo:    %d arquivo(s), %.1f MB" % (n, total / 1024 ** 2))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
