# -*- coding: utf-8 -*-
"""
SIGNIFICANCIA — a diferenca entre duas familias e real ou e ruido?

POR QUE ESTE SCRIPT EXISTE
--------------------------
A regra de desempate da fase fixou "diferenca de AUC menor que 0,02 e empate".
Esse numero foi escolhido antes de ver resultado, o que e correto, mas e
arbitrario: com 10 mil pares no teste FRIO_FRIO, 0,02 pode ser muito ou pouco.
Aqui isso e medido em vez de arbitrado.

METODO — bootstrap PAREADO
--------------------------
Reamostra os MESMOS pares de teste para as duas familias ao mesmo tempo e mede
a diferenca de AUC em cada reamostragem. O intervalo de 95% dessa diferenca
responde a pergunta certa: "se eu tivesse outro conjunto de farmacos novos, a
familia A continuaria a frente?". Bootstrap nao pareado responde uma pergunta
mais fraca e costuma exagerar a incerteza.

Se o intervalo da diferenca contem zero, a vantagem NAO esta estabelecida, e
a regra §1 da especificacao manda ficar com a mais simples.

Saida: ml/saida/45_significancia.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import TREINO, conectar, gravar, linha, rng, secao, titulo, versao_dados
from _features import carregar_contexto, construir
from _modelos import (Dados, Floresta, GradientBoosting, Logistica,
                      TabelaClasseClasse)

BLOCOS = ("ATC", "REG", "ADM", "PK")
CANDIDATOS = [TabelaClasseClasse, Logistica, Floresta, GradientBoosting]
N_BOOT = 1000


def bootstrap_auc(y, preds: dict, n_boot: int, semente: int):
    """AUC de cada modelo e diferencas, sobre a MESMA reamostragem."""
    g = np.random.default_rng(semente)
    nomes = list(preds)
    n = len(y)
    guardado = {k: [] for k in nomes}
    idx_pos = np.flatnonzero(y == 1)
    idx_neg = np.flatnonzero(y == 0)
    for _ in range(n_boot):
        # reamostragem estratificada: mantem a prevalencia da amostra
        ii = np.concatenate([g.choice(idx_pos, len(idx_pos), replace=True),
                             g.choice(idx_neg, len(idx_neg), replace=True)])
        yb = y[ii]
        for k in nomes:
            guardado[k].append(roc_auc_score(yb, preds[k][ii]))
    return {k: np.array(v) for k, v in guardado.items()}


def ic(v):
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def main() -> int:
    con = conectar()
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    regime, frieza = d["regime_farmaco"], d["frieza"]
    pares = list(zip(a_id.tolist(), b_id.tolist()))
    atc = {s: c for s, c in con.execute(
        "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
    r = {"versao_dados": versao_dados(con), "n_bootstrap": N_BOOT}

    titulo("SIGNIFICANCIA DA DIFERENCA ENTRE FAMILIAS")
    tr = regime == 0
    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    X = construir(ctx, pares, BLOCOS)
    dtr = Dados(X[tr], y[tr], [pares[i] for i in np.flatnonzero(tr)], ctx, atc)

    modelos = {}
    for Fam in CANDIDATOS:
        f = Fam()
        f.treinar(dtr)
        modelos[f.nome] = f
        print("  treinado: %s" % f.nome)

    for nome_conj, m in (("teste (todos os regimes)", regime == 2),
                         ("teste FRIO_FRIO", (regime == 2) & (frieza == 2))):
        secao(nome_conj)
        dd = Dados(X[m], y[m], [pares[i] for i in np.flatnonzero(m)], ctx, atc)
        preds = {k: f.prever(dd) for k, f in modelos.items()}
        linha("pares", int(m.sum()), "positivos %d" % int(y[m].sum()))
        boot = bootstrap_auc(dd.y, preds, N_BOOT, 20260909)
        print("\n  %-26s %8s   IC 95%%" % ("familia", "AUC"))
        for k in modelos:
            lo, hi = ic(boot[k])
            print("  %-26s %8.4f   [%.4f ; %.4f]"
                  % (k, roc_auc_score(dd.y, preds[k]), lo, hi))
        print("\n  DIFERENCAS PAREADAS (A - B), IC 95%:")
        chaves = list(modelos)
        difs = []
        for i in range(len(chaves)):
            for j in range(i + 1, len(chaves)):
                a, b = chaves[i], chaves[j]
                dv = boot[a] - boot[b]
                lo, hi = ic(dv)
                contem_zero = lo <= 0 <= hi
                print("  %-24s - %-24s %+7.4f  [%+.4f ; %+.4f]  %s"
                      % (a[:24], b[:24], dv.mean(), lo, hi,
                         "EMPATE (IC contem zero)" if contem_zero
                         else "diferenca estabelecida"))
                difs.append(dict(a=a, b=b, media=float(dv.mean()),
                                 ic_baixo=lo, ic_alto=hi,
                                 empate=bool(contem_zero)))
        r[nome_conj] = dict(
            n=int(m.sum()), positivos=int(y[m].sum()),
            auc={k: float(roc_auc_score(dd.y, preds[k])) for k in modelos},
            ic={k: list(ic(boot[k])) for k in modelos},
            diferencas=difs)

    print("""
  COMO ISTO ENTRA NA DECISAO: onde o intervalo da diferenca contem zero, a
  vantagem nao esta estabelecida com este tamanho de amostra, e a
  especificacao §1 manda preferir a familia mais simples. Onde nao contem, a
  diferenca e real e precisa ser pesada contra custo e interpretabilidade —
  nao adotada automaticamente.""")

    gravar("45_significancia.json", r)
    print("\nGravado: ml/saida/45_significancia.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
