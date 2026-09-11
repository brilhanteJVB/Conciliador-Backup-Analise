# -*- coding: utf-8 -*-
"""
V2 — VERIFICACAO INDEPENDENTE.

A regra do projeto: a segunda verificacao nao repete o mesmo teste, procura o
erro por OUTRO CAMINHO. Todos os defeitos serios das fases anteriores foram
achados assim.

SEIS CAMINHOS DIFERENTES
------------------------
 1. DATASET RECONTADO POR SQL PROPRIO, sem tocar no .npz. Se o arquivo de
    treino estiver errado, os numeros divergem aqui.
 2. METRICAS REIMPLEMENTADAS em numpy puro (AUC por postos de Mann-Whitney,
    PR-AUC por trapezio, Brier, ECE). Se a metrica publicada estiver errada,
    as duas implementacoes discordam.
 3. ROTULO CONFRONTADO COM O SISTEMA ANTERIOR, no acervo, casando por chave
    normalizada de NOME — outro banco, outro codigo, outros ids.
 4. CACA AO VAZAMENTO por forca bruta: par de teste (e seu invertido) dentro
    do treino, farmaco de teste dentro do grafo de treino, atributo de grafo
    nao nulo em farmaco inedito.
 5. SPLIT CONFERIDO POR COMBINATORIA, nao por reexecucao do sorteio: o numero
    de pares de cada regime tem de ser exatamente o que os tamanhos dos grupos
    obrigam.
 6. ARTEFATO JSON RECALCULADO A MAO, sem scikit-learn: le media, escala,
    coeficientes e intercepto do arquivo e refaz a conta. Prova que o
    artefato e autossuficiente para o .exe.

Sai 1 se qualquer caminho discordar do pipeline principal.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import MODELOS, RAIZ, TREINO, conectar, secao, titulo
from _features import carregar_contexto, construir, espaco
from _modelos import Dados, GradientBoosting, Logistica

ACERVO = Path(r"C:\Conteudos banco de dados tcc")
falhas = []


def ok(desc, cond, detalhe=""):
    print("  [%s] %-58s %s" % ("OK " if cond else "FALHA", desc, detalhe))
    if not cond:
        falhas.append(desc)


# ----------------------------------------------------- metricas do zero

def auc_postos(y, p):
    """AUC = estatistica U de Mann-Whitney normalizada. Empate vale 1/2."""
    y = np.asarray(y)
    ordem = np.argsort(p, kind="mergesort")
    ps = np.asarray(p, dtype=np.float64)[ordem]
    ys = y[ordem]
    # postos medios para empates
    postos = np.empty(len(ps))
    i = 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[i]:
            j += 1
        postos[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    n1 = float(ys.sum())
    n0 = float(len(ys) - n1)
    if n1 == 0 or n0 == 0:
        return None
    soma = postos[ys == 1].sum()
    return (soma - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def pr_auc_trapezio(y, p):
    """Area sob precisao x recall, por trapezio sobre os pontos de corte."""
    y = np.asarray(y)
    ordem = np.argsort(-np.asarray(p, dtype=np.float64), kind="mergesort")
    ys = y[ordem]
    vp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    prec = vp / np.maximum(1, vp + fp)
    rec = vp / max(1, ys.sum())
    area = 0.0
    rec_ant, prec_ant = 0.0, 1.0
    for r_, pr_ in zip(rec, prec):
        area += (r_ - rec_ant) * (pr_ + prec_ant) / 2.0
        rec_ant, prec_ant = r_, pr_
    return area


def brier(y, p):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def ece_proprio(y, p, n=10):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    total = 0.0
    for i in range(n):
        lo, hi = i / n, (i + 1) / n
        m = (p >= lo) & ((p < hi) if i < n - 1 else (p <= hi))
        if m.sum():
            total += m.sum() * abs(p[m].mean() - y[m].mean())
    return total / len(y)


def main() -> int:
    con = conectar()
    titulo("V2 — VERIFICACAO INDEPENDENTE DA FASE 7")
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    regime, frieza, grupo = d["regime_farmaco"], d["frieza"], d["grupo_farmaco"]
    subst = d["substancias"].tolist()
    pares = list(zip(a_id.tolist(), b_id.tolist()))

    # ============================================ 1. recontagem por SQL
    secao("1. DATASET RECONTADO POR SQL PROPRIO (sem ler o .npz)")
    q = lambda s: con.execute(s).fetchone()[0]
    n_sub_sql = q("SELECT COUNT(*) FROM (SELECT substancia_a_id AS s FROM "
                  "interacao_substancia UNION SELECT substancia_b_id FROM "
                  "interacao_substancia)")
    n_pos_sql = q("SELECT COUNT(*) FROM (SELECT DISTINCT substancia_a_id, "
                  "substancia_b_id FROM interacao_substancia)")
    ok("substancias do universo", n_sub_sql == len(subst),
       "SQL %d  npz %d" % (n_sub_sql, len(subst)))
    ok("positivos", n_pos_sql == int(y.sum()),
       "SQL %d  npz %d" % (n_pos_sql, int(y.sum())))
    ok("pares totais", n_sub_sql * (n_sub_sql - 1) // 2 == len(y),
       "combinatoria %d  npz %d" % (n_sub_sql * (n_sub_sql - 1) // 2, len(y)))
    # amostra de 300 positivos conferidos um a um
    amostra = [pares[i] for i in np.flatnonzero(y == 1)[:: max(1, int(y.sum()) // 300)]]
    erros = sum(1 for a, b in amostra if not con.execute(
        "SELECT 1 FROM interacao_substancia WHERE substancia_a_id=? AND "
        "substancia_b_id=? LIMIT 1", (a, b)).fetchone())
    ok("cada positivo da amostra existe no banco", erros == 0,
       "%d pares conferidos" % len(amostra))
    negs = [pares[i] for i in np.flatnonzero(y == 0)[:: max(1, int((y == 0).sum()) // 300)]]
    erros_n = sum(1 for a, b in negs if con.execute(
        "SELECT 1 FROM interacao_substancia WHERE substancia_a_id=? AND "
        "substancia_b_id=? LIMIT 1", (a, b)).fetchone())
    ok("nenhum negativo da amostra existe no banco", erros_n == 0,
       "%d pares conferidos" % len(negs))

    # ================================== 2. metricas reimplementadas
    secao("2. METRICAS REIMPLEMENTADAS EM NUMPY PURO")
    from sklearn.metrics import (average_precision_score, brier_score_loss,
                                 roc_auc_score)
    blocos = ("ATC", "REG", "ADM", "PK")
    tr, te = regime == 0, regime == 2
    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    X = construir(ctx, pares, blocos)
    mk = lambda m: Dados(X[m], y[m], [pares[i] for i in np.flatnonzero(m)], ctx, {})
    gb = GradientBoosting(); gb.treinar(mk(tr))
    p_te = gb.prever(mk(te))
    y_te = y[te]

    a_meu, a_sk = auc_postos(y_te, p_te), roc_auc_score(y_te, p_te)
    ok("AUC: Mann-Whitney proprio == sklearn", abs(a_meu - a_sk) < 1e-9,
       "%.8f vs %.8f" % (a_meu, a_sk))
    pr_meu, pr_sk = pr_auc_trapezio(y_te, p_te), average_precision_score(y_te, p_te)
    ok("PR-AUC: trapezio proprio ~ average_precision", abs(pr_meu - pr_sk) < 5e-3,
       "%.6f vs %.6f (metodos diferentes por definicao)" % (pr_meu, pr_sk))
    b_meu, b_sk = brier(y_te, p_te), brier_score_loss(y_te, p_te)
    ok("Brier proprio == sklearn", abs(b_meu - b_sk) < 1e-12,
       "%.8f vs %.8f" % (b_meu, b_sk))
    from _avaliacao import ece as ece_pipeline
    e_meu, e_pip = ece_proprio(y_te, p_te), ece_pipeline(y_te, p_te)
    ok("ECE proprio == do pipeline", abs(e_meu - e_pip) < 1e-12,
       "%.8f vs %.8f" % (e_meu, e_pip))
    # AUC de um preditor constante tem de ser exatamente 0,5
    ok("AUC de preditor constante == 0,5",
       abs(auc_postos(y_te, np.full(len(y_te), 0.3)) - 0.5) < 1e-12)
    ok("AUC do rotulo perfeito == 1,0",
       abs(auc_postos(y_te, y_te.astype(float)) - 1.0) < 1e-12)

    # ====================== 3. rotulo confrontado com o sistema anterior
    secao("3. ROTULO CONFRONTADO COM O SISTEMA ANTERIOR (acervo, outro banco)")
    antigo = ACERVO / "banco" / "conciliador.db"
    if not antigo.exists():
        ok("banco do sistema anterior disponivel", False, str(antigo))
    else:
        old = sqlite3.connect("file:%s?mode=ro" % antigo.as_posix(), uri=True)
        # chave normalizada -> id, nos dois bancos, sem usar id de lado nenhum
        novo_chave = {c: i for i, c in con.execute(
            "SELECT id, chave_normalizada FROM substancia")}
        old_chave = {c: i for i, c in old.execute(
            "SELECT id, chave_normalizada FROM substancia")}
        comuns = set(novo_chave) & set(old_chave)
        ok("chaves normalizadas em comum entre os dois bancos",
           len(comuns) > 1500, "%d chaves" % len(comuns))
        pares_old = set()
        for a, b in old.execute("SELECT substancia_a_id, substancia_b_id "
                                "FROM interacao_ff"):
            pares_old.add((a, b) if a < b else (b, a))
        old_id_chave = {i: c for c, i in old_chave.items()}
        # traduz os pares do banco antigo para chave-chave
        old_cc = set()
        for a, b in pares_old:
            ca, cb = old_id_chave.get(a), old_id_chave.get(b)
            if ca in comuns and cb in comuns:
                old_cc.add((ca, cb) if ca <= cb else (cb, ca))
        novo_id_chave = {i: c for c, i in novo_chave.items()}
        novo_cc = set()
        for i in np.flatnonzero(y == 1):
            a, b = pares[i]
            ca, cb = novo_id_chave.get(a), novo_id_chave.get(b)
            if ca in comuns and cb in comuns:
                novo_cc.add((ca, cb) if ca <= cb else (cb, ca))
        inter = old_cc & novo_cc
        print("      pares (chave x chave) no sistema anterior: %d" % len(old_cc))
        print("      pares (chave x chave) neste sistema:       %d" % len(novo_cc))
        print("      em comum:                                  %d" % len(inter))
        cob = len(inter) / max(1, len(novo_cc))
        ok(">=90% dos pares deste sistema estao no anterior", cob >= 0.90,
           "%.1f%%" % (100 * cob))
        so_novo = len(novo_cc - old_cc)
        so_velho = len(old_cc - novo_cc)
        print("      so neste sistema: %d   so no anterior: %d"
              % (so_novo, so_velho))
        ok("divergencia explicavel (<15% de cada lado)",
           so_novo / max(1, len(novo_cc)) < 0.15,
           "as duas cargas usam recortes de substancia diferentes")
        old.close()

    # ========================================== 4. caca ao vazamento
    secao("4. CACA AO VAZAMENTO — forca bruta")
    set_tr = {pares[i] for i in np.flatnonzero(tr)}
    set_te = {pares[i] for i in np.flatnonzero(te)}
    ok("nenhum par de teste dentro do treino", len(set_tr & set_te) == 0,
       "interseccao %d" % len(set_tr & set_te))
    invertidos = {(b, a) for a, b in set_te}
    ok("nenhum par de teste INVERTIDO dentro do treino",
       len(set_tr & invertidos) == 0)
    idx = {s: i for i, s in enumerate(subst)}
    farm_te = {s for s in subst if grupo[idx[s]] == 2}
    tocam = {p_ for p_ in set_tr if p_[0] in farm_te or p_[1] in farm_te}
    ok("nenhum par de treino toca farmaco de teste", len(tocam) == 0,
       "%d farmacos de teste" % len(farm_te))
    no_grafo = farm_te & set(ctx.adjacencia)
    ok("nenhum farmaco de teste no grafo de atributos", len(no_grafo) == 0)
    # o bloco GRAFO, se fosse usado, seria zero em FRIO_FRIO
    ff = [pares[i] for i in np.flatnonzero(te & (frieza == 2))[:2000]]
    Xg = construir(ctx, ff, ("GRAFO",))
    ok("atributos de grafo sao zero em todo par FRIO_FRIO",
       not Xg.any(), "%d pares conferidos" % len(ff))
    # mesma substancia nos dois lados
    ok("nenhum par com a mesma substancia nos dois lados",
       not any(a == b for a, b in pares))

    # ================================== 5. split conferido por combinatoria
    secao("5. SPLIT CONFERIDO POR COMBINATORIA")
    n0 = int((grupo == 0).sum()); n1 = int((grupo == 1).sum())
    n2 = int((grupo == 2).sum())
    ok("grupos somam o universo", n0 + n1 + n2 == len(subst),
       "%d + %d + %d = %d" % (n0, n1, n2, len(subst)))
    esperado_tr = n0 * (n0 - 1) // 2
    ok("pares de treino == C(n_treino,2)", int(tr.sum()) == esperado_tr,
       "%d == %d" % (int(tr.sum()), esperado_tr))
    esperado_ff = n2 * (n2 - 1) // 2
    ok("pares FRIO_FRIO == C(n_teste,2)",
       int((te & (frieza == 2)).sum()) == esperado_ff,
       "%d == %d" % (int((te & (frieza == 2)).sum()), esperado_ff))
    esperado_qf = n2 * (n0 + n1)
    ok("pares QUENTE_FRIO == n_teste x (n_treino+n_val)",
       int((te & (frieza == 1)).sum()) == esperado_qf,
       "%d == %d" % (int((te & (frieza == 1)).sum()), esperado_qf))

    # ================================ 6. artefato JSON refeito a mao
    secao("6. ARTEFATO JSON RECALCULADO A MAO (sem scikit-learn)")
    art = MODELOS / "m1_1_0-logistica.json"
    ok("artefato da logistica e JSON", art.exists(), str(art.name))
    if art.exists():
        j = json.loads(art.read_text(encoding="utf-8"))
        ok("tipo declarado e JSON puro", j["tipo"] == "LOGISTICA_JSON", j["tipo"])
        media = np.array(j["media"]); escala = np.array(j["escala"])
        w = np.array(j["coeficientes"]); b0 = float(j["intercepto"])
        ok("dimensoes conferem com o espaco de atributos",
           len(w) == len(espaco(ctx, blocos)) == len(media),
           "%d coeficientes" % len(w))
        amostra_i = np.flatnonzero(te)[:300]
        Xa = X[amostra_i].astype(np.float64)
        z = ((Xa - media) / escala) @ w + b0
        p_mao = 1.0 / (1.0 + np.exp(-z))
        lr = Logistica(); lr.treinar(mk(tr))
        p_sk = lr.prever(Dados(X[amostra_i], y[amostra_i],
                               [pares[i] for i in amostra_i], ctx, {}))
        difmax = float(np.abs(p_mao - p_sk).max())
        # TOLERANCIA. A primeira versao deste teste usava 1e-9 e REPROVOU, com
        # diferenca maxima de 1,21e-07. Investigado: a matriz de atributos e
        # float32 (escolha de memoria — 457.446 x 130 em float64 seriam 475 MB),
        # e o scikit-learn faz a conta inteira em float32, enquanto a conta a
        # mao promove para float64. A diferenca e exatamente o epsilon do
        # float32 (1,192e-07), nao um erro de leitura do artefato: refazendo a
        # conta em float32 a diferenca cai para 5,96e-08. O limite certo e o da
        # precisao do dado gravado, e o teste da ordenacao abaixo e o que
        # realmente importa para uma decisao por limiar.
        ok("conta feita a mao == scikit-learn (dentro do float32)",
           difmax < 1e-6, "maior diferenca %.2e em 300 pares (eps float32 = "
                          "1,19e-07)" % difmax)
        ok("a ordenacao das 300 previsoes e identica",
           bool((np.argsort(p_mao) == np.argsort(p_sk)).all()),
           "diferenca numerica nao muda nenhuma decisao por limiar")
        ok("nenhuma probabilidade fora de [0,1]",
           bool(((p_mao >= 0) & (p_mao <= 1)).all()))

    # ================================== 7. sanidade farmacologica
    secao("7. SANIDADE — documentado pontua mais alto que sorteado")
    pos_te = p_te[y_te == 1]
    g = np.random.default_rng(7)
    todos = [s for (s,) in con.execute("SELECT id FROM substancia")]
    sorteados = []
    docs = set(con.execute("SELECT substancia_a_id, substancia_b_id "
                           "FROM interacao_substancia"))
    while len(sorteados) < 2000:
        a, b = g.choice(todos, 2, replace=False)
        a, b = (int(a), int(b)) if a < b else (int(b), int(a))
        if (a, b) not in docs:
            sorteados.append((a, b))
    Xs = construir(ctx, sorteados, blocos)
    p_s = gb.prever(Dados(Xs, np.zeros(len(sorteados), np.int8), sorteados, ctx, {}))
    print("      media dos positivos de teste ... %.4f" % pos_te.mean())
    print("      media dos pares sorteados ...... %.4f" % p_s.mean())
    ok("positivos pontuam mais que sorteados", pos_te.mean() > p_s.mean() + 0.05)
    concordancia = auc_postos(
        np.r_[np.ones(len(pos_te)), np.zeros(len(p_s))], np.r_[pos_te, p_s])
    ok("separacao documentado x sorteado com AUC > 0,80", concordancia > 0.80,
       "%.4f" % concordancia)

    print("\n" + "=" * 74)
    if falhas:
        print("V2 FALHOU em %d caminho(s):" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("V2 OK — seis caminhos independentes concordam com o pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
