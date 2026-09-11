# -*- coding: utf-8 -*-
"""
ROBUSTEZ — quatro provas que a metrica agregada nao da.

1. PAREADO POR GRAU. No universo inteiro, farmaco popular tem mais interacao
   afirmada, e um modelo pode acertar so por saber quem e popular. Aqui cada
   negativo tem grau parecido com o do positivo, entao popularidade deixa de
   separar as classes. O que sobra e farmacologia.

2. CONTROLE NEGATIVO (§20). 5.000 pares sorteados ao acaso entre as 2.094
   substancias, nenhum deles positivo, a maioria envolvendo farmaco de grau
   zero. Um modelo que distribui probabilidade alta indiscriminadamente
   aparece aqui.

3. ROTULO MAIS DURO. Repete o teste usando como positivo somente o par que as
   DUAS fontes afirmam. Se o desempenho desabar, o modelo estava aprendendo o
   idiossincratico de uma base; se sobreviver, o sinal e comum as duas.

4. O PONTO CEGO, MEDIDO. Quantas das 2.094 substancias o modelo escolhido
   consegue pontuar de fato — isto e, tem os atributos de que precisa.

Saida: ml/saida/25_robustez.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _avaliacao import avaliar, escolher_limiar_f1, escolher_limiar_recall
from _comum import TREINO, conectar, gravar, linha, pct, secao, titulo, versao_dados
from _features import carregar_contexto, construir, espaco
from _modelos import Dados, GradientBoosting, Logistica

CONFIGS = {"COMPLETO": ("ATC", "REG", "ADM", "PK", "GRAFO"),
           "SEM_GRAFO": ("ATC", "REG", "ADM", "PK")}
FAMILIAS = [Logistica, GradientBoosting]


def main() -> int:
    con = conectar()
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    n_fontes = d["n_fontes"]
    regime = d["regime_farmaco"]
    frieza = d["frieza"]
    pares = list(zip(a_id.tolist(), b_id.tolist()))
    atc = {s: c for s, c in con.execute(
        "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
    r = {"versao_dados": versao_dados(con)}

    titulo("ROBUSTEZ DO ALVO A")

    # =============================================== 1. pareado por grau
    secao("1. PAREADO POR GRAU — quanto do acerto era popularidade?")
    sub = d["indices_pareado_grau"]
    m_sub = np.zeros(len(y), dtype=bool)
    m_sub[sub] = True
    tr = m_sub & (regime == 0)
    va = m_sub & (regime == 1)
    te = m_sub & (regime == 2)
    linha("pares no subconjunto", int(m_sub.sum()),
          "prevalencia %s" % pct(int(y[m_sub].sum()), int(m_sub.sum())))
    for nome, m in (("treino", tr), ("validacao", va), ("teste", te)):
        linha("  %s" % nome, int(m.sum()),
              "prevalencia %s" % pct(int(y[m].sum()), int(m.sum())))

    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_PAREADO")
    r["pareado_grau"] = []
    print()
    for nome_cfg, blocos in CONFIGS.items():
        X = construir(ctx, pares, blocos)
        dd = {k: Dados(X[m], y[m], [pares[i] for i in np.flatnonzero(m)], ctx, atc)
              for k, m in (("treino", tr), ("validacao", va), ("teste", te))}
        for Fam in FAMILIAS:
            f = Fam()
            f.treinar(dd["treino"])
            pv = f.prever(dd["validacao"])
            lf1 = escolher_limiar_f1(dd["validacao"].y, pv)
            lrc = escolher_limiar_recall(dd["validacao"].y, pv)
            mt = avaliar(dd["teste"].y, f.prever(dd["teste"]), lf1, lrc)
            r["pareado_grau"].append(dict(configuracao=nome_cfg, familia=f.nome,
                                          teste=mt))
            print("  %-18s %-10s  AUC %.4f   PR-AUC %.4f (piso %.3f)"
                  % (f.nome, nome_cfg, mt["roc_auc"], mt["pr_auc"],
                     mt["pr_auc_piso"]))
        del X, dd
    print("""
  Como ler: no universo inteiro, com atributos SEM_GRAFO, o gradient boosting
  faz AUC 0,79. Aqui, com grau neutralizado, o numero que sobra e o que o
  modelo sabe de farmacologia. A diferenca entre os dois e o tamanho do
  artefato de popularidade.""")

    # ================================================ 2. controle negativo
    secao("2. CONTROLE NEGATIVO — 5.000 pares ao acaso (§20)")
    ctrl = list(zip(d["controle_a"].tolist(), d["controle_b"].tolist()))
    m_tr = regime == 0
    arestas = list(zip(a_id[m_tr & (y == 1)].tolist(),
                       b_id[m_tr & (y == 1)].tolist()))
    ctx2 = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    blocos = CONFIGS["SEM_GRAFO"]
    X = construir(ctx2, pares, blocos)
    dtr = Dados(X[m_tr], y[m_tr], [pares[i] for i in np.flatnonzero(m_tr)], ctx2, atc)
    f = GradientBoosting()
    f.treinar(dtr)

    Xc = construir(ctx2, ctrl, blocos)
    pc = f.prever(Dados(Xc, np.zeros(len(ctrl), np.int8), ctrl, ctx2, atc))
    m_te = regime == 2
    pte = f.prever(Dados(X[m_te], y[m_te],
                         [pares[i] for i in np.flatnonzero(m_te)], ctx2, atc))
    pos_te, neg_te = pte[y[m_te] == 1], pte[y[m_te] == 0]
    linha("probabilidade media — positivos do teste", "%.3f" % pos_te.mean())
    linha("probabilidade media — negativos do teste", "%.3f" % neg_te.mean())
    linha("probabilidade media — controle ao acaso", "%.3f" % pc.mean())
    for t in (0.5, 0.7, 0.9):
        linha("  controle acima de %.1f" % t, int((pc >= t).sum()),
              "(%s dos 5.000)" % pct(int((pc >= t).sum()), len(pc)))
    # quantos do controle o modelo consegue pontuar com atributo real
    sem_atc = sum(1 for a, b in ctrl if a not in atc or b not in atc)
    linha("pares de controle com pelo menos um lado sem ATC", sem_atc,
          "(%s)" % pct(sem_atc, len(ctrl)))
    r["controle_negativo"] = dict(
        media_positivos_teste=float(pos_te.mean()),
        media_negativos_teste=float(neg_te.mean()),
        media_controle=float(pc.mean()),
        acima_0_5=int((pc >= 0.5).sum()), acima_0_7=int((pc >= 0.7).sum()),
        acima_0_9=int((pc >= 0.9).sum()), n=len(pc),
        sem_atc_em_um_lado=sem_atc)
    print("""
  O controle nao tem rotulo verdadeiro — sao pares nao afirmados, e nao pares
  provadamente inertes. Serve para uma pergunta so: a probabilidade sai alta
  indiscriminadamente? Se a media do controle ficasse perto da media dos
  positivos, o modelo estaria dizendo sim para tudo.""")

    # ================================================= 3. rotulo mais duro
    secao("3. ROTULO MAIS DURO — positivo so quando as DUAS fontes afirmam")
    y2 = (n_fontes >= 2).astype(np.int8)
    linha("positivos com este criterio", int(y2.sum()),
          "(contra %d do criterio normal)" % int(y.sum()))
    linha("prevalencia", pct(int(y2.sum()), len(y2)))
    # os pares afirmados por uma fonte so viram... negativos? Nao: sairiam do
    # universo, porque chama-los de negativo seria afirmar que a outra fonte
    # os examinou e recusou. Ficam FORA.
    manter = (n_fontes != 1)
    linha("pares afirmados por UMA fonte, removidos do universo",
          int((n_fontes == 1).sum()),
          "<- nao viram negativo: a outra base pode nao te-los examinado")
    linha("universo restante", int(manter.sum()))
    tr2 = manter & (regime == 0)
    va2 = manter & (regime == 1)
    te2 = manter & (regime == 2)
    arestas2 = list(zip(a_id[tr2 & (y2 == 1)].tolist(),
                        b_id[tr2 & (y2 == 1)].tolist()))
    ctx3 = carregar_contexto(con, arestas2, origem_grafo="TREINO_DUAS_FONTES")
    X2 = construir(ctx3, pares, CONFIGS["SEM_GRAFO"])
    dd = {k: Dados(X2[m], y2[m], [pares[i] for i in np.flatnonzero(m)], ctx3, atc)
          for k, m in (("treino", tr2), ("validacao", va2), ("teste", te2))}
    r["rotulo_duas_fontes"] = []
    print()
    for Fam in FAMILIAS:
        f2 = Fam()
        f2.treinar(dd["treino"])
        pv = f2.prever(dd["validacao"])
        lf1 = escolher_limiar_f1(dd["validacao"].y, pv)
        lrc = escolher_limiar_recall(dd["validacao"].y, pv)
        mt = avaliar(dd["teste"].y, f2.prever(dd["teste"]), lf1, lrc)
        r["rotulo_duas_fontes"].append(dict(familia=f2.nome, teste=mt))
        print("  %-18s SEM_GRAFO   AUC %.4f   PR-AUC %.4f (piso %.3f)"
              % (f2.nome, mt["roc_auc"], mt["pr_auc"], mt["pr_auc_piso"]))
    del X2, dd

    # ==================================================== 4. o ponto cego
    secao("4. PONTO CEGO — em quantas substancias o modelo consegue opinar?")
    total = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
    com_atc = len(atc)
    linha("substancias no banco", total)
    linha("com ATC (atributo principal)", com_atc, "(%s)" % pct(com_atc, total))
    linha("sem ATC — modelo opina so pelos atributos fracos", total - com_atc,
          "(%s)" % pct(total - com_atc, total))
    grau0_sem_atc = con.execute(
        "SELECT COUNT(*) FROM substancia WHERE atc_codigo IS NULL AND id NOT IN "
        "(SELECT substancia_a_id FROM interacao_substancia UNION "
        " SELECT substancia_b_id FROM interacao_substancia)").fetchone()[0]
    linha("sem ATC E sem nenhuma interacao conhecida", grau0_sem_atc,
          "(%s)  <- cegueira dupla" % pct(grau0_sem_atc, total))
    r["ponto_cego"] = dict(substancias=total, com_atc=com_atc,
                           sem_atc=total - com_atc,
                           sem_atc_e_sem_aresta=grau0_sem_atc)
    print("""
  Para essas o sistema continua tendo o que dizer — pelas regras
  deterministicas e pela declaracao de nao-cobertura — mas o modelo nao
  acrescenta nada, e a interface tem de dizer isso em vez de exibir uma
  probabilidade baseada em quase nenhum atributo.""")

    # =========================================== 5. precisao no topo da lista
    secao("5. PRECISAO NO TOPO — o unico regime em que previsao viraria alerta")
    print("""  Um modelo com AUC 0,74 nao serve para rastrear tudo. Pode servir para
  apontar POUCOS pares com alta confianca. A pergunta e: entre os N pares de
  maior probabilidade, quantos sao mesmo afirmados por fonte?""")
    m_ff = (regime == 2) & (frieza == 2)
    d_ff = Dados(X[m_ff], y[m_ff], [pares[i] for i in np.flatnonzero(m_ff)],
                 ctx2, atc)
    p_ff = f.prever(d_ff)
    y_ff = y[m_ff]
    print("\n  regime FRIO_FRIO (%d pares, prevalencia %s):"
          % (len(y_ff), pct(int(y_ff.sum()), len(y_ff))))
    topo = []
    ordem = np.argsort(-p_ff)
    for frac in (0.001, 0.005, 0.01, 0.05, 0.10):
        k = max(1, int(frac * len(y_ff)))
        sel = ordem[:k]
        prec = float(y_ff[sel].mean())
        topo.append(dict(fracao=frac, n=k, precisao=prec,
                         limiar=float(p_ff[sel][-1]),
                         recall=float(y_ff[sel].sum() / max(1, y_ff.sum()))))
        linha("  top %.1f%% (%d pares)" % (100 * frac, k),
              "precisao %.3f   recall %.3f   limiar %.3f"
              % (prec, y_ff[sel].sum() / max(1, y_ff.sum()), p_ff[sel][-1]))
    linha("  linha de base (acaso)", "precisao %.3f" % y_ff.mean())
    r["precisao_no_topo"] = dict(regime="FRIO_FRIO", prevalencia=float(y_ff.mean()),
                                 pontos=topo)
    print("""
  Leitura para a decisao de implantacao: se a precisao no topo nao for
  claramente maior que a prevalencia, um alerta previsto acrescentaria mais
  ruido que informacao, e a resposta correta e nao exibi-lo como alerta.""")

    gravar("25_robustez.json", r)
    print("\nGravado: ml/saida/25_robustez.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
