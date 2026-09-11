# -*- coding: utf-8 -*-
"""
REGISTRO DO MODELO — treina o candidato final, grava o artefato e a linha
em `modelo`, com tudo o que um terceiro precisa para repetir o experimento.

O QUE VAI GRAVADO, E POR QUE CADA COISA
---------------------------------------
    semente               sem ela nao ha reproducao
    versao_dados          identifica o banco medido, nao o momento da carga
    espaco_features_json  os 130 nomes na ordem exata; 70_predizer aborta se
                          divergir, que foi o defeito que quebrou o sistema
                          anterior em silencio
    protocolo_validacao   split por farmaco, com os tres regimes
    metricas_json         teste e teste FRIO_FRIO, com intervalo de confianca
    limitacoes            em portugues, obrigatorio pelo esquema
    status                EXPERIMENTAL — medido, NAO liberado para o balcao
    ativo                 0

DOIS MODELOS SAO REGISTRADOS, NAO UM
------------------------------------
O de melhor metrica (gradient boosting) e o de referencia interpretavel
(regressao logistica). A diferenca entre eles e pequena e medida; guardar os
dois deixa a troca futura ser uma decisao com numero, e nao um retreino no
escuro. Nenhum dos dois fica ativo.

Saida: models/m1_*.json|pkl, models/espaco_features.json, linha em `modelo`
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _artefato import salvar
from _avaliacao import avaliar, escolher_limiar_f1, escolher_limiar_recall
from _comum import (MODELOS, SEMENTE, TREINO, conectar, gravar, linha, secao,
                    titulo, versao_dados)
from _features import carregar_contexto, construir, espaco
from _modelos import Dados, GradientBoosting, Logistica

BLOCOS = ("ATC", "REG", "ADM", "PK")
PROBLEMA = "existencia de interacao farmaco x farmaco documentada"

LIMITACOES = (
    "1) O rotulo negativo e PRESUMIDO: as fontes listam o que afirmam e nunca "
    "afirmam ausencia. O modelo estima probabilidade de o par ESTAR "
    "DOCUMENTADO nas bases carregadas, nao de o par ser perigoso. "
    "2) Medido em split por farmaco; no regime em que os dois farmacos sao "
    "ineditos a AUC e 0,74, com recall de 0,53 no ponto de F1 maximo — "
    "insuficiente para rastrear. "
    "3) So opina com alguma base nas 1.153 substancias que tem codigo ATC; "
    "para as outras 941 os atributos sao fracos. "
    "4) Nao gradua gravidade e nao substitui fonte: previsao nunca vira "
    "evidencia documental. "
    "5) Validacao COMPUTACIONAL apenas. Nenhum farmaceutico avaliou nenhuma "
    "previsao deste modelo."
)


def main() -> int:
    con = conectar()
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    regime, frieza = d["regime_farmaco"], d["frieza"]
    pares = list(zip(a_id.tolist(), b_id.tolist()))
    atc = {s: c for s, c in con.execute(
        "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
    vd = versao_dados(con)

    titulo("REGISTRO DO MODELO — Fase 7")
    tr, va, te = regime == 0, regime == 1, regime == 2
    ff = te & (frieza == 2)
    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    nomes = espaco(ctx, BLOCOS)
    X = construir(ctx, pares, BLOCOS)
    mk = lambda m: Dados(X[m], y[m], [pares[i] for i in np.flatnonzero(m)], ctx, atc)
    dtr, dva, dte, dff = mk(tr), mk(va), mk(te), mk(ff)

    # espaco de atributos: gravado uma vez, conferido na predicao
    MODELOS.mkdir(parents=True, exist_ok=True)
    (MODELOS / "espaco_features.json").write_text(
        json.dumps(dict(blocos=list(BLOCOS), n=len(nomes), nomes=nomes),
                   ensure_ascii=False, indent=2), encoding="utf-8")
    linha("espaco de atributos gravado", len(nomes), "models/espaco_features.json")

    calib = json.loads((MODELOS / "calibrador_m1.json").read_text(encoding="utf-8")) \
        if (MODELOS / "calibrador_m1.json").exists() else None

    registrados = []
    for Fam, versao, papel in ((GradientBoosting, "1.0-boosting", "melhor metrica"),
                               (Logistica, "1.0-logistica", "referencia interpretavel")):
        f = Fam()
        f.treinar(dtr)
        p_va = f.prever(dva)
        lim_f1 = escolher_limiar_f1(dva.y, p_va)
        lim_rec = escolher_limiar_recall(dva.y, p_va)
        met = dict(
            validacao=avaliar(dva.y, p_va, lim_f1, lim_rec),
            teste=avaliar(dte.y, f.prever(dte), lim_f1, lim_rec),
            teste_frio_frio=avaliar(dff.y, f.prever(dff), lim_f1, lim_rec),
            limiar_f1=lim_f1, limiar_recall_alto=lim_rec)
        caminho = MODELOS / ("m1_%s" % versao.replace(".", "_"))
        cab = salvar(f, caminho, dict(
            modelo="m1_existencia_interacao", versao=versao, familia=f.nome,
            blocos=list(BLOCOS), n_features=len(nomes), semente=SEMENTE,
            versao_dados=vd["impressao"], treinado_em=str(date.today())))
        art = Path(cab["artefato"])          # sempre o manifesto .json
        tam = cab.get("bytes_pickle") or art.stat().st_size
        secao("%s  (%s)" % (versao, papel))
        linha("familia", f.nome)
        linha("AUC teste / FRIO_FRIO",
              "%.4f / %.4f" % (met["teste"]["roc_auc"],
                               met["teste_frio_frio"]["roc_auc"]))
        linha("formato do artefato", cab["tipo"])
        linha("tamanho do artefato", "%.2f MB" % (tam / 1e6))
        if cab.get("aviso"):
            print("    AVISO: %s" % cab["aviso"])

        # Re-registrar a MESMA versao substitui o artefato. As previsoes que
        # existiam foram produzidas pelo artefato ANTIGO: mante-las apontando
        # para o registro novo faria a rastreabilidade mentir — o achado diria
        # "modelo 1.0-boosting" e o numero teria vindo de outro. Por isso elas
        # saem junto, e a fila de curadoria e refeita por 80_fila_curadoria.py.
        # (Sem isto o DELETE falhava com FOREIGN KEY e o registro ficava
        # dessincronizado do artefato — defeito encontrado pela V1 da Fase 8.)
        apagadas = con.execute(
            "DELETE FROM predicao WHERE modelo_id IN "
            "(SELECT id FROM modelo WHERE nome=? AND versao=?)",
            ("m1_existencia_interacao", versao)).rowcount
        if apagadas:
            print("    %d previsao(oes) do artefato anterior removidas — "
                  "refaca a fila com ml/80_fila_curadoria.py" % apagadas)
        con.execute("DELETE FROM modelo WHERE nome=? AND versao=?",
                    ("m1_existencia_interacao", versao))
        con.execute(
            "INSERT INTO modelo (nome,versao,problema,algoritmo,n_features,"
            "protocolo_validacao,metricas_json,treinado_em,semente,versao_dados,"
            "espaco_features_json,calibrador_json,artefato,status,limitacoes,ativo)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
            ("m1_existencia_interacao", versao, PROBLEMA, f.nome, len(nomes),
             "split por farmaco (estratificado por decil de grau); regimes "
             "QUENTE_QUENTE / QUENTE_FRIO / FRIO_FRIO; limiar escolhido na "
             "validacao; grafo de atributos excluido por vazamento medido",
             json.dumps(met, ensure_ascii=False),
             str(date.today()), SEMENTE, vd["impressao"],
             json.dumps(nomes, ensure_ascii=False),
             json.dumps(calib, ensure_ascii=False) if calib else None,
             str(art.relative_to(art.parent.parent)),
             "EXPERIMENTAL", LIMITACOES))
        registrados.append(dict(versao=versao, familia=f.nome,
                                artefato=str(art.name), tipo=cab["tipo"],
                                bytes=tam,
                                auc_teste=met["teste"]["roc_auc"],
                                auc_frio_frio=met["teste_frio_frio"]["roc_auc"]))
    con.commit()

    secao("ESTADO NO BANCO")
    for r_ in con.execute("SELECT nome,versao,algoritmo,status,ativo FROM modelo"):
        linha("%s %s" % (r_[0], r_[1]), "%s  status=%s  ativo=%d"
              % (r_[2], r_[3], r_[4]))
    print("""
  NENHUM MODELO ATIVO. `ativo=0` e `status='EXPERIMENTAL'` sao a forma de o
  banco dizer que o modelo foi medido e NAO foi liberado para gerar alerta ao
  farmaceutico. O indice unico do esquema impede que dois fiquem ativos para o
  mesmo problema, e o CHECK impede ativar um que nao esteja homologado —
  homologar exige decisao humana registrada, nao um UPDATE distraido.""")

    gravar("60_registro.json", dict(versao_dados=vd, modelos=registrados,
                                    limitacoes=LIMITACOES))
    print("\nGravado: ml/saida/60_registro.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
