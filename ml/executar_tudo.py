# -*- coding: utf-8 -*-
"""
EXECUTA A FASE 7 INTEIRA, NA ORDEM, e para no primeiro erro.

A ordem nao e cosmetica: a auditoria do dataset roda antes da auditoria dos
rotulos, que roda antes da construcao do dataset, que roda antes de qualquer
treino. Um alvo so entra depois de aparecer numa auditoria com numero ao lado.

    python ml/executar_tudo.py            # tudo (~20 min)
    python ml/executar_tudo.py --rapido   # pula o que leva minutos
    python ml/executar_tudo.py --so-verificacao

TEMPO: o gargalo e 20_treinar.py (40 execucoes, floresta e boosting sobre
320 mil linhas). O resto soma menos de tres minutos.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ETAPAS = [
    ("ml/_features.py", "autoteste do espaco de atributos", False),
    ("ml/01_auditoria_dataset.py", "auditoria do dataset", False),
    ("ml/02_auditoria_rotulos.py", "auditoria dos rotulos", False),
    ("ml/10_dataset.py", "dataset e splits", False),
    ("ml/20_treinar.py", "comparacao das 10 familias (LENTO)", True),
    ("ml/25_robustez.py", "robustez, controle negativo, precisao no topo", True),
    ("ml/45_significancia.py", "bootstrap pareado das diferencas", True),
    ("ml/30_calibracao.py", "calibracao", True),
    ("ml/40_explicabilidade.py", "explicabilidade", True),
    ("ml/50_comparacao.py", "tabela de comparacao e decisao", False),
    ("ml/60_registrar_modelo.py", "registro do modelo no banco", True),
    ("ml/80_fila_curadoria.py", "fila de curadoria priorizada", True),
]

VERIFICACOES = [
    ("ml/70_predizer.py", "contrato de previsao (autoteste)", ("--autoteste",)),
    ("ml/91_v1_pipeline.py", "V1 — validacao do pipeline", ()),
    ("ml/92_v2_independente.py", "V2 — verificacao independente", ()),
    ("tests/teste_ml.py", "regressao das garantias de ML", ()),
]


def roda(rel, desc, extra=()):
    print("\n" + "=" * 74)
    print(">> %s  —  %s" % (rel, desc))
    print("=" * 74, flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(RAIZ / rel), *extra], cwd=str(RAIZ))
    print("   (%.1fs)" % (time.time() - t0), flush=True)
    return r.returncode == 0


def main() -> int:
    rapido = "--rapido" in sys.argv
    so_ver = "--so-verificacao" in sys.argv
    if not so_ver:
        for rel, desc, lento in ETAPAS:
            if rapido and lento:
                print("\n(pulado por --rapido: %s)" % rel)
                continue
            if not roda(rel, desc):
                print("\nFASE 7 INTERROMPIDA em %s" % rel)
                return 1
    print("\n\n" + "#" * 74)
    print("# VERIFICACAO — V1, V2 e regressao")
    print("#" * 74)
    falhou = [rel for rel, desc, extra in VERIFICACOES
              if not roda(rel, desc, extra)]
    print("\n" + "=" * 74)
    if falhou:
        print("VERIFICACOES COM FALHA: %s" % ", ".join(falhou))
        return 1
    print("FASE 7 COMPLETA — medida, verificada duas vezes e sem regressao")
    return 0


if __name__ == "__main__":
    sys.exit(main())
