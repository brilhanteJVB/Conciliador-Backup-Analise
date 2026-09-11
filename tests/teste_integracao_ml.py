# -*- coding: utf-8 -*-
"""
V1 — INTEGRACAO DO MODELO PREDITIVO (Fase 8).

Fecha a costura que a Fase 7 deixou pronta e desligada: motor deterministico +
modelo + `achado` + interface, sem que a previsao substitua evidencia.

TUDO ACONTECE NUMA COPIA DO BANCO. O teste precisa HOMOLOGAR um modelo para
exercitar o caminho — e homologar e ato humano registrado (D-042). Fazer isso
no banco de producao seria o teste ligando em producao aquilo que a Fase 7
decidiu manter desligado. A copia e apagada no fim.

O QUE E CONFERIDO
-----------------
  1  a view      as quatro travas de `vw_predicao_liberada`, uma a uma
  2  o motor     modulo 13 produz o achado PREVISTO com os campos certos
  3  o esquema   o banco aceita gravar esse achado e recusa as variantes erradas
  4  a separacao previsao nunca aparece onde ha documento; nunca conta no KPI
  5  a interface bloco proprio, painel de rastreabilidade, relatorio separado
  6  o desligar  sem modelo ativo, o sistema volta a ser exatamente o de antes

Uso: python tests/teste_integracao_ml.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline", "tests"):
    sys.path.insert(0, str(RAIZ / _p))

BANCO = RAIZ / "database" / "conciliador.db"
falhas = []


def add_med(c, con, codigo, nome):
    """Adiciona pelo mesmo caminho da tela: busca -> escolha -> POST."""
    import busca
    achados = busca.buscar_medicamento(con, nome)
    r = c.post("/a/%s/medicamento" % codigo,
               data={"nome_relatado": nome,
                     "escolha": achados[0].chave if achados else "",
                     "lista": "EM_USO", "origem": "PRESCRITO"})
    return r.status_code


def ok(desc, cond, detalhe=""):
    print("  [%s] %-56s %s" % ("OK " if cond else "FALHA", desc,
                              str(detalhe)[:60]))
    if not cond:
        falhas.append(desc)


def par_sem_documento(con):
    """Duas substancias com produto ativo e SEM interacao documentada."""
    return con.execute(
        "SELECT a.id, a.nome_dcb, b.id, b.nome_dcb "
        "FROM substancia a, substancia b "
        "WHERE a.id < b.id AND a.n_produtos_ativos > 0 AND b.n_produtos_ativos > 0 "
        "AND a.atc_codigo IS NOT NULL AND b.atc_codigo IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM interacao_substancia i "
        "                 WHERE i.substancia_a_id=a.id AND i.substancia_b_id=b.id) "
        "LIMIT 1").fetchone()


def par_com_documento(con):
    return con.execute(
        "SELECT a.id, a.nome_dcb, b.id, b.nome_dcb FROM interacao_substancia i "
        "JOIN substancia a ON a.id=i.substancia_a_id "
        "JOIN substancia b ON b.id=i.substancia_b_id "
        "WHERE a.n_produtos_ativos > 0 AND b.n_produtos_ativos > 0 LIMIT 1"
    ).fetchone()


def main() -> int:
    print("=" * 74)
    print("V1 — INTEGRACAO DO MODELO PREDITIVO")
    print("=" * 74)
    tmpdir = Path(tempfile.mkdtemp())
    copia = tmpdir / "conciliador.db"
    shutil.copy(BANCO, copia)

    import servicos as sv
    sv.BANCO = copia                      # a aplicacao inteira passa a ler a copia
    import web                            # noqa: F401  (usa sv.conectar)
    from motor_conciliacao import conciliar_atendimento

    try:
        con = sqlite3.connect(copia)
        con.execute("PRAGMA foreign_keys = ON")

        if con.execute("SELECT COUNT(*) FROM modelo WHERE versao="
                       "'1.0-boosting'").fetchone()[0] == 0:
            print("\n" + "=" * 74)
            print("BANCO SEM MODELO REGISTRADO — este teste precisa de um")
            print("modelo treinado para exercitar a integracao. Rode")
            print("`python ml/executar_tudo.py` e tente de novo.")
            print("=" * 74)
            return 0
        a_id, a_nome, b_id, b_nome = par_sem_documento(con)
        d_a, d_a_nome, d_b, d_b_nome = par_com_documento(con)
        print("  par SEM documento: %s × %s" % (a_nome, b_nome))
        print("  par COM documento: %s × %s" % (d_a_nome, d_b_nome))

        modelo_id = con.execute(
            "SELECT id FROM modelo WHERE versao='1.0-boosting'").fetchone()[0]
        # A copia herda as 600 previsoes da fila de curadoria. Elas sao dado
        # legitimo, mas aqui atrapalham: o teste precisa controlar quantas
        # linhas a view deve devolver. Sao removidas SO NA COPIA.
        herdadas = con.execute("SELECT COUNT(*) FROM predicao").fetchone()[0]
        con.execute("DELETE FROM predicao")
        print("  (%d previsoes da fila de curadoria removidas da copia)"
              % herdadas)
        fatores = [{"atributo": "atc_n2_igual", "valor": 1.0, "efeito": 0.21},
                   {"atributo": "adm_lados_com_regra", "valor": 2.0,
                    "efeito": 0.09}]
        con.execute(
            "INSERT OR REPLACE INTO predicao (modelo_id,substancia_a_id,"
            "substancia_b_id,probabilidade,probabilidade_calibrada,"
            "explicacao_json) VALUES (?,?,?,?,?,?)",
            (modelo_id, a_id, b_id, 0.9312, 0.8840,
             json.dumps(fatores, ensure_ascii=False)))
        # previsao tambem para o par DOCUMENTADO: a view tem de escondê-la
        con.execute(
            "INSERT OR REPLACE INTO predicao (modelo_id,substancia_a_id,"
            "substancia_b_id,probabilidade,probabilidade_calibrada) "
            "VALUES (?,?,?,?,?)", (modelo_id, d_a, d_b, 0.99, 0.99))
        con.commit()

        # ------------------------------------------------------ 1. a view
        print("\n1. AS QUATRO TRAVAS DA VIEW")
        n = lambda: con.execute("SELECT COUNT(*) FROM vw_predicao_liberada"
                                ).fetchone()[0]
        ok("modelo EXPERIMENTAL e inativo -> view vazia", n() == 0, n())

        con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1 "
                    "WHERE id=?", (modelo_id,))
        con.commit()
        ok("homologado e ativo, mas SEM limiar -> ainda vazia", n() == 0,
           "fail-closed")

        con.execute("UPDATE modelo SET limiar_alerta=0.85 WHERE id=?",
                    (modelo_id,))
        con.commit()
        ok("com limiar 0,85 -> a previsao acima do limiar aparece", n() == 1, n())
        vis = con.execute("SELECT substancia_a_id, substancia_b_id "
                          "FROM vw_predicao_liberada").fetchone()
        ok("o par que aparece e o SEM documento", vis == (a_id, b_id), vis)
        ok("o par COM documento NAO aparece, mesmo com prob 0,99",
           con.execute("SELECT COUNT(*) FROM vw_predicao_liberada WHERE "
                       "substancia_a_id=? AND substancia_b_id=?",
                       (d_a, d_b)).fetchone()[0] == 0)

        con.execute("UPDATE modelo SET limiar_alerta=0.95 WHERE id=?",
                    (modelo_id,))
        con.commit()
        ok("limiar acima da probabilidade -> some", n() == 0)
        con.execute("UPDATE modelo SET limiar_alerta=0.85 WHERE id=?",
                    (modelo_id,))
        con.execute("UPDATE predicao SET status='REVISADA_RECUSADA',"
                    "revisado_por='Farm. Teste' WHERE substancia_a_id=? "
                    "AND substancia_b_id=?", (a_id, b_id))
        con.commit()
        ok("previsao recusada por farmaceutico -> some", n() == 0)
        con.execute("UPDATE predicao SET status='NAO_REVISADA',"
                    "revisado_por=NULL WHERE substancia_a_id=? "
                    "AND substancia_b_id=?", (a_id, b_id))
        con.commit()
        ok("volta a aparecer quando o status volta", n() == 1)

        # -------------------------------------------------- 2 e 3. o motor
        print("\n2. O MOTOR — modulo 13")
        c = web.app.test_client()
        web.app.config["TESTING"] = True
        r = c.post("/novo", data={"nome": "Paciente V1 ML",
                                  "farmaceutico": "Farm. Teste",
                                  "crf": "CRF-TS 001"})
        codigo = r.headers["Location"].split("/a/")[1].split("/")[0]
        for sid, nome in ((a_id, a_nome), (b_id, b_nome),
                          (d_a, d_a_nome), (d_b, d_b_nome)):
            add_med(c, con, codigo, nome)

        at_id = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                            (codigo,)).fetchone()[0]
        res = conciliar_atendimento(con, at_id)
        previstos = [x for x in res.achados if x.natureza == "PREVISTO"]
        docs = [x for x in res.achados if x.natureza != "PREVISTO"]
        ok("o motor produziu exatamente 1 achado PREVISTO",
           len(previstos) == 1, "%d previstos, %d documentados"
           % (len(previstos), len(docs)))
        if not previstos:
            raise SystemExit(1)
        p = previstos[0]
        ok("origem_achado = MODELO", p.origem_achado == "MODELO")
        ok("status_informacao = PREVISTO", p.status_informacao == "PREVISTO")
        ok("classificacao = POSSIVEL", p.classificacao == "POSSIVEL")
        ok("probabilidade = a CALIBRADA, nao a bruta",
           abs(p.probabilidade_modelo - 0.8840) < 1e-9, p.probabilidade_modelo)
        ok("origem_afirmacao aponta para predicao.<id>",
           p.origem_afirmacao.startswith("predicao."), p.origem_afirmacao)
        ok("gravidade da fonte AUSENTE (o modelo nao gradua)",
           p.gravidade_fonte is None)
        ok("nivel de evidencia AUSENTE", p.nivel_evidencia is None)
        ok("nenhuma evidencia documental anexada", len(p.evidencias) == 0)
        ok("confianca do sistema BAIXA", p.confianca_sistema == "BAIXA")
        ok("prioridade INFORMATIVO (teto por definicao)",
           p.prioridade == "INFORMATIVO", p.prioridade)
        ok("exige revisao profissional", p.requer_revisao_profissional == 1)
        ok("chave de grupo distinta da do par documentado",
           p.grupo_chave.startswith("PREVISTA:"), p.grupo_chave)
        ok("metodo_deteccao nomeia modelo e versao",
           "1.0-boosting" in p.metodo_deteccao, p.metodo_deteccao)
        for termo in ("NÃO HÁ INTERAÇÃO DOCUMENTADA", "PREVISÃO estatística",
                      "não estima gravidade", "semente", "Requer verificação"):
            ok("a explicacao contem %r" % termo[:28], termo in p.explicacao)
        ok("a explicacao nao afirma mecanismo farmacologico",
           "mecanismo farmacológico" not in p.explicacao
           or "não um mecanismo" in p.explicacao)
        ok("o par DOCUMENTADO gerou achado documentado, nao previsto",
           any(x.substancia_a_id == d_a and x.substancia_b_id == d_b
               and x.natureza != "PREVISTO" for x in docs))
        ok("nenhum achado documentado virou previsto",
           all(x.origem_achado == "REGRA" for x in docs))

        print("\n3. O RESUMO SEPARA")
        ok("resumo conta previstos a parte",
           res.resumo["achados_previstos"] == 1, res.resumo["achados_previstos"])
        ok("previsto NAO entra na contagem de achados",
           res.resumo["achados"] == len(docs), res.resumo["achados"])
        soma_prio = sum(res.resumo[k] for k in
                        ("criticos", "altos", "moderados", "baixos",
                         "informativos"))
        ok("previsto NAO entra na escala de prioridade",
           soma_prio == len(docs), "%d prioridades, %d documentados"
           % (soma_prio, len(docs)))

        print("\n4. O BANCO ACEITA GRAVAR, E RECUSA O ERRADO")
        res2 = conciliar_atendimento(con, at_id, persistir=True)
        gravado = con.execute(
            "SELECT natureza, origem_achado, probabilidade_modelo, "
            "origem_afirmacao, nivel_evidencia, gravidade_fonte FROM achado "
            "WHERE natureza='PREVISTO'").fetchone()
        ok("achado PREVISTO gravado no banco", gravado is not None)
        if gravado:
            ok("gravado com origem MODELO e ponteiro para predicao",
               gravado[1] == "MODELO" and gravado[3].startswith("predicao."),
               gravado[3])
            ok("gravado sem nivel de evidencia nem gravidade",
               gravado[4] is None and gravado[5] is None)
        n_ev = con.execute(
            "SELECT COUNT(*) FROM achado_evidencia e JOIN achado a "
            "ON a.id=e.achado_id WHERE a.natureza='PREVISTO'").fetchone()[0]
        ok("nenhuma linha em achado_evidencia para previsao", n_ev == 0, n_ev)

        print("\n5. A INTERFACE")
        html = c.get("/a/%s/resultados" % codigo).data.decode("utf-8")
        # Procurar por "PREVISTO POR MODELO" casaria com o COMENTARIO HTML da
        # seccao, que e renderizado mesmo quando o bloco esta vazio — foi assim
        # que este teste deu falso positivo na primeira execucao. O marcador
        # `id="bloco-previsto"` so existe dentro do `{% if previstos %}`.
        ok("a tela tem bloco PREVISTO POR MODELO",
           'id="bloco-previsto"' in html)
        ok("o bloco diz que nao e alerta",
           "não é alerta e não é interação documentada" in html)
        # "Evid" e "nenhuma" soltos casam com quase qualquer pagina — a
        # Fase 9 mostrou que esta asserçao nao provava nada. O rotulo e o
        # valor sao dois <div> irmaos, e a conferencia e dentro do bloco.
        _bloco = html.split('id="bloco-previsto"')[-1]
        ok("o bloco mostra 'Evidência documental' com valor 'nenhuma'",
           ">Evidência documental</div>" in _bloco
           and ">nenhuma</div>" in _bloco)
        i_prev = html.find('id="bloco-previsto"')
        i_prio = max(html.find('class="prio %s"' % p_)
                     for p_ in ("CRITICO", "ALTO", "MODERADO", "BAIXO",
                                "INFORMATIVO"))
        ok("o bloco previsto vem DEPOIS dos blocos de prioridade",
           i_prev > i_prio > -1, "previsto em %d, prioridade em %d"
           % (i_prev, i_prio))

        det = c.get("/a/%s/achado?chave=%s"
                    % (codigo, p.grupo_chave)).data.decode("utf-8")
        ok("o detalhe diz que nao ha evidencia documental",
           "Não há evidência documental para este par" in det)
        for campo in ("Rastreabilidade da previsão", "1.0-boosting",
                      "Limiar de alerta", "Versão dos dados", "Semente",
                      "Registrada em", "Situação da previsão",
                      "O que o modelo pesou", "atc_n2_igual"):
            ok("o detalhe mostra %r" % campo[:26], campo in det)
        ok("o detalhe avisa que a contribuicao nao e SHAP",
           "Não é SHAP" in det or "não é SHAP" in det)
        ok("o detalhe nega mecanismo farmacologico",
           "não é mecanismo" in det)

        txt = c.get("/a/%s/relatorio.txt" % codigo).data.decode("utf-8")
        ok("o relatorio tem secao propria de previsto",
           "PREVISTO POR MODELO — NAO E INTERACAO DOCUMENTADA" in txt)
        ok("o relatorio declara evidencia NENHUMA",
           "evidência documental: NENHUMA" in txt)
        i_ach = txt.find("ACHADOS")
        i_pre = txt.find("PREVISTO POR MODELO")
        ok("no relatorio, previsto vem depois dos achados", i_pre > i_ach > -1)

        print("\n6. DESLIGAR O MODELO DEVOLVE O SISTEMA AO ESTADO ANTERIOR")
        con.execute("UPDATE modelo SET ativo=0 WHERE id=?", (modelo_id,))
        con.commit()
        res3 = conciliar_atendimento(con, at_id)
        ok("sem modelo ativo, zero achados previstos",
           not [x for x in res3.achados if x.natureza == "PREVISTO"])
        ok("os achados documentados continuam identicos",
           len([x for x in res3.achados if x.natureza != "PREVISTO"]) == len(docs))
        html2 = c.get("/a/%s/resultados" % codigo).data.decode("utf-8")
        ok("a tela nao mostra mais o bloco previsto",
           'id="bloco-previsto"' not in html2)
        con.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 74)
    if falhas:
        print("V1 FALHOU em %d verificacao(oes):" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("V1 OK — a previsao chega ao farmaceutico sem se disfarcar de fato")
    return 0


if __name__ == "__main__":
    sys.exit(main())
