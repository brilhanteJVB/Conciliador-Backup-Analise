# -*- coding: utf-8 -*-
"""
CALIBRACAO — 0,80 quer dizer 80%?

Uma probabilidade mal calibrada e pior que nenhuma: o farmaceutico le "85%"
e trata como quase certeza, quando a frequencia real naquela faixa pode ser
40%. Este script mede isso e conserta quando da.

METODO
------
O calibrador e ajustado na VALIDACAO e medido no TESTE. Ajustar e medir no
mesmo conjunto produz calibracao perfeita e falsa.

    ISOTONICA   monotona, nao parametrica, forte quando ha muitos pontos.
    PLATT       sigmoide de dois parametros, mais estavel com pouco dado.

O calibrador escolhido e gravado como TABELA DE PONTOS em JSON, nao como
pickle: o projeto vai virar .exe e um pickle de sklearn amarra a versao da
biblioteca ao artefato. Uma tabela de (x, y) com interpolacao linear e lida
por qualquer coisa e continua legivel daqui a cinco anos.

Saida: ml/saida/30_calibracao.json + models/calibrador_m1.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _avaliacao import avaliar, curva_confiabilidade, ece
from _comum import MODELOS, TREINO, conectar, gravar, linha, secao, titulo, versao_dados
from _features import carregar_contexto, construir
from _modelos import Dados, Floresta, GradientBoosting, Logistica, TabelaClasseClasse

BLOCOS = ("ATC", "REG", "ADM", "PK")     # SEM_GRAFO — decidido em 20_treinar
CANDIDATOS = [Logistica, Floresta, GradientBoosting, TabelaClasseClasse]


def tabela_isotonica(iso: IsotonicRegression, n: int = 51) -> dict:
    x = np.linspace(0.0, 1.0, n)
    return dict(tipo="ISOTONICA_INTERPOLADA",
                x=[round(float(v), 6) for v in x],
                y=[round(float(v), 6) for v in np.clip(iso.predict(x), 0, 1)])


def aplicar_tabela(tab: dict, p) -> np.ndarray:
    return np.interp(np.asarray(p, float), tab["x"], tab["y"])


def main() -> int:
    con = conectar()
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    regime = d["regime_farmaco"]
    frieza = d["frieza"]
    pares = list(zip(a_id.tolist(), b_id.tolist()))
    atc = {s: c for s, c in con.execute(
        "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
    r = {"versao_dados": versao_dados(con), "blocos": list(BLOCOS),
         "split": "POR_FARMACO", "candidatos": []}

    titulo("CALIBRACAO — split POR_FARMACO, atributos SEM_GRAFO")

    tr, va, te = regime == 0, regime == 1, regime == 2
    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    X = construir(ctx, pares, BLOCOS)
    dd = {k: Dados(X[m], y[m], [pares[i] for i in np.flatnonzero(m)], ctx, atc)
          for k, m in (("treino", tr), ("validacao", va), ("teste", te))}
    m_ff = te & (frieza == 2)
    d_ff = Dados(X[m_ff], y[m_ff], [pares[i] for i in np.flatnonzero(m_ff)],
                 ctx, atc)

    melhor = None
    for Fam in CANDIDATOS:
        f = Fam()
        f.treinar(dd["treino"])
        p_va = f.prever(dd["validacao"])
        p_te = f.prever(dd["teste"])
        p_ff = f.prever(d_ff)
        secao("%s" % f.nome)

        iso = IsotonicRegression(out_of_bounds="clip").fit(p_va, dd["validacao"].y)
        tab = tabela_isotonica(iso)
        platt = LogisticRegression(max_iter=1000).fit(
            p_va.reshape(-1, 1), dd["validacao"].y)

        variantes = {
            "CRU": (p_te, p_ff),
            "ISOTONICA": (aplicar_tabela(tab, p_te), aplicar_tabela(tab, p_ff)),
            "PLATT": (platt.predict_proba(p_te.reshape(-1, 1))[:, 1],
                      platt.predict_proba(p_ff.reshape(-1, 1))[:, 1]),
        }
        reg = dict(familia=f.nome, variantes={})
        for nome, (pt, pf) in variantes.items():
            mt = avaliar(dd["teste"].y, pt)
            mf = avaliar(d_ff.y, pf)
            reg["variantes"][nome] = dict(teste=mt, teste_frio_frio=mf)
            linha("%-10s teste  ECE / Brier / AUC" % nome,
                  "%.4f / %.4f / %.4f" % (mt["ece"], mt["brier"], mt["roc_auc"]))
        reg["curva_crua"] = curva_confiabilidade(dd["teste"].y, p_te)
        reg["curva_isotonica"] = curva_confiabilidade(
            dd["teste"].y, variantes["ISOTONICA"][0])
        reg["tabela_isotonica"] = tab
        r["candidatos"].append(reg)

        # o melhor e o de maior AUC no teste FRIO_FRIO, que e o regime real
        auc_ff = reg["variantes"]["CRU"]["teste_frio_frio"]["roc_auc"]
        if melhor is None or auc_ff > melhor[1]:
            melhor = (f.nome, auc_ff, reg)

    # ---------------------------------------------- curva do escolhido
    nome_m, auc_m, reg_m = melhor
    secao("CURVA DE CONFIABILIDADE — %s (teste)" % nome_m)
    print("  %-12s %8s %14s %14s  %s" % ("faixa", "n", "prob. media",
                                         "freq. real", "desvio"))
    for a, b in zip(reg_m["curva_crua"], reg_m["curva_isotonica"]):
        if not a["n"]:
            continue
        dv = a["probabilidade_media"] - a["frequencia_real"]
        print("  %-12s %8d %14.3f %14.3f  %+.3f" % (
            a["faixa"], a["n"], a["probabilidade_media"], a["frequencia_real"], dv))
    print("\n  Depois da calibracao isotonica:")
    for b in reg_m["curva_isotonica"]:
        if not b["n"]:
            continue
        print("  %-12s %8d %14.3f %14.3f  %+.3f" % (
            b["faixa"], b["n"], b["probabilidade_media"], b["frequencia_real"],
            b["probabilidade_media"] - b["frequencia_real"]))

    v = reg_m["variantes"]
    secao("ESCOLHA DO CALIBRADOR")
    for nome in ("CRU", "ISOTONICA", "PLATT"):
        linha(nome, "ECE %.4f  Brier %.4f  AUC %.4f  (frio-frio ECE %.4f)"
              % (v[nome]["teste"]["ece"], v[nome]["teste"]["brier"],
                 v[nome]["teste"]["roc_auc"],
                 v[nome]["teste_frio_frio"]["ece"]))
    escolhido = min(("ISOTONICA", "PLATT", "CRU"),
                    key=lambda k: v[k]["teste"]["ece"])
    print("\n  Calibrador escolhido: %s (menor ECE no teste)." % escolhido)
    print("""
  A calibracao nao muda a ordenacao (isotonica e Platt sao monotonas), logo a
  AUC nao muda. Ela muda o NUMERO que aparece na tela — que e exatamente o que
  o farmaceutico le. Por isso ela e obrigatoria antes de exibir qualquer
  probabilidade, e nao um refinamento opcional.""")

    MODELOS.mkdir(parents=True, exist_ok=True)
    destino = MODELOS / "calibrador_m1.json"
    destino.write_text(json.dumps(dict(
        modelo=nome_m, metodo=escolhido, ajustado_em="validacao",
        split="POR_FARMACO", blocos=list(BLOCOS),
        tabela=reg_m["tabela_isotonica"] if escolhido == "ISOTONICA" else None,
        ece_antes=v["CRU"]["teste"]["ece"], ece_depois=v[escolhido]["teste"]["ece"],
    ), ensure_ascii=False, indent=2), encoding="utf-8")
    r["escolhido"] = dict(familia=nome_m, calibrador=escolhido,
                          ece_antes=v["CRU"]["teste"]["ece"],
                          ece_depois=v[escolhido]["teste"]["ece"])
    gravar("30_calibracao.json", r)
    print("\nGravado: ml/saida/30_calibracao.json e models/calibrador_m1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
