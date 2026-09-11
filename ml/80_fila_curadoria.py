# -*- coding: utf-8 -*-
"""
FILA DE CURADORIA — o uso do modelo que os numeros sustentam.

POR QUE ESTE E O USO CORRETO, E NAO O ALERTA
--------------------------------------------
Medido em 20/25: no regime realista (dois farmacos ineditos) o modelo tem
AUC 0,74 e, no ponto de F1 maximo, recall 0,53 e precisao 0,40. Isso e pouco
para rastrear: metade das interacoes documentadas passaria batido e 6 de cada
10 alertas seriam falsos. Levar isso ao balcao aumentaria a fadiga de alerta
sem aumentar a seguranca — o que a especificacao §19 proibe explicitamente.

Mas a precisao NO TOPO da lista e alta: entre os 0,5% de maior probabilidade,
82% eram pares realmente afirmados por fonte, contra 20% de linha de base.
Um modelo que acerta 4 em 5 nos casos de maior confianca serve para uma coisa
concreta: dizer a um farmaceutico QUAIS pares valem ser investigados primeiro.
Isso e priorizacao de curadoria, nao alerta clinico, e a diferenca esta em
quem le e o que faz com a informacao.

DUAS FILAS, PORQUE SAO PERGUNTAS DIFERENTES
-------------------------------------------
    FILA A  pares em que pelo menos um farmaco nao tem NENHUMA interacao nas
            bases carregadas. E o ponto cego que motiva o projeto: ali o
            sistema hoje so sabe dizer "nao avaliado".
    FILA B  pares entre farmacos ja cobertos, mas que nenhuma das duas bases
            afirma. Aqui a ausencia e mais informativa (as bases olharam
            esses farmacos), logo probabilidade alta sugere lacuna da fonte.

O QUE A FILA NAO E
------------------
Nao e lista de interacoes. Nenhuma linha dela afirma que existe interacao.
Cada linha diz: "o modelo estima X% e por isso este par esta no topo da fila
de verificacao". As linhas gravadas em `predicao` nascem com
`status='NAO_REVISADA'` e nao viram achado — o modelo esta EXPERIMENTAL e
`70_predizer.contrato_achado` recusa.

Saida: reports/fila_curadoria_m1.csv + linhas em `predicao`
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import (RAIZ, carregar_predizer, conectar, gravar, linha, pct,
                    secao, titulo, versao_dados)
from _features import construir

TOPO_POR_FILA = 300
BLOCO = 40000
TETO_POR_SUBSTANCIA = 8




def main() -> int:
    con = conectar()
    p = carregar_predizer().Preditor(con)
    titulo("FILA DE CURADORIA — modelo %s %s (status %s)"
           % (p.nome, p.versao, p.status))
    r = {"versao_dados": versao_dados(con), "modelo": p.versao}

    com_atc = sorted(p.atc)
    conectadas = {s for (s,) in con.execute(
        "SELECT substancia_a_id FROM interacao_substancia "
        "UNION SELECT substancia_b_id FROM interacao_substancia")}
    documentados = set(con.execute(
        "SELECT substancia_a_id, substancia_b_id FROM vw_interacao_liberada"))
    nome = p.nome_subst
    linha("substancias com ATC", len(com_atc))
    linha("  destas, ja com alguma interacao afirmada",
          len([s for s in com_atc if s in conectadas]))
    linha("  destas, sem nenhuma interacao afirmada",
          len([s for s in com_atc if s not in conectadas]),
          "<- o ponto cego")
    linha("pares possiveis entre substancias com ATC",
          len(com_atc) * (len(com_atc) - 1) // 2)

    # ------------------------------------------------- monta os candidatos
    secao("PONTUANDO OS PARES NAO DOCUMENTADOS")
    candidatos = []
    for i in range(len(com_atc)):
        a = com_atc[i]
        for j in range(i + 1, len(com_atc)):
            b = com_atc[j]
            if (a, b) in documentados:
                continue
            candidatos.append((a, b))
    linha("pares candidatos (nao documentados)", len(candidatos))

    probs = np.empty(len(candidatos), dtype=np.float64)
    for k in range(0, len(candidatos), BLOCO):
        lote = candidatos[k:k + BLOCO]
        X = construir(p.ctx, lote, p.blocos)
        probs[k:k + len(lote)] = p.obj.prever(X=X, pares=lote, atc=p.atc)
        print("    %d / %d" % (min(k + BLOCO, len(candidatos)), len(candidatos)),
              flush=True)
    pc = p._calibrar(probs)
    if pc is not None:
        probs_exib = pc
    else:
        probs_exib = probs
    linha("probabilidade calibrada — media", "%.4f" % probs_exib.mean())
    linha("  acima de 0,90", int((probs_exib >= 0.90).sum()))
    linha("  acima de 0,80", int((probs_exib >= 0.80).sum()))
    linha("  acima de 0,50", int((probs_exib >= 0.50).sum()),
          "(%s dos candidatos)" % pct(int((probs_exib >= 0.50).sum()),
                                      len(candidatos)))

    # -------------------------------------------------------- duas filas
    cego = np.array([1 if (a not in conectadas or b not in conectadas) else 0
                     for a, b in candidatos], dtype=np.int8)
    filas = {}
    for rot, mask in (("A_PONTO_CEGO", cego == 1), ("B_LACUNA_DE_FONTE", cego == 0)):
        idx = np.flatnonzero(mask)
        ordenados = idx[np.argsort(-probs_exib[idx])]
        # TETO POR SUBSTANCIA. Sem ele a fila vira uma lista sobre um farmaco
        # so: levomepromazina nao tem nenhuma interacao em nenhuma das duas
        # bases, e o modelo (corretamente) marca alto todos os seus pares com
        # psicotropicos — 300 linhas sobre o mesmo farmaco. Um farmaceutico
        # verifica o farmaco UMA vez; a fila tem de cobrir varios.
        conta = {}
        ordem = []
        for i in ordenados:
            a, b = candidatos[i]
            if conta.get(a, 0) >= TETO_POR_SUBSTANCIA or \
               conta.get(b, 0) >= TETO_POR_SUBSTANCIA:
                continue
            conta[a] = conta.get(a, 0) + 1
            conta[b] = conta.get(b, 0) + 1
            ordem.append(i)
            if len(ordem) >= TOPO_POR_FILA:
                break
        ordem = np.array(ordem, dtype=np.int64)
        filas[rot] = ordem
        secao("FILA %s" % rot)
        linha("candidatos nesta fila", int(mask.sum()))
        linha("substancias distintas na fila", len(conta),
              "(teto de %d pares por substancia)" % TETO_POR_SUBSTANCIA)
        linha("probabilidade do 1o colocado", "%.3f" % probs_exib[ordem[0]])
        linha("probabilidade do %do colocado" % len(ordem),
              "%.3f" % probs_exib[ordem[-1]])
        print("\n  os 10 primeiros:")
        for i in ordem[:10]:
            a, b = candidatos[i]
            print("    %.3f  %-32s x %-32s"
                  % (probs_exib[i], nome.get(a, "?")[:32], nome.get(b, "?")[:32]))

    # ------------------------------------------------------------ gravacao
    destino = RAIZ / "reports" / "fila_curadoria_m1.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    n_grav = 0
    with destino.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["fila", "posicao", "substancia_a", "substancia_b",
                    "atc_a", "atc_b", "probabilidade_calibrada",
                    "probabilidade_bruta", "modelo", "versao", "status_modelo",
                    "o_que_isto_e"])
        for rot, ordem in filas.items():
            for pos, i in enumerate(ordem, 1):
                a, b = candidatos[i]
                w.writerow([rot, pos, nome.get(a, "?"), nome.get(b, "?"),
                            p.atc.get(a, ""), p.atc.get(b, ""),
                            "%.4f" % probs_exib[i], "%.4f" % probs[i],
                            p.nome, p.versao, p.status,
                            "PREVISAO estatistica, sem evidencia documental; "
                            "requer verificacao por farmaceutico"])
                n_grav += 1

    # grava em `predicao` os pares das duas filas
    todos = [candidatos[i] for ordem in filas.values() for i in ordem]
    prev = p.prever(todos)
    n_pred = p.gravar_predicoes(prev)

    secao("GRAVADO")
    linha("linhas no CSV", n_grav, str(destino.relative_to(RAIZ)))
    linha("linhas em `predicao`", n_pred, "status NAO_REVISADA")
    linha("achados gerados", 0, "<- modelo EXPERIMENTAL, contrato recusa")
    r["filas"] = {rot: [dict(a=nome.get(candidatos[i][0]),
                             b=nome.get(candidatos[i][1]),
                             probabilidade=float(probs_exib[i]))
                        for i in ordem[:20]]
                  for rot, ordem in filas.items()}
    r["candidatos"] = len(candidatos)
    r["acima_0_90"] = int((probs_exib >= 0.90).sum())
    r["acima_0_50"] = int((probs_exib >= 0.50).sum())
    r["gravadas_em_predicao"] = n_pred
    gravar("80_fila_curadoria.json", r)
    print("""
  COMO ESTA FILA E USADA: um farmaceutico pega o topo, procura a interacao na
  literatura e registra o que achou. Cada linha verificada vira rotulo humano
  — o insumo que hoje nao existe (anotacao_profissional esta vazia) e sem o
  qual o modelo de RELEVANCIA (problema B) nao pode ser treinado. A fila e,
  portanto, tambem o caminho para sair da limitacao central desta fase.""")
    print("\nGravado: ml/saida/80_fila_curadoria.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
