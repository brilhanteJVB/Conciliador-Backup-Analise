# -*- coding: utf-8 -*-
"""
METRICAS E LIMIARES.

Uma so implementacao para o pipeline principal, baseada no scikit-learn.
A VERIFICACAO INDEPENDENTE (92_v2_independente.py) reimplementa as mesmas
metricas em numpy puro e compara os numeros — se as duas divergirem, uma
das duas esta errada, e e isso que a segunda verificacao existe para achar.

POR QUE NAO ACURACIA
--------------------
Com prevalencia de 20,7%, dizer "nao interage" sempre acerta 79,3%. Acuracia
alta aqui e ausencia de modelo. O que interessa e:
    ROC-AUC   ordena bem? (independente de limiar e de prevalencia)
    PR-AUC    acerta os positivos sem afogar o farmaceutico em alerta?
              O piso e a prevalencia, nao 0,5 — por isso vai reportado junto.
    RECALL    quantos pares documentados o modelo deixaria passar
    ESPECIFICIDADE  quantos alertas falsos ele acrescentaria

DOIS PONTOS DE OPERACAO, E OS DOIS SAO REPORTADOS
-------------------------------------------------
    F1_MAXIMO       o equilibrio, escolhido na validacao
    RECALL_ALTO     limiar que garante 95% de recall na validacao — o que
                    interessa quando deixar passar custa mais que avisar de
                    mais. O preco (quantos alertas a mais) vai ao lado.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             confusion_matrix, roc_auc_score)

RECALL_ALVO = 0.95


def ece(y, p, n_bins: int = 10) -> float:
    """Erro de calibracao esperado: |confianca - frequencia| media ponderada."""
    limites = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for i in range(n_bins):
        m = (p >= limites[i]) & (p < limites[i + 1] if i < n_bins - 1
                                 else p <= limites[i + 1])
        if m.sum():
            total += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(total / len(y))


def curva_confiabilidade(y, p, n_bins: int = 10) -> list[dict]:
    limites = np.linspace(0.0, 1.0, n_bins + 1)
    saida = []
    for i in range(n_bins):
        m = (p >= limites[i]) & (p < limites[i + 1] if i < n_bins - 1
                                 else p <= limites[i + 1])
        saida.append(dict(faixa="%.1f-%.1f" % (limites[i], limites[i + 1]),
                          n=int(m.sum()),
                          probabilidade_media=float(p[m].mean()) if m.sum() else None,
                          frequencia_real=float(y[m].mean()) if m.sum() else None))
    return saida


def no_limiar(y, p, limiar: float) -> dict:
    yp = (p >= limiar).astype(np.int8)
    mc = confusion_matrix(y, yp, labels=[0, 1])
    vn, fp, fn, vp = mc.ravel()
    prec = vp / (vp + fp) if (vp + fp) else 0.0
    rec = vp / (vp + fn) if (vp + fn) else 0.0
    esp = vn / (vn + fp) if (vn + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return dict(limiar=float(limiar), precisao=float(prec), recall=float(rec),
                especificidade=float(esp), f1=float(f1),
                verdadeiro_positivo=int(vp), falso_positivo=int(fp),
                falso_negativo=int(fn), verdadeiro_negativo=int(vn),
                alertas_emitidos=int(vp + fp))


def escolher_limiar_f1(y, p) -> float:
    """Limiar de F1 maximo. Escolhido SEMPRE na validacao, nunca no teste."""
    cand = np.unique(np.quantile(p, np.linspace(0.001, 0.999, 400)))
    melhor, melhor_f1 = 0.5, -1.0
    for t in cand:
        m = no_limiar(y, p, t)
        if m["f1"] > melhor_f1:
            melhor, melhor_f1 = float(t), m["f1"]
    return melhor


def escolher_limiar_recall(y, p, alvo: float = RECALL_ALVO) -> float:
    """Menor limiar (mais alertas) que ainda entrega `alvo` de recall."""
    ordem = np.sort(p[y == 1])
    if not len(ordem):
        return 0.5
    k = int(np.floor((1 - alvo) * len(ordem)))
    return float(ordem[min(k, len(ordem) - 1)])


def avaliar(y, p, limiar_f1=None, limiar_recall=None) -> dict:
    y = np.asarray(y).astype(np.int8)
    p = np.asarray(p, dtype=np.float64)
    prev = float(y.mean())
    r = dict(n=int(len(y)), positivos=int(y.sum()), prevalencia=prev)
    if 0 < y.sum() < len(y):
        r["roc_auc"] = float(roc_auc_score(y, p))
        r["pr_auc"] = float(average_precision_score(y, p))
        r["pr_auc_piso"] = prev          # PR-AUC de um modelo aleatorio
        r["pr_auc_ganho"] = r["pr_auc"] - prev
    else:
        r["roc_auc"] = r["pr_auc"] = None
        r["pr_auc_piso"] = prev
        r["pr_auc_ganho"] = None
    r["brier"] = float(brier_score_loss(y, np.clip(p, 0, 1)))
    r["ece"] = ece(y, np.clip(p, 0, 1))
    r["probabilidade_media"] = float(p.mean())
    if limiar_f1 is not None:
        r["ponto_f1"] = no_limiar(y, p, limiar_f1)
    if limiar_recall is not None:
        r["ponto_recall_alto"] = no_limiar(y, p, limiar_recall)
    return r


def formatar(nome: str, m: dict) -> str:
    def v(x, casas=4):
        return "—" if x is None else ("%.*f" % (casas, x)).replace(".", ",")
    f1 = m.get("ponto_f1") or {}
    return ("  %-34s AUC %s  PR-AUC %s (piso %s)  F1 %s  rec %s  esp %s"
            % (nome[:34], v(m.get("roc_auc")), v(m.get("pr_auc")),
               v(m.get("pr_auc_piso"), 3), v(f1.get("f1"), 3),
               v(f1.get("recall"), 3), v(f1.get("especificidade"), 3)))
