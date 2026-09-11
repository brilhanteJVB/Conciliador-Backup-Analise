# -*- coding: utf-8 -*-
"""
REGRESSAO DAS GARANTIAS DE MACHINE LEARNING (Fase 7).

Trava, uma por uma, as garantias que a Fase 7 nao pode quebrar. Cada linha
aqui existe porque quebra-la seria levar uma previsao ao balcao disfarcada de
fato, ou porque foi um defeito real no sistema anterior.

Nao usa framework: python tests/teste_ml.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ml"))

BANCO = RAIZ / "database" / "conciliador.db"
falhas = []


def ok(desc, cond, detalhe=""):
    print("  [%s] %-58s %s" % ("OK " if cond else "FALHA", desc, detalhe))
    if not cond:
        falhas.append(desc)


def recusa(con, desc, sql):
    try:
        con.execute(sql)
        con.rollback()
        ok(desc, False, "o banco ACEITOU")
    except sqlite3.Error as e:
        con.rollback()
        ok(desc, True, type(e).__name__)


def main() -> int:
    print("=" * 74)
    print("REGRESSAO — GARANTIAS DE ML")
    print("=" * 74)
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA foreign_keys = ON")
    um = lambda s: con.execute(s).fetchone()[0]

    print("\nML NUNCA ATRIBUI GRAVIDADE")
    ok("nenhuma predicao com gravidade sugerida",
       um("SELECT COUNT(*) FROM predicao WHERE gravidade_sugerida IS NOT NULL") == 0)
    mid = con.execute("SELECT id FROM modelo LIMIT 1").fetchone()
    if mid:
        recusa(con, "o banco recusa gravidade sugerida por modelo",
               "INSERT INTO predicao (modelo_id,substancia_a_id,substancia_b_id,"
               "probabilidade,gravidade_sugerida) VALUES (%d,1,2,0.5,'MAIOR')" % mid[0])

    print("\nPREVISAO NAO SE DISFARCA DE FATO")
    ok("nenhum achado com natureza PREVISTO no banco",
       um("SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO'") == 0,
       "modelo EXPERIMENTAL: nenhuma previsao virou achado")
    ok("nenhum achado com origem MODELO",
       um("SELECT COUNT(*) FROM achado WHERE origem_achado<>'REGRA'") == 0)
    ok("todo achado existente e de REGRA",
       um("SELECT COUNT(*) FROM achado WHERE origem_achado='REGRA'")
       == um("SELECT COUNT(*) FROM achado"),
       "%d achados" % um("SELECT COUNT(*) FROM achado"))
    ok("nenhum achado de REGRA carrega probabilidade de modelo",
       um("SELECT COUNT(*) FROM achado WHERE origem_achado='REGRA' "
          "AND probabilidade_modelo IS NOT NULL") == 0)
    ok("PREVISTO sempre aponta para uma linha de predicao",
       um("SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' "
          "AND origem_afirmacao NOT LIKE 'predicao.%'") == 0)
    ok("previsao nao entra em vw_interacao_liberada",
       "predicao" not in (con.execute(
           "SELECT sql FROM sqlite_master WHERE name='vw_interacao_liberada'"
       ).fetchone()[0] or ""),
       "a view que chega ao farmaceutico nao le a tabela de previsao")

    print("\nA VIEW E A UNICA PORTA (Fase 8)")
    ok("vw_predicao_liberada existe",
       um("SELECT COUNT(*) FROM sqlite_master WHERE type='view' "
          "AND name='vw_predicao_liberada'") == 1)
    sql_view = con.execute(
        "SELECT sql FROM sqlite_master WHERE name='vw_predicao_liberada'"
    ).fetchone()[0]
    for exigido in ("m.ativo = 1", "m.status = 'HOMOLOGADO'",
                    "m.limiar_alerta IS NOT NULL", "NOT EXISTS",
                    "REVISADA_RECUSADA"):
        ok("a view exige %r" % exigido, exigido in sql_view)
    ok("sem modelo ativo, a view devolve zero",
       um("SELECT COUNT(*) FROM vw_predicao_liberada") == 0)
    ok("nenhum achado previsto no banco de producao",
       um("SELECT COUNT(*) FROM achado WHERE subtipo='INTERACAO_PREVISTA'") == 0)
    motor = (RAIZ / "rules" / "motor_conciliacao.py").read_text(encoding="utf-8")
    ok("o motor le a view de previsao", "vw_predicao_liberada" in motor)
    ok("o motor NAO consulta a tabela `predicao` direto",
       "FROM predicao" not in motor and "INTO predicao" not in motor)
    ok("a previsao entra com prioridade de teto INFORMATIVO",
       '("FARMACO_FARMACO", "PREVISTA")' in
       (RAIZ / "rules" / "_prioridade.py").read_text(encoding="utf-8"))

    print("\nA TELA SEPARA DOCUMENTADO DE PREVISTO (Fase 8)")
    res_html = (RAIZ / "app" / "templates" / "resultados.html"
                ).read_text(encoding="utf-8")
    ok("a tela tem bloco proprio para previsto",
       'id="bloco-previsto"' in res_html)
    ok("o bloco declara que nao e alerta nem interacao documentada",
       "não é alerta e não é interação documentada" in res_html)
    web_py = (RAIZ / "app" / "web.py").read_text(encoding="utf-8")
    ok("a rota separa as duas listas antes de renderizar",
       "previstos = [a for a in visiveis" in web_py)
    rel_py = (RAIZ / "app" / "relatorio.py").read_text(encoding="utf-8")
    ok("o relatorio separa previsto dos achados",
       "achados_previstos" in rel_py)
    det_html = (RAIZ / "app" / "templates" / "achado.html"
                ).read_text(encoding="utf-8")
    ok("o detalhe tem painel de rastreabilidade do modelo",
       "Rastreabilidade da previsão" in det_html)
    ok("o detalhe declara ausencia de evidencia documental",
       "Não há evidência documental para este par" in det_html)

    print("\nMODELO NAO E TROCADO EM SILENCIO")
    ok("no maximo um modelo ativo por problema",
       um("SELECT COUNT(*) FROM (SELECT problema FROM modelo WHERE ativo=1 "
          "GROUP BY problema HAVING COUNT(*)>1)") == 0)
    ok("nenhum modelo ativo hoje", um("SELECT COUNT(*) FROM modelo WHERE ativo=1") == 0,
       "%d modelos registrados, todos inativos"
       % um("SELECT COUNT(*) FROM modelo"))
    ok("todo modelo declara semente, versao de dados e espaco de atributos",
       um("SELECT COUNT(*) FROM modelo WHERE semente IS NULL OR "
          "versao_dados IS NULL OR espaco_features_json IS NULL") == 0)
    ok("todo modelo declara limitacoes em texto",
       um("SELECT COUNT(*) FROM modelo WHERE limitacoes IS NULL "
          "OR LENGTH(limitacoes)<40") == 0)
    ok("nenhum modelo ativo sem estar homologado",
       um("SELECT COUNT(*) FROM modelo WHERE ativo=1 AND status<>'HOMOLOGADO'") == 0)

    # Depois de `executar_tudo.py --recriar` o banco nasce sem modelo e sem
    # previsao: os artefatos de ML sao reconstruidos por `ml/executar_tudo.py`,
    # que e outro pipeline. As garantias estruturais acima valem sempre; as
    # que dependem de um modelo treinado ficam declaradas como nao verificadas
    # em vez de darem falso OK.
    tem_modelo = um("SELECT COUNT(*) FROM modelo") > 0
    if not tem_modelo:
        print("\n" + "=" * 74)
        print("BANCO SEM MODELO REGISTRADO — as garantias estruturais acima")
        print("passaram; as que dependem de modelo treinado NAO foram")
        print("verificadas. Rode `python ml/executar_tudo.py` para reconstrui-lo.")
        print("=" * 74)
        return 1 if falhas else 0

    print("\nPREVISAO GRAVADA NASCE NAO REVISADA")
    n_pred = um("SELECT COUNT(*) FROM predicao")
    ok("ha previsoes gravadas para curadoria", n_pred > 0, "%d linhas" % n_pred)
    ok("todas NAO_REVISADA",
       um("SELECT COUNT(*) FROM predicao WHERE status<>'NAO_REVISADA'") == 0)
    ok("nenhuma revisada sem quem revisou",
       um("SELECT COUNT(*) FROM predicao WHERE status<>'NAO_REVISADA' "
          "AND revisado_por IS NULL") == 0)
    ok("toda previsao aponta para um modelo existente",
       um("SELECT COUNT(*) FROM predicao p LEFT JOIN modelo m ON m.id=p.modelo_id "
          "WHERE m.id IS NULL") == 0)
    ok("todo par de previsao em ordem canonica",
       um("SELECT COUNT(*) FROM predicao WHERE substancia_a_id>=substancia_b_id") == 0)

    print("\nO ESPACO DE ATRIBUTOS NAO DIVERGE")
    from _comum import conectar
    from _features import carregar_contexto, espaco
    ctx = carregar_contexto(con, None, origem_grafo="TESTE")
    atual = espaco(ctx, ("ATC", "REG", "ADM", "PK"))
    arq = RAIZ / "models" / "espaco_features.json"
    ok("models/espaco_features.json existe", arq.exists())
    if arq.exists():
        ok("espaco em disco == espaco calculado agora",
           json.loads(arq.read_text(encoding="utf-8"))["nomes"] == atual,
           "%d atributos" % len(atual))
    for versao in ("1.0-boosting", "1.0-logistica"):
        gravado = con.execute("SELECT espaco_features_json FROM modelo "
                              "WHERE versao=?", (versao,)).fetchone()
        if gravado:
            ok("espaco gravado no modelo %s confere" % versao,
               json.loads(gravado[0]) == atual)
    ok("nenhum atributo derivado da tabela de interacao",
       not any(k in n for n in atual for k in
               ("gravidade", "mecanismo", "efeito", "descricao", "prioridade")))
    ok("nenhum atributo de grafo no espaco publicado",
       not any(n.startswith("g_") for n in atual),
       "grafo excluido por vazamento medido em 20_treinar")

    print("\nO CONTRATO RECUSA MODELO NAO HOMOLOGADO")
    from _comum import carregar_predizer
    predizer = carregar_predizer()
    p = predizer.Preditor(con)
    # par SEM documentacao: o texto de previsao so faz sentido ali, e e o unico
    # caso em que o modelo seria usado de verdade.
    par = con.execute(
        "SELECT a.id, b.id FROM substancia a, substancia b WHERE a.id<b.id "
        "AND a.atc_codigo IS NOT NULL AND b.atc_codigo IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM interacao_substancia i "
        "WHERE i.substancia_a_id=a.id AND i.substancia_b_id=b.id) LIMIT 1"
    ).fetchone()
    pv = p.prever([par], com_explicacao=False)[0]
    ok("par de teste realmente nao documentado", not pv.ja_documentado,
       "%s x %s" % (pv.nome_a, pv.nome_b))
    try:
        p.contrato_achado(pv)
        ok("contrato_achado recusa modelo EXPERIMENTAL", False, "aceitou")
    except predizer.ModeloNaoHomologado:
        ok("contrato_achado recusa modelo EXPERIMENTAL", True)
    ok("previsao em [0,1]", 0.0 <= pv.probabilidade <= 1.0,
       "%.4f" % pv.probabilidade)
    ok("previsao simetrica",
       abs(pv.probabilidade
           - p.prever([(par[1], par[0])],
                      com_explicacao=False)[0].probabilidade) < 1e-12)
    texto = p.texto(pv)
    for exigido in ("PREVISÃO", "Nenhuma bula", "farmacêutico"):
        ok("o texto da tela contem %r" % exigido, exigido in texto)
    ok("o texto nao afirma mecanismo",
       not any(w in texto.lower() for w in ("inibe a enzima", "induz a enzima",
                                            "mecanismo confirmado")))

    print("\nOS MOTORES NAO DEPENDEM DE ML")
    for arq_ in ("rules/motor_conciliacao.py", "rules/motor_horarios.py",
                 "rules/_prioridade.py", "app/servicos.py", "app/web.py",
                 "app/relatorio.py", "app/busca.py"):
        texto_py = (RAIZ / arq_).read_text(encoding="utf-8")
        ok("%s nao importa nada de ml/" % arq_,
           "from ml" not in texto_py and "import ml" not in texto_py
           and "70_predizer" not in texto_py)
    # Procurar a PALAVRA "sklearn" casava com o comentario do modulo 13, que
    # diz justamente que o motor NAO carrega sklearn. O que interessa e a
    # importacao de verdade, entao a busca e por linha de import.
    import re as _re
    padrao = _re.compile(r"^\s*(import\s+sklearn|from\s+sklearn|"
                         r"import\s+joblib|import\s+pickle|import\s+numpy)",
                         _re.M)
    carrega = [a for a in ("rules/motor_conciliacao.py", "rules/motor_horarios.py",
                           "app/servicos.py", "app/web.py")
               if padrao.search((RAIZ / a).read_text(encoding="utf-8"))]
    ok("nenhum modelo e carregado no caminho deterministico", not carrega,
       str(carrega) if carrega else "4 arquivos conferidos")

    print("\nA INTERFACE JA SABE MOSTRAR PREVISTO")
    for arq_ in ("app/templates/achado.html", "app/templates/resultados.html"):
        ok("%s trata status PREVISTO" % arq_,
           "PREVISTO" in (RAIZ / arq_).read_text(encoding="utf-8"))
    rot = (RAIZ / "app" / "rotulos.py").read_text(encoding="utf-8")
    ok("rotulos.py tem texto em pt-BR para PREVISTO", "PREVISTO" in rot)
    ok("o texto de PREVISTO nega evidencia publicada",
       "não de evidência publicada" in rot or "nao de evidencia publicada" in rot)

    print("\n" + "=" * 74)
    if falhas:
        print("REGRESSAO DE ML FALHOU em %d garantia(s):" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("NENHUMA REGRESSAO — as garantias de ML continuam de pe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
