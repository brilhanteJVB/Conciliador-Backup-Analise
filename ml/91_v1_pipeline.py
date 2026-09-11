# -*- coding: utf-8 -*-
"""
V1 — VALIDACAO DO PIPELINE.

Confere que cada peca faz o que diz, usando a mesma metodologia do pipeline.
E a primeira das duas verificacoes exigidas pela disciplina do projeto; a
segunda (92) tenta achar o erro por outro caminho.

O QUE E CONFERIDO
-----------------
    1  dataset      o .npz corresponde ao banco, par por par
    2  rotulo       y=1 exatamente onde existe linha em interacao_substancia
    3  split        particao completa, disjunta, e sem farmaco em dois grupos
    4  atributos    largura, simetria, e bloco de grafo zerado fora do treino
    5  treino       mesma semente -> previsao identica (determinismo)
    6  metricas     as gravadas em `modelo` batem com o recalculo
    7  persistencia artefato salvo e recarregado da a MESMA previsao
    8  inferencia   o Preditor concorda com o modelo em memoria

Sai 1 se qualquer conferencia falhar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _artefato import carregar
from _comum import (MODELOS, RAIZ, SEMENTE, TREINO, carregar_predizer,
                    conectar, secao, titulo)
from _features import carregar_contexto, construir, espaco
from _modelos import Dados, GradientBoosting

falhas = []


def ok(desc, cond, detalhe=""):
    print("  [%s] %-58s %s" % ("OK " if cond else "FALHA", desc, detalhe))
    if not cond:
        falhas.append(desc)


def main() -> int:
    con = conectar()
    titulo("V1 — VALIDACAO DO PIPELINE DE ML")
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    regime, frieza = d["regime_farmaco"], d["frieza"]
    grupo = d["grupo_farmaco"]
    subst = d["substancias"]
    pares = list(zip(a_id.tolist(), b_id.tolist()))

    # ------------------------------------------------------------ 1. dataset
    secao("1. DATASET")
    n_sub = len(subst)
    ok("numero de pares == C(n,2)", len(y) == n_sub * (n_sub - 1) // 2,
       "%d pares, %d substancias" % (len(y), n_sub))
    ok("todo par em ordem canonica (a<b)", bool((a_id < b_id).all()))
    ok("nenhum par repetido", len(set(pares)) == len(pares))
    no_banco = set(con.execute("SELECT DISTINCT substancia_a_id, substancia_b_id "
                               "FROM interacao_substancia"))
    ok("positivos do .npz == pares do banco",
       {pares[i] for i in np.flatnonzero(y == 1)} == no_banco,
       "%d positivos" % int(y.sum()))
    conectadas = {s for (s,) in con.execute(
        "SELECT substancia_a_id FROM interacao_substancia "
        "UNION SELECT substancia_b_id FROM interacao_substancia")}
    ok("universo == substancias com >=1 interacao",
       set(subst.tolist()) == conectadas, "%d substancias" % n_sub)
    ok("semente gravada no dataset", int(d["semente"][0]) == SEMENTE,
       str(int(d["semente"][0])))

    # ------------------------------------------------------------- 2. rotulo
    secao("2. ROTULO")
    n_f = d["n_fontes"]
    ok("n_fontes>0 exatamente onde y=1", bool(((n_f > 0) == (y == 1)).all()))
    ok("n_fontes maximo == 2 (duas bases carregadas)", int(n_f.max()) == 2)
    dois = int(con.execute(
        "SELECT COUNT(*) FROM (SELECT substancia_a_id FROM interacao_substancia "
        "GROUP BY substancia_a_id, substancia_b_id HAVING COUNT(*)=2)").fetchone()[0])
    ok("pares com 2 fontes conferem com o banco", int((n_f == 2).sum()) == dois,
       "%d" % dois)
    tipo = d["tipo"]
    ok("rotulo de tipo so existe entre positivos",
       bool((tipo[y == 0] == -1).all()))

    # -------------------------------------------------------------- 3. split
    secao("3. SPLIT")
    sp = d["split_par"]
    ok("split por par cobre tudo e nao se sobrepoe",
       bool(((sp == 0) | (sp == 1) | (sp == 2)).all()))
    ok("split por par: proporcao ~70/15/15",
       abs((sp == 0).mean() - 0.70) < 0.01 and abs((sp == 2).mean() - 0.15) < 0.01,
       "%.3f / %.3f / %.3f" % ((sp == 0).mean(), (sp == 1).mean(), (sp == 2).mean()))
    ok("nenhum farmaco em dois grupos", len(grupo) == n_sub)
    idx = {s: i for i, s in enumerate(subst.tolist())}
    ga = np.array([grupo[idx[a]] for a, _ in pares])
    gb = np.array([grupo[idx[b]] for _, b in pares])
    ok("regime de treino == os dois lados de treino",
       bool((((ga == 0) & (gb == 0)) == (regime == 0)).all()))
    ok("regime de teste == pelo menos um lado de teste",
       bool((((ga == 2) | (gb == 2)) == (regime == 2)).all()))
    ok("FRIO_FRIO == os dois lados de teste",
       bool((((ga == 2) & (gb == 2)) == ((regime == 2) & (frieza == 2))).all()))
    ok("nenhum par de treino toca farmaco de validacao ou teste",
       int(((regime == 0) & ((ga > 0) | (gb > 0))).sum()) == 0)

    # ---------------------------------------------------------- 4. atributos
    secao("4. ATRIBUTOS")
    blocos = ("ATC", "REG", "ADM", "PK")
    tr = regime == 0
    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    nomes = espaco(ctx, blocos)
    amostra = pares[:500]
    X1 = construir(ctx, amostra, blocos)
    ok("largura da matriz == espaco declarado", X1.shape[1] == len(nomes),
       "%d atributos" % len(nomes))
    X2 = construir(ctx, [(b, a) for a, b in amostra], blocos)
    ok("atributos simetricos", bool(np.array_equal(X1, X2)))
    ok("sem NaN/infinito", bool(np.isfinite(X1).all()))
    ok("bloco GRAFO fora do espaco publicado",
       not any(n.startswith("g_") for n in nomes))
    ctx_cheio = carregar_contexto(con, arestas + [(1, 2)], origem_grafo="X")
    ok("grafo do contexto vem so do treino",
       len(ctx.adjacencia) <= len(ctx_cheio.adjacencia),
       "%d substancias no grafo de treino" % len(ctx.adjacencia))

    # ------------------------------------------------------------- 5. treino
    secao("5. TREINO — determinismo")
    X = construir(ctx, pares, blocos)
    dtr = Dados(X[tr], y[tr], [pares[i] for i in np.flatnonzero(tr)], ctx, {})
    te = regime == 2
    dte = Dados(X[te], y[te], [pares[i] for i in np.flatnonzero(te)], ctx, {})
    m1 = GradientBoosting(); m1.treinar(dtr)
    m2 = GradientBoosting(); m2.treinar(dtr)
    p1, p2 = m1.prever(dte), m2.prever(dte)
    ok("dois treinos com a mesma semente dao a mesma previsao",
       bool(np.allclose(p1, p2)),
       "maior diferenca %.2e" % float(np.abs(p1 - p2).max()))

    # ----------------------------------------------------------- 6. metricas
    secao("6. METRICAS GRAVADAS")
    from sklearn.metrics import roc_auc_score
    row = con.execute("SELECT metricas_json, semente, versao_dados, n_features, "
                      "espaco_features_json, status, ativo FROM modelo "
                      "WHERE nome='m1_existencia_interacao' AND versao='1.0-boosting'"
                      ).fetchone()
    ok("modelo registrado no banco", row is not None)
    if row:
        met = json.loads(row[0])
        # A metrica gravada tem de ser reproduzida pelo ARTEFATO PUBLICADO, nao
        # por um treino novo. Sao coisas diferentes: o artefato e o que iria a
        # producao, e e ele que precisa bater com o numero que o registro
        # afirma. Comparar com um retreino escondia uma dessincronizacao real
        # entre `modelo.metricas_json` e o `.pkl` no disco — foi assim que a
        # V1 achou que `60_registrar_modelo.py` nao conseguia re-registrar
        # quando ja havia previsao gravada (FOREIGN KEY), deixando o registro
        # velho ao lado de um artefato novo.
        from _artefato import carregar as _carregar
        p_art = _carregar(MODELOS / "m1_1_0-boosting.json").prever(X=X[te])
        auc_art = roc_auc_score(dte.y, p_art)
        ok("o ARTEFATO publicado reproduz a AUC gravada",
           abs(auc_art - met["teste"]["roc_auc"]) < 1e-9,
           "%.6f vs %.6f" % (auc_art, met["teste"]["roc_auc"]))
        auc_recalc = roc_auc_score(dte.y, p1)
        ok("um treino novo reproduz a AUC gravada",
           abs(auc_recalc - met["teste"]["roc_auc"]) < 1e-9,
           "%.6f vs %.6f" % (auc_recalc, met["teste"]["roc_auc"]))
        ok("semente gravada == semente da fase", row[1] == SEMENTE, str(row[1]))
        ok("n_features gravado == espaco atual", row[3] == len(nomes))
        ok("espaco gravado == espaco atual", json.loads(row[4]) == nomes)
        ok("modelo NAO esta ativo", row[6] == 0, "status=%s" % row[5])

    # ------------------------------------------------------- 7. persistencia
    secao("7. PERSISTENCIA — salvar e recarregar")
    art = MODELOS / "m1_1_0-boosting.json"
    ok("artefato existe", art.exists(), str(art.name))
    if art.exists():
        carregado = carregar(art)
        pl = carregado.prever(X=X[te])
        ok("previsao do artefato recarregado == a do modelo em memoria",
           bool(np.allclose(pl, p1)),
           "maior diferenca %.2e" % float(np.abs(pl - p1).max()))
    esp = MODELOS / "espaco_features.json"
    ok("espaco_features.json existe e confere", esp.exists()
       and json.loads(esp.read_text(encoding="utf-8"))["nomes"] == nomes)
    cal = MODELOS / "calibrador_m1.json"
    ok("calibrador gravado como tabela, nao pickle", cal.exists()
       and json.loads(cal.read_text(encoding="utf-8")).get("tabela") is not None)

    # --------------------------------------------------------- 8. inferencia
    secao("8. INFERENCIA PELO CONTRATO")
    predizer = carregar_predizer()
    p = predizer.Preditor(con)
    alguns = [pares[i] for i in np.flatnonzero(te)[:200]]
    prev = p.prever(alguns, com_explicacao=False)
    Xa = construir(ctx, alguns, blocos)
    p_dir = m1.prever(Dados(Xa, np.zeros(len(alguns), np.int8), alguns, ctx, {}))
    ok("Preditor concorda com o modelo treinado agora",
       bool(np.allclose([x.probabilidade for x in prev], p_dir, atol=1e-9)),
       "200 pares")
    ok("probabilidade calibrada dentro de [0,1]",
       all(0 <= (x.probabilidade_calibrada or 0) <= 1 for x in prev))
    ok("previsao e simetrica",
       bool(np.allclose([x.probabilidade for x in prev],
                        [x.probabilidade for x in
                         p.prever([(b, a) for a, b in alguns],
                                  com_explicacao=False)])))
    try:
        p.contrato_achado(prev[0])
        ok("contrato recusa modelo experimental", False, "aceitou")
    except predizer.ModeloNaoHomologado:
        ok("contrato recusa modelo experimental", True)
    except RuntimeError:
        ok("contrato recusa modelo experimental", False,
           "recusou por outro motivo")

    print("\n" + "=" * 74)
    if falhas:
        print("V1 FALHOU em %d conferencia(s):" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("V1 OK — o pipeline faz o que diz que faz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
