# -*- coding: utf-8 -*-
"""
V2 — VERIFICACAO INDEPENDENTE DA INTEGRACAO (Fase 8).

Nao repete o V1. O V1 pergunta "funciona?" chamando o motor e lendo o objeto
que ele devolve. Este aqui parte do lado oposto: le o **HTML e o SQL cru**, sem
usar as estruturas do motor, e procura especificamente os oito modos de falha
que a especificacao §6 lista.

OS OITO ALVOS
-------------
  1  previsao apresentada como fato
  2  perda de rastreabilidade
  3  vazamento de dados (previsao de um paciente aparecendo em outro)
  4  erro de probabilidade (numero exibido != numero gravado)
  5  previsao associada ao paciente errado
  6  duplicacao de alerta (o mesmo par duas vezes)
  7  conflito entre regra e modelo
  8  regressao na aplicacao

METODO DIFERENTE, DE PROPOSITO
------------------------------
  * o achado e lido por SQL direto na tabela, nao pelo objeto do motor;
  * a probabilidade exibida e extraida do HTML por expressao regular e
    comparada com a do banco;
  * o isolamento entre pacientes e testado com DOIS atendimentos simultaneos;
  * o conflito regra x modelo e provocado de proposito, inserindo previsao
    para um par que TEM documento.

Uso: python tests/verificacao_integracao_ml.py
"""
from __future__ import annotations

import re
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


def main() -> int:
    print("=" * 74)
    print("V2 — VERIFICACAO INDEPENDENTE DA INTEGRACAO")
    print("=" * 74)
    tmpdir = Path(tempfile.mkdtemp())
    copia = tmpdir / "conciliador.db"
    shutil.copy(BANCO, copia)

    import servicos as sv
    sv.BANCO = copia
    import web
    web.app.config["TESTING"] = True
    c = web.app.test_client()

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
        mid = con.execute("SELECT id FROM modelo WHERE versao='1.0-boosting'"
                          ).fetchone()[0]

        # dois pares sem documento, um para cada paciente — o isolamento e
        # testado com dados DIFERENTES, nao com o mesmo par duas vezes
        # OS DOIS PARES TEM DE SER DISJUNTOS. Um `LIMIT 2` cru devolve pares
        # que compartilham substancia (interferon x abacavir e interferon x
        # abatacepte), e ai "o paciente 2 nao recebe o par do outro" falha por
        # construcao do teste, nao por vazamento. Foi o primeiro achado desta
        # verificacao — e era defeito do fixture.
        pool = con.execute(
            "SELECT id, nome_dcb FROM substancia WHERE n_produtos_ativos > 0 "
            "AND atc_codigo IS NOT NULL ORDER BY id LIMIT 60").fetchall()
        documentado = lambda x, y: con.execute(
            "SELECT 1 FROM interacao_substancia WHERE substancia_a_id=? "
            "AND substancia_b_id=? LIMIT 1",
            (min(x, y), max(x, y))).fetchone() is not None
        pares, usados = [], set()
        for i in range(len(pool)):
            if len(pares) == 2:
                break
            if pool[i][0] in usados:
                continue
            for j in range(i + 1, len(pool)):
                if pool[j][0] in usados or documentado(pool[i][0], pool[j][0]):
                    continue
                a_, b_ = sorted((pool[i], pool[j]))
                pares.append((a_[0], a_[1], b_[0], b_[1]))
                usados |= {a_[0], b_[0]}
                break
        assert len(pares) == 2, "nao ha dois pares disjuntos sem documento"
        print("  par do paciente 1: %s × %s" % (pares[0][1], pares[0][3]))
        print("  par do paciente 2: %s × %s" % (pares[1][1], pares[1][3]))
        doc = con.execute(
            "SELECT a.id, a.nome_dcb, b.id, b.nome_dcb, i.gravidade "
            "FROM interacao_substancia i "
            "JOIN substancia a ON a.id=i.substancia_a_id "
            "JOIN substancia b ON b.id=i.substancia_b_id "
            "WHERE a.n_produtos_ativos>0 AND b.n_produtos_ativos>0 "
            "AND a.id NOT IN (%s) AND b.id NOT IN (%s) LIMIT 1"
            % (",".join(str(x) for x in usados),
               ",".join(str(x) for x in usados))).fetchone()

        probs = (0.9111, 0.8712)
        for (pa, _na, pb, _nb), pr in zip(pares, probs):
            con.execute(
                "INSERT OR REPLACE INTO predicao (modelo_id,substancia_a_id,"
                "substancia_b_id,probabilidade,probabilidade_calibrada) "
                "VALUES (?,?,?,?,?)", (mid, pa, pb, pr + 0.02, pr))
        # ---- alvo 7: previsao para um par que TEM documento
        con.execute(
            "INSERT OR REPLACE INTO predicao (modelo_id,substancia_a_id,"
            "substancia_b_id,probabilidade,probabilidade_calibrada) "
            "VALUES (?,?,?,?,?)", (mid, doc[0], doc[2], 0.999, 0.999))
        con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1, "
                    "limiar_alerta=0.80 WHERE id=?", (mid,))
        con.commit()

        codigos = []
        for i, (pa, na, pb, nb) in enumerate(pares):
            r = c.post("/novo", data={"nome": "Paciente V2 %d" % (i + 1),
                                      "farmaceutico": "Farm. Teste",
                                      "crf": "CRF-TS 002"})
            cod = r.headers["Location"].split("/a/")[1].split("/")[0]
            codigos.append(cod)
            for sid, nome in ((pa, na), (pb, nb), (doc[0], doc[1]),
                              (doc[2], doc[3])):
                add_med(c, con, cod, nome)
            c.post("/a/%s/analisar" % cod, data={})

        # =============================== 1. previsao apresentada como fato
        print("\n1. PREVISAO APRESENTADA COMO FATO")
        linhas = con.execute(
            "SELECT natureza, status_informacao, origem_achado, "
            "nivel_evidencia, gravidade_fonte, probabilidade_modelo, "
            "confianca_sistema, prioridade FROM achado "
            "WHERE subtipo='INTERACAO_PREVISTA'").fetchall()
        ok("ha achados previstos gravados", len(linhas) >= 2, len(linhas))
        ok("todos com natureza PREVISTO",
           all(l[0] == "PREVISTO" for l in linhas))
        ok("nenhum com status DOCUMENTADO ou REVISADO",
           all(l[1] == "PREVISTO" for l in linhas))
        ok("nenhum com nivel de evidencia de publicacao",
           all(l[3] is None for l in linhas))
        ok("nenhum com gravidade de fonte", all(l[4] is None for l in linhas))
        ok("nenhum com confianca ALTA", all(l[6] == "BAIXA" for l in linhas))
        ok("nenhum acima de INFORMATIVO",
           all(l[7] == "INFORMATIVO" for l in linhas))
        mistos = con.execute(
            "SELECT COUNT(*) FROM achado WHERE origem_achado='REGRA' "
            "AND probabilidade_modelo IS NOT NULL").fetchone()[0]
        ok("nenhum achado de regra carrega probabilidade", mistos == 0)

        html = c.get("/a/%s/resultados" % codigos[0]).data.decode("utf-8")
        bloco = html[html.find('id="bloco-previsto"'):]
        ok("o texto do bloco nunca usa a palavra 'documentada' afirmando",
           "interação documentada" not in bloco.split("Não avaliado")[0]
           or "não é interação documentada" in bloco)

        # ==================================== 2. perda de rastreabilidade
        print("\n2. RASTREABILIDADE")
        for l in con.execute(
                "SELECT origem_afirmacao, metodo_deteccao FROM achado "
                "WHERE subtipo='INTERACAO_PREVISTA'"):
            ok("origem_afirmacao aponta para predicao existente",
               l[0].startswith("predicao.") and con.execute(
                   "SELECT 1 FROM predicao WHERE id=?",
                   (int(l[0].split(".")[1]),)).fetchone() is not None, l[0])
            ok("metodo_deteccao nomeia modelo e versao",
               "1.0-boosting" in l[1], l[1])
        # da previsao chega-se a semente, versao dos dados e limiar
        cadeia = con.execute(
            "SELECT m.semente, m.versao_dados, m.limiar_alerta, "
            "m.protocolo_validacao FROM achado a "
            "JOIN predicao p ON p.id = CAST(SUBSTR(a.origem_afirmacao,10) AS INT) "
            "JOIN modelo m ON m.id=p.modelo_id "
            "WHERE a.subtipo='INTERACAO_PREVISTA' LIMIT 1").fetchone()
        ok("do achado chega-se a semente, versao dos dados e limiar",
           cadeia is not None and all(x is not None for x in cadeia), cadeia)

        # ================================= 3 e 5. vazamento entre pacientes
        print("\n3. ISOLAMENTO ENTRE PACIENTES")
        for i, cod in enumerate(codigos):
            at = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                             (cod,)).fetchone()[0]
            prev = con.execute(
                "SELECT a.item_a, a.item_b FROM achado a "
                "JOIN conciliacao c ON c.id=a.conciliacao_id "
                "WHERE c.atendimento_id=? AND a.subtipo='INTERACAO_PREVISTA'",
                (at,)).fetchall()
            esperado = {pares[i][1], pares[i][3]}
            obtido = set()
            for x, y in prev:
                obtido |= {x, y}
            ok("paciente %d recebe SO o seu par previsto" % (i + 1),
               obtido == esperado, "%s vs %s" % (obtido, esperado))
            outro = {pares[1 - i][1], pares[1 - i][3]}
            ok("paciente %d NAO recebe o par do outro" % (i + 1),
               not (obtido & outro))
            h = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
            ok("a tela do paciente %d nao cita o par do outro" % (i + 1),
               not any(n in h[h.find('id="bloco-previsto"'):] for n in outro
                       if h.find('id="bloco-previsto"') > -1))

        # ================================= 4. erro de probabilidade
        print("\n4. A PROBABILIDADE EXIBIDA E A GRAVADA")
        for i, cod in enumerate(codigos):
            h = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
            trecho = h[h.find('id="bloco-previsto"'):]
            m = re.search(r"Probabilidade estimada</div>\s*<div class=\"valor\">"
                          r"(\d+)%", trecho)
            ok("a tela do paciente %d mostra a probabilidade" % (i + 1),
               m is not None)
            if m:
                esperado = round(100 * probs[i])
                ok("paciente %d: exibido %s%% == calibrado %d%%"
                   % (i + 1, m.group(1), esperado),
                   int(m.group(1)) == esperado)
            # a bruta NAO e a exibida
            ok("a probabilidade exibida nao e a bruta",
               ("%d%%" % round(100 * (probs[i] + 0.02))) not in
               (m.group(0) if m else ""))
        no_banco = con.execute(
            "SELECT a.probabilidade_modelo, p.probabilidade_calibrada, "
            "p.probabilidade FROM achado a JOIN predicao p "
            "ON p.id = CAST(SUBSTR(a.origem_afirmacao,10) AS INT) "
            "WHERE a.subtipo='INTERACAO_PREVISTA'").fetchall()
        ok("o achado guarda a probabilidade CALIBRADA, nao a bruta",
           all(abs(x[0] - x[1]) < 1e-9 for x in no_banco))
        ok("nenhuma probabilidade fora de [0,1]",
           all(0.0 <= x[0] <= 1.0 for x in no_banco))

        # ==================================== 6. duplicacao de alerta
        print("\n6. DUPLICACAO")
        dup = con.execute(
            "SELECT COUNT(*) FROM (SELECT conciliacao_id, substancia_a_id, "
            "substancia_b_id, COUNT(*) n FROM achado WHERE status='PRINCIPAL' "
            "AND substancia_b_id IS NOT NULL GROUP BY 1,2,3 HAVING n>1)"
        ).fetchone()[0]
        ok("nenhum par com dois achados principais no mesmo atendimento",
           dup == 0, dup)
        chaves = con.execute(
            "SELECT COUNT(*) FROM (SELECT conciliacao_id, grupo_chave, "
            "COUNT(*) n FROM achado WHERE status='PRINCIPAL' "
            "GROUP BY 1,2 HAVING n>1)").fetchone()[0]
        ok("nenhuma chave de grupo repetida", chaves == 0, chaves)

        # ============================ 7. conflito entre regra e modelo
        print("\n7. CONFLITO ENTRE REGRA E MODELO")
        conflito = con.execute(
            "SELECT COUNT(*) FROM achado WHERE subtipo='INTERACAO_PREVISTA' "
            "AND substancia_a_id=? AND substancia_b_id=?",
            (doc[0], doc[2])).fetchone()[0]
        ok("o par COM documento nao gerou achado previsto, apesar de "
           "previsao 0,999", conflito == 0, conflito)
        documentado = con.execute(
            "SELECT COUNT(*) FROM achado WHERE natureza<>'PREVISTO' "
            "AND substancia_a_id=? AND substancia_b_id=?",
            (doc[0], doc[2])).fetchone()[0]
        ok("e o achado documentado desse par continua existindo",
           documentado >= 1, documentado)
        ok("a view esconde a previsao do par documentado",
           con.execute("SELECT COUNT(*) FROM vw_predicao_liberada WHERE "
                       "substancia_a_id=? AND substancia_b_id=?",
                       (doc[0], doc[2])).fetchone()[0] == 0)

        # ================================ 8. regressao na aplicacao
        print("\n8. REGRESSAO NA APLICACAO")
        for rota, esperado in ((("/a/%s/resultados" % codigos[0]), 200),
                               (("/a/%s/relatorio" % codigos[0]), 200),
                               (("/a/%s/relatorio.txt" % codigos[0]), 200),
                               (("/a/%s/conciliacao" % codigos[0]), 200),
                               (("/a/%s/medicamentos" % codigos[0]), 200),
                               ("/", 200)):
            ok("rota %s responde %d" % (rota[:34], esperado),
               c.get(rota).status_code == esperado)
        rel = c.get("/a/%s/relatorio" % codigos[0]).data.decode("utf-8")
        i_ach = rel.find("<h2>Achados</h2>")
        i_prev = rel.find("Previsto por modelo")
        ok("no relatorio HTML, previsto vem depois dos achados",
           i_prev > i_ach > -1, "%d > %d" % (i_prev, i_ach))
        ok("o relatorio HTML declara ausencia de evidencia",
           "Nenhuma fonte do acervo afirma os pares abaixo" in rel)

        # o sistema com o modelo DESLIGADO tem de voltar ao anterior
        con.execute("UPDATE modelo SET ativo=0 WHERE id=?", (mid,))
        con.commit()
        c.post("/a/%s/analisar" % codigos[0], data={})
        at0 = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (codigos[0],)).fetchone()[0]
        restou = con.execute(
            "SELECT COUNT(*) FROM achado a JOIN conciliacao c "
            "ON c.id=a.conciliacao_id WHERE c.atendimento_id=? "
            "AND a.subtipo='INTERACAO_PREVISTA' AND c.id=("
            "SELECT MAX(id) FROM conciliacao WHERE atendimento_id=?)",
            (at0, at0)).fetchone()[0]
        ok("desativado o modelo, a nova analise nao tem previsto", restou == 0,
           restou)
        con.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 74)
    if falhas:
        print("V2 FALHOU em %d verificacao(oes):" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("V2 OK — os oito modos de falha foram procurados e nao encontrados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
