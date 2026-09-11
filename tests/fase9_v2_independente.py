# -*- coding: utf-8 -*-
"""
FASE 9 — V2: AUDITORIA INDEPENDENTE DO SISTEMA INTEIRO.

A V1 executa o sistema pelo caminho normal e confere o que ele devolve. Se o
caminho normal estiver errado, ela concorda com o erro. Esta verificacao usa
FERRAMENTAS DIFERENTES a proposito:

  A  SQL cru               a conciliacao refeita em SQL, sem tocar no motor
  B  HTML lido como texto  a pagina contada por regex, sem as estruturas
  C  recontagem do banco   contagens proprias contra o que a documentacao diz
  D  segunda implementacao as quatro travas da view reescritas em Python
  E  calibracao por fora   np.interp reimplementado sem numpy, 600 previsoes
  F  leitura do codigo     o que os arquivos importam, e o que nao importam
  G  atendimento por SQL   dois pacientes montados sem passar pela interface
  H  cacada de afirmacao   previsao apresentada como fato, em HTML e em texto

O QUE ELA PROCURA, especificamente: defeito de INTEGRACAO que passou pelas
fases anteriores. Cada fase validou o seu modulo; o que ninguem validou e a
costura.

Uso: python tests/fase9_v2_independente.py
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "database" / "conciliador.db"

PASSOS, FALHAS = [], []


def checa(caminho, nome, ok, detalhe=""):
    PASSOS.append((caminho, nome, ok, detalhe))
    if not ok:
        FALHAS.append((caminho, nome, detalhe))
    print("   %s %-54s %s" % ("OK  " if ok else "ERRO", nome[:54],
                              str(detalhe)[:58]))


# =====================================================================
# A — SQL CRU: a conciliacao refeita sem tocar no motor
# =====================================================================
def caminho_a(con, sv, codigo):
    print("\nA. SQL CRU — a conciliação refeita à mão, sem o motor\n")
    aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                      (codigo,)).fetchone()[0]

    # Pares farmaco x farmaco documentados, calculados so com SQL. O motor
    # nao participa desta conta.
    pares_sql = {tuple(sorted(r)) for r in con.execute(
        "SELECT DISTINCT m1.substancia_id, m2.substancia_id "
        "FROM atendimento_medicamento m1 JOIN atendimento_medicamento m2 "
        "  ON m1.atendimento_id = m2.atendimento_id "
        " AND m1.substancia_id < m2.substancia_id "
        "JOIN vw_interacao_liberada v "
        "  ON v.substancia_a_id = m1.substancia_id "
        " AND v.substancia_b_id = m2.substancia_id "
        "WHERE m1.atendimento_id = ?", (aid,))}

    res = sv.resultado_atual(con, codigo)
    pares_motor = {tuple(sorted((a.substancia_a_id, a.substancia_b_id)))
                   for a in res.achados
                   if a.tipo == "FARMACO_FARMACO"
                   and a.natureza == "DOCUMENTADO"
                   and a.substancia_a_id and a.substancia_b_id}
    checa("A", "o SQL cru encontra os mesmos pares que o motor",
          pares_sql == pares_motor,
          "SQL %d · motor %d · só num deles: %s"
          % (len(pares_sql), len(pares_motor),
             sorted(pares_sql ^ pares_motor)[:2]))

    # Gravidade: a maior gravidade da fonte, calculada por SQL.
    ordem = {"MAIOR": 3, "MODERADA": 2, "MENOR": 1, "NAO_DETERMINADA": 0}
    for a, b in sorted(pares_sql)[:3]:
        graves = [g for (g,) in con.execute(
            "SELECT gravidade FROM vw_interacao_liberada "
            "WHERE substancia_a_id=? AND substancia_b_id=?", (a, b))]
        pior = max(graves, key=lambda g: ordem.get(g, 0))
        do_motor = next(x.gravidade_fonte for x in res.achados
                        if x.tipo == "FARMACO_FARMACO"
                        and tuple(sorted((x.substancia_a_id,
                                          x.substancia_b_id))) == (a, b))
        checa("A", "gravidade do par %d×%d bate com o SQL" % (a, b),
              pior == do_motor, "%s vs %s" % (pior, do_motor))

    # Duplicidade de 4o nivel ATC, por SQL. A comparacao e por CODIGO DE
    # CLASSE, nao por par de substancias: o achado de classe nao preenche
    # `substancia_a_id` de proposito — a classe pode reunir mais de duas
    # substancias, e escolher duas para representar seria arbitrario. A
    # primeira versao desta conferencia exigia os dois ids e acusou
    # divergencia onde nao havia.
    dup_sql = {r[0] for r in con.execute(
        "SELECT DISTINCT substr(s1.atc_codigo,1,5) FROM atendimento_medicamento m1 "
        "JOIN atendimento_medicamento m2 ON m2.atendimento_id = "
        "  m1.atendimento_id AND m1.substancia_id < m2.substancia_id "
        "JOIN substancia s1 ON s1.id = m1.substancia_id "
        "JOIN substancia s2 ON s2.id = m2.substancia_id "
        "WHERE m1.atendimento_id = ? AND s1.atc_codigo IS NOT NULL "
        "AND s2.atc_codigo IS NOT NULL "
        "AND substr(s1.atc_codigo,1,5) = substr(s2.atc_codigo,1,5)", (aid,))}
    dup_motor = {a.grupo_chave.split(":", 1)[1] for a in res.achados
                 if a.subtipo == "MESMA_CLASSE_ATC4"}
    checa("A", "a duplicidade de classe bate com o SQL",
          dup_sql == dup_motor, "SQL %s · motor %s" % (sorted(dup_sql),
                                                       sorted(dup_motor)))
    checa("A", "o achado de classe não finge ser um par de substâncias",
          all(a.substancia_a_id is None and a.substancia_b_id is None
              for a in res.achados if a.subtipo == "MESMA_CLASSE_ATC4"),
          "alvo é a CLASSE, e a classe pode ter mais de duas")

    # O 5o nivel NAO pode ser usado: nenhum codigo de 5o nivel e partilhado.
    partilhado = con.execute(
        "SELECT COUNT(*) FROM (SELECT atc_codigo FROM substancia "
        "WHERE atc_codigo IS NOT NULL GROUP BY atc_codigo HAVING COUNT(*)>1)"
    ).fetchone()[0]
    checa("A", "nenhum código ATC de 5º nível é partilhado por 2 substâncias",
          partilhado == 0, "%d" % partilhado)


# =====================================================================
# B — HTML LIDO COMO TEXTO
# =====================================================================
def caminho_b(cliente, con, codigo):
    print("\nB. HTML — a página contada por regex, sem as estruturas\n")
    html = cliente.get("/a/%s/resultados" % codigo).data.decode("utf-8")

    blocos_doc = len(re.findall(r'class="achado (?:CRITICO|ALTO|MODERADO|'
                                r'BAIXO|INFORMATIVO)"', html))
    blocos_prev = len(re.findall(r'class="achado previsto"', html))
    aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                      (codigo,)).fetchone()[0]
    checa("B", "a página não mistura achado documentado com previsto",
          blocos_doc > 0 and blocos_prev >= 0
          and not re.search(r'class="achado previsto[^"]*(?:CRITICO|ALTO)',
                            html),
          "%d documentado(s) · %d previsto(s)" % (blocos_doc, blocos_prev))

    # O bloco previsto so pode aparecer DEPOIS do ultimo bloco de prioridade.
    fim_prio = max([m.end() for m in re.finditer(
        r'class="achado (?:CRITICO|ALTO|MODERADO|BAIXO|INFORMATIVO)"', html)]
        or [-1])
    inicio_prev = html.find('id="bloco-previsto"')
    checa("B", "nenhum bloco de prioridade aparece depois do previsto",
          inicio_prev == -1 or inicio_prev > fim_prio,
          "prioridade até %d · previsto em %d" % (fim_prio, inicio_prev))

    # Cada previsto tem de exibir probabilidade E a ausencia de evidencia.
    # A probabilidade sai pelo formatador unico: percentual, ou o teto
    # declarado quando a calibracao satura. "100%" nao pode aparecer — ver
    # `rules/_prioridade.percentual_previsao`.
    for pedaco in html.split('class="achado previsto"')[1:]:
        cabeca = pedaco[:2000]
        valores = re.findall(r'<div class="valor">([^<]+)</div>', cabeca)
        prob = [v.strip() for v in valores
                if "%" in v and ("acima de" in v or "abaixo de" in v
                                 or re.fullmatch(r"\d+%", v.strip()))]
        checa("B", "cada linha prevista mostra probabilidade e ausência",
              ">nenhuma</div>" in cabeca and bool(prob), prob[:1])
        checa("B", "a probabilidade da linha prevista não promete certeza",
              all(v.strip() not in ("100%", "0%") for v in prob), prob[:1])

    # O indicador de previstos nao pode estar dentro da escala de prioridade.
    painel = html.split('class="numero')
    escala = [p for p in painel if "previsto" not in p[:40]]
    checa("B", "o contador de previstos é um número à parte",
          any("previsto" in p[:40] for p in painel) == (blocos_prev > 0),
          "%d indicador(es) de prioridade" % len(escala))

    # Nenhum texto pode dizer que a previsao esta documentada.
    proibidas = ["previsão documentada", "interação documentada pelo modelo",
                 "o modelo confirma", "confirmado pelo modelo",
                 "evidência do modelo"]
    achadas = [t for t in proibidas if t in html.lower()]
    checa("B", "a página nunca chama previsão de documentada", not achadas,
          achadas)


# =====================================================================
# C — RECONTAGEM DO BANCO
# =====================================================================
def caminho_c(con):
    print("\nC. RECONTAGEM — contagens próprias, contra o que se afirma\n")
    tabelas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY 1")]
    views = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY 1")]
    checa("C", "44 tabelas, como a documentação afirma", len(tabelas) == 44,
          "%d" % len(tabelas))
    checa("C", "15 views, como a documentação afirma", len(views) == 15,
          "%d" % len(views))

    n_sub = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
    com_atc = con.execute("SELECT COUNT(*) FROM substancia "
                          "WHERE atc_codigo IS NOT NULL").fetchone()[0]
    checa("C", "2.094 substâncias", n_sub == 2094, "%d" % n_sub)
    checa("C", "1.159 substâncias com ATC (convergência do passo 68)",
          com_atc == 1159, "%d (%.1f%%)" % (com_atc, 100 * com_atc / n_sub))

    # Toda tabela de afirmacao precisa de chave de unicidade.
    afirmacao = ["interacao_substancia", "interacao_doenca", "interacao_item",
                 "interacao_habito", "regra_administracao", "regra_separacao",
                 "papel_farmacocinetico", "substancia_sinonimo"]
    sem_chave = []
    for t in afirmacao:
        sql = con.execute("SELECT sql FROM sqlite_master WHERE name=?",
                          (t,)).fetchone()[0]
        indices = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql LIKE '%UNIQUE%'", (t,))]
        if "UNIQUE" not in sql and not indices:
            sem_chave.append(t)
    checa("C", "toda tabela de afirmação tem chave de unicidade",
          not sem_chave, sem_chave)

    # Duplicata exata em tabela de afirmacao: recontada aqui, nao herdada.
    dups = con.execute(
        "SELECT COUNT(*) FROM (SELECT substancia_id, alvo_tipo, "
        "COALESCE(alvo_substancia_id,-1), COALESCE(alvo_item_id,-1), "
        "COALESCE(alvo_classe_atc,''), COALESCE(intervalo_horas,-1), "
        "sentido, COALESCE(motivo,''), fonte_id, COUNT(*) n "
        "FROM regra_separacao GROUP BY 1,2,3,4,5,6,7,8,9 HAVING n>1)"
    ).fetchone()[0]
    checa("C", "nenhuma regra de separação duplicada letra por letra",
          dups == 0, "%d" % dups)

    # Lote de carga: um por (script, arquivo), nunca um por execucao.
    repetidos = con.execute(
        "SELECT COUNT(*) FROM (SELECT script, documento_origem, COUNT(*) n "
        "FROM carga GROUP BY 1,2 HAVING n>1)").fetchone()[0]
    checa("C", "um lote de carga por (script, arquivo)", repetidos == 0,
          "%d repetido(s)" % repetidos)

    # Gravidade ausente e declarada, nao inventada.
    sem_grad = con.execute(
        "SELECT COUNT(*) FROM interacao_substancia "
        "WHERE gravidade='NAO_DETERMINADA'").fetchone()[0]
    total_int = con.execute("SELECT COUNT(*) FROM interacao_substancia"
                            ).fetchone()[0]
    checa("C", "a gravidade ausente continua declarada, não preenchida",
          sem_grad > 0,
          "%d de %d (%.1f%%) sem graduação na fonte"
          % (sem_grad, total_int, 100 * sem_grad / total_int))


# =====================================================================
# D — SEGUNDA IMPLEMENTACAO DAS QUATRO TRAVAS
# =====================================================================
def caminho_d(con):
    print("\nD. SEGUNDA IMPLEMENTAÇÃO — as quatro travas reescritas\n")
    documentados = {(a, b) for a, b in con.execute(
        "SELECT substancia_a_id, substancia_b_id FROM interacao_substancia")}
    modelos = {m[0]: dict(zip(("ativo", "status", "limiar", "versao"), m[1:]))
               for m in con.execute(
                   "SELECT id, ativo, status, limiar_alerta, versao "
                   "FROM modelo")}

    esperado = set()
    for (pid, mid, a, b, p, pc, st) in con.execute(
            "SELECT id, modelo_id, substancia_a_id, substancia_b_id, "
            "probabilidade, probabilidade_calibrada, status FROM predicao"):
        m = modelos.get(mid)
        if not m or m["ativo"] != 1 or m["status"] != "HOMOLOGADO":
            continue
        if m["limiar"] is None:
            continue
        exibida = pc if pc is not None else p
        if exibida < m["limiar"]:
            continue
        if st == "REVISADA_RECUSADA":
            continue
        if (a, b) in documentados:
            continue
        esperado.add(pid)

    da_view = {r[0] for r in con.execute(
        "SELECT predicao_id FROM vw_predicao_liberada")}
    checa("D", "a view devolve exatamente o que a reimplementação calcula",
          esperado == da_view,
          "reimpl %d · view %d · diferença %s"
          % (len(esperado), len(da_view), sorted(esperado ^ da_view)[:3]))

    # A trava 4 so funciona porque as duas tabelas usam a MESMA ordem de par.
    fora_a = con.execute("SELECT COUNT(*) FROM interacao_substancia "
                         "WHERE substancia_a_id >= substancia_b_id"
                         ).fetchone()[0]
    fora_b = con.execute("SELECT COUNT(*) FROM predicao "
                         "WHERE substancia_a_id >= substancia_b_id"
                         ).fetchone()[0]
    checa("D", "o NOT EXISTS da trava 4 é válido: par sempre canônico",
          fora_a == 0 and fora_b == 0, "%d + %d fora de ordem"
          % (fora_a, fora_b))

    # E se um par documentado estivesse invertido, a trava falharia. Prova
    # por construcao, num par inventado que existe so nesta transacao.
    par = con.execute(
        "SELECT p.substancia_a_id, p.substancia_b_id FROM predicao p LIMIT 1"
    ).fetchone()
    if par:
        invertido_pega = (par[1], par[0]) in documentados
        checa("D", "nenhum par documentado está guardado invertido",
              not invertido_pega or (par[0], par[1]) in documentados)

    # O texto do SQL da view: as quatro travas tem de estar TODAS la.
    sql = con.execute("SELECT sql FROM sqlite_master WHERE "
                      "name='vw_predicao_liberada'").fetchone()[0]
    for trava, marca in (("modelo ativo", "m.ativo = 1"),
                         ("homologado", "m.status = 'HOMOLOGADO'"),
                         ("limiar declarado", "m.limiar_alerta IS NOT NULL"),
                         ("limiar atingido", ">= m.limiar_alerta"),
                         ("sem documento", "NOT EXISTS"),
                         ("não recusada", "REVISADA_RECUSADA")):
        checa("D", "a view carrega a trava: %s" % trava, marca in sql)


# =====================================================================
# E — CALIBRACAO REIMPLEMENTADA SEM NUMPY
# =====================================================================
def interp(x, xs, ys):
    """np.interp reescrito em Python puro. Duas implementacoes do mesmo
    calculo; se discordarem, uma esta errada."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        meio = (lo + hi) // 2
        if xs[meio] <= x:
            lo = meio
        else:
            hi = meio
    if xs[hi] == xs[lo]:
        return ys[lo]
    t = (x - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] + t * (ys[hi] - ys[lo])


def caminho_e(con):
    print("\nE. CALIBRAÇÃO — np.interp reescrito, 600 previsões conferidas\n")
    calib = json.loads((RAIZ / "models" / "calibrador_m1.json")
                       .read_text(encoding="utf-8"))
    tabela = calib["tabela"]
    xs, ys = tabela["x"], tabela["y"]
    checa("E", "a tabela do calibrador é monótona não decrescente",
          all(ys[i] <= ys[i + 1] + 1e-12 for i in range(len(ys) - 1)),
          "%d ponto(s)" % len(xs))
    checa("E", "os pontos de x estão ordenados",
          all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1)))
    checa("E", "o calibrador é tabela legível, não binário",
          tabela.get("tipo") == "ISOTONICA_INTERPOLADA"
          and isinstance(xs, list), tabela.get("tipo"))

    linhas = list(con.execute(
        "SELECT id, probabilidade, probabilidade_calibrada FROM predicao"))
    piores, n_conf = 0.0, 0
    for pid, p, pc in linhas:
        if pc is None:
            continue
        n_conf += 1
        piores = max(piores, abs(interp(p, xs, ys) - pc))
    checa("E", "as %d probabilidades calibradas conferem por fora" % n_conf,
          n_conf > 0 and piores < 1e-9, "maior diferença %.3e" % piores)
    checa("E", "nenhuma probabilidade calibrada fora de [0, 1]",
          con.execute("SELECT COUNT(*) FROM predicao WHERE "
                      "probabilidade_calibrada NOT BETWEEN 0 AND 1"
                      ).fetchone()[0] == 0)
    checa("E", "a calibração melhorou o ECE, e os dois números estão gravados",
          float(calib["ece_depois"]) < float(calib["ece_antes"]),
          "%.4f → %.4f" % (float(calib["ece_antes"]),
                           float(calib["ece_depois"])))


# =====================================================================
# F — LEITURA DO CODIGO-FONTE
# =====================================================================
def caminho_f():
    print("\nF. CÓDIGO-FONTE — o que cada camada importa, e o que não\n")
    web = (RAIZ / "app" / "web.py").read_text(encoding="utf-8")
    motor = (RAIZ / "rules" / "motor_conciliacao.py").read_text(encoding="utf-8")
    horarios = (RAIZ / "rules" / "motor_horarios.py").read_text(encoding="utf-8")
    servicos = (RAIZ / "app" / "servicos.py").read_text(encoding="utf-8")

    sql_na_tela = [l.strip() for l in web.splitlines()
                   if re.search(r'"\s*(SELECT|INSERT|UPDATE|DELETE)\s',
                                l, re.I)]
    checa("F", "web.py não tem uma linha de SQL", not sql_na_tela,
          sql_na_tela[:1])

    for rotulo, fonte in (("motor de conciliação", motor),
                          ("motor de horários", horarios),
                          ("serviços", servicos), ("interface", web)):
        proibido = re.findall(
            r"^\s*(?:import|from)\s+(sklearn|joblib|pickle|numpy|scipy)",
            fonte, re.M)
        checa("F", "%s não carrega biblioteca de ML" % rotulo, not proibido,
              proibido)
        importa_ml = re.findall(r"^\s*(?:import|from)\s+ml[\s.]", fonte, re.M)
        checa("F", "%s não importa nada de ml/" % rotulo, not importa_ml,
              importa_ml)

    for nome in ("resultados.html", "achado.html", "relatorio.html"):
        t = (RAIZ / "app" / "templates" / nome).read_text(encoding="utf-8")
        calcula = re.findall(r"{%\s*(?:set|if)[^%]*"
                             r"(?:CRITICO|MAIOR)\s*(?:if|and|or)[^%]*%}", t)
        checa("F", "%s não calcula prioridade nem gravidade" % nome,
              not calcula, calcula[:1])

    # A tabela de prioridade e o unico lugar que decide prioridade.
    prioridade = (RAIZ / "rules" / "_prioridade.py").read_text(encoding="utf-8")
    checa("F", "previsão tem teto INFORMATIVO escrito na tabela",
          '"PREVISTA"' in prioridade and "INFORMATIVO" in prioridade)
    escreve_prio = re.findall(r'prioridade\s*=\s*"(CRITICO|ALTO|MODERADO)"',
                              motor)
    checa("F", "o motor não escreve prioridade à mão", not escreve_prio,
          escreve_prio[:2])


# =====================================================================
# G — ATENDIMENTO MONTADO POR SQL, SEM A INTERFACE
# =====================================================================
def caminho_g(con):
    print("\nG. SQL DIRETO — dois atendimentos montados sem a interface\n")
    sys.path.insert(0, str(RAIZ / "rules"))
    from motor_conciliacao import conciliar_atendimento

    ids = {}
    for nome, subs in (("V2-A", (2070, 1039)), ("V2-B", (1010, 1016))):
        pid = con.execute("INSERT INTO paciente (nome) VALUES (?)",
                          (nome,)).lastrowid
        aid = con.execute(
            "INSERT INTO atendimento (paciente_id, codigo) VALUES (?,?)",
            (pid, "V2-%s" % nome)).lastrowid
        for s in subs:
            con.execute(
                "INSERT INTO atendimento_medicamento (atendimento_id, "
                "substancia_id, nome_relatado, lista, origem, reconhecimento) "
                "VALUES (?,?,?,'EM_USO','PRESCRITO','NOME_EXATO')",
                (aid, s, "sub %d" % s))
        ids[nome] = (pid, aid, set(subs))
    con.commit()

    resultados = {}
    for nome, (_pid, aid, subs) in ids.items():
        r = conciliar_atendimento(con, aid, persistir=False)
        resultados[nome] = r
        citadas = {x for a in r.achados
                   for x in (a.substancia_a_id, a.substancia_b_id) if x}
        checa("G", "[%s] só cita as substâncias que recebeu" % nome,
              citadas <= subs, sorted(citadas - subs))
        checa("G", "[%s] o resumo conta o que recebeu" % nome,
              r.resumo["medicamentos"] == len(subs),
              "%d de %d" % (r.resumo["medicamentos"], len(subs)))

    checa("G", "os dois atendimentos não têm nenhum achado em comum",
          not ({a.grupo_chave for a in resultados["V2-A"].achados}
               & {a.grupo_chave for a in resultados["V2-B"].achados}))
    checa("G", "montado por SQL, o motor produz o mesmo tipo de achado",
          any(a.tipo == "FARMACO_FARMACO"
              for a in resultados["V2-A"].achados),
          "%d achado(s) em A" % len(resultados["V2-A"].achados))

    # Apagar o atendimento leva tudo junto e nao quebra referencia.
    for nome, (pid, aid, _s) in ids.items():
        con.execute("DELETE FROM atendimento WHERE id=?", (aid,))
        con.execute("DELETE FROM paciente WHERE id=?", (pid,))
    con.commit()
    sobra = sum(con.execute(
        "SELECT COUNT(*) FROM %s WHERE atendimento_id IN (?,?)" % t,
        (ids["V2-A"][1], ids["V2-B"][1])).fetchone()[0]
        for t in ("atendimento_medicamento", "conciliacao",
                  "anotacao_profissional", "rotina_paciente"))
    checa("G", "apagar o atendimento não deixa resto", sobra == 0,
          "%d" % sobra)
    checa("G", "nem quebra chave estrangeira",
          not con.execute("PRAGMA foreign_key_check").fetchall())


# =====================================================================
# H — CACADA: PREVISAO APRESENTADA COMO FATO
# =====================================================================
def caminho_h(cliente, con, codigos):
    print("\nH. CAÇADA — previsão apresentada como fato\n")
    for rotulo, codigo in codigos.items():
        html = cliente.get("/a/%s/resultados" % codigo).data.decode("utf-8")
        det_txt = cliente.get("/a/%s/relatorio.txt"
                              % codigo).data.decode("utf-8")
        for nome, texto in (("tela", html), ("relatório", det_txt)):
            baixo = texto.lower()
            # Uma previsao nunca pode ser descrita com verbo de fato.
            suspeitas = [f for f in (
                "interação documentada pelo modelo", "o modelo comprova",
                "há interação entre", "existe interação documentada entre",
                "evidência: modelo", "fonte: modelo") if f in baixo]
            checa("H", "[%s/%s] nenhuma frase apresenta previsão como fato"
                  % (rotulo[:12], nome), not suspeitas, suspeitas)

    # No banco: nenhum achado PREVISTO com atributo de fato.
    erros = con.execute(
        "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' AND "
        "(nivel_evidencia IS NOT NULL AND nivel_evidencia <> 'NAO_AVALIADA' "
        " OR gravidade_fonte IS NOT NULL OR fonte IS NOT NULL "
        " OR documento IS NOT NULL)").fetchone()[0]
    checa("H", "nenhum achado previsto carrega gravidade, fonte ou documento",
          erros == 0, "%d" % erros)
    misturado = con.execute(
        "SELECT COUNT(*) FROM achado a JOIN achado b "
        "ON a.grupo_chave = b.grupo_chave AND a.id <> b.id "
        "WHERE a.natureza='PREVISTO' AND b.natureza='DOCUMENTADO'"
    ).fetchone()[0]
    checa("H", "previsto e documentado nunca partilham grupo_chave",
          misturado == 0, "%d" % misturado)
    duplicado = con.execute(
        "SELECT COUNT(*) FROM (SELECT conciliacao_id, grupo_chave, COUNT(*) n "
        "FROM achado WHERE status <> 'AGRUPADO' GROUP BY 1,2 HAVING n>1)"
    ).fetchone()[0]
    checa("H", "nenhum alerta duplicado na mesma conciliação", duplicado == 0,
          "%d" % duplicado)
    sem_rastro = con.execute(
        "SELECT COUNT(*) FROM achado WHERE origem_achado='MODELO' AND "
        "(metodo_deteccao NOT LIKE 'MODELO_%' OR origem_afirmacao "
        "NOT LIKE 'predicao.%')").fetchone()[0]
    checa("H", "toda previsão nomeia modelo e versão no método de detecção",
          sem_rastro == 0, "%d" % sem_rastro)


# =====================================================================
def main() -> int:
    print("=" * 78)
    print("FASE 9 — V2: AUDITORIA INDEPENDENTE DO SISTEMA INTEIRO")
    print("=" * 78)
    tmp = Path(tempfile.mkdtemp())
    copia = tmp / "conciliador.db"
    shutil.copy(BANCO, copia)

    for _p in ("app", "rules", "pipeline"):
        sys.path.insert(0, str(RAIZ / _p))
    import servicos as sv
    sv.BANCO = copia
    import web
    from werkzeug.datastructures import MultiDict
    web.app.config["TESTING"] = True
    cliente = web.app.test_client()

    con = sqlite3.connect(copia)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        linha = con.execute(
            "SELECT m.id, COUNT(p.id) FROM modelo m LEFT JOIN predicao p "
            "ON p.modelo_id = m.id GROUP BY m.id ORDER BY 2 DESC LIMIT 1"
        ).fetchone()
        modelo_id = linha[0]
        con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1, "
                    "limiar_alerta=0.90 WHERE id=?", (modelo_id,))
        con.commit()

        # Um atendimento com os quatro estados na mesma tela.
        r = cliente.post("/novo", data={"nome": "V2 — quatro estados",
                                        "farmaceutico": "Farm. V2",
                                        "crf": "CRF-V2 1"})
        cod = r.headers["Location"].split("/a/")[1].split("/")[0]
        cliente.post("/a/%s/paciente" % cod,
                     data={"nome": "V2 — quatro estados",
                           "data_nascimento": "1952-07-01", "sexo": "M"})
        for rotulo, sid in (("Varfarina 5 mg", 2070),
                            ("Ibuprofeno 600 mg", 1039),
                            ("Haloperidol 1 mg", 301),
                            ("Levomepromazina 25 mg", 1427),
                            ("Gliclazida 30 mg", 1010),
                            ("Glimepirida 2 mg", 1016),
                            ("um chá sem rótulo", None)):
            rr = cliente.post("/a/%s/medicamento" % cod,
                              data={"nome_relatado": rotulo,
                                    "escolha": ("substancia:%d" % sid)
                                    if sid else "", "lista": "EM_USO",
                                    "origem": "PRESCRITO"})
            if rr.status_code == 302 and sid:
                g = rr.headers["Location"].rstrip("/").split("/")[-1]
                cliente.post("/a/%s/posologia/%s" % (cod, g),
                             data=MultiDict([("dose_valor", "1"),
                                             ("dose_unidade", "mg"),
                                             ("vezes_por_dia", "1"),
                                             ("via_administracao", "oral"),
                                             ("horario", "08:00")]))
        cliente.post("/a/%s/analisar" % cod)
        print("atendimento de trabalho: %s" % cod)

        caminho_a(con, sv, cod)
        caminho_b(cliente, con, cod)
        caminho_c(con)
        caminho_d(con)
        caminho_e(con)
        caminho_f()
        caminho_g(con)
        caminho_h(cliente, con, {"quatro estados": cod})
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 78)
    print("%d verificação(ões) · %d ok · %d falha(s)"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS)))
    for caminho, nome, det in FALHAS:
        print("  FALHA [%s] %s — %s" % (caminho, nome, det))
    if not FALHAS:
        print("\nV2 OK — oito caminhos independentes, nenhum defeito de "
              "integração encontrado.")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
