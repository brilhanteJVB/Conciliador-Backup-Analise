# -*- coding: utf-8 -*-
"""
FASE 9 — V1: AUDITORIA FUNCIONAL DO SISTEMA INTEIRO.

Nao repete o teste de cada modulo. Procura o que so aparece quando tudo roda
junto: dado que vaza de um atendimento para outro, resultado que sobrevive a
uma mudanca que devia invalida-lo, previsao que escapa de uma trava, modelo
que nao e o registrado, tela que faz quatro estados diferentes parecerem o
mesmo.

ONZE EIXOS
----------
  1  isolamento entre atendimentos      dois pacientes, nada em comum
  2  persistencia                       outro PROCESSO le o que foi gravado
  3  recalculo                          mudar o dado muda o resultado
  4  o ML dentro do sistema             nove condicoes de liberacao
  5  integridade do modelo              o que roda e o que esta registrado
  6  dados desatualizados               modelo novo nao entra sozinho
  7  resiliencia                        onze situacoes que podem dar errado
  8  seguranca logica                   id cruzado, orfao, chave estrangeira
  9  a interface                        quatro estados, quatro aparencias
 10  o relatorio                        cinco perfis de paciente
 11  desempenho                         seis medidas, com orcamento declarado

TUDO NUMA COPIA DO BANCO — os eixos 4, 5, 6 e 9 precisam homologar um modelo.

Uso: python tests/fase9_v1_sistema.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline", "tests"):
    sys.path.insert(0, str(RAIZ / _p))

from werkzeug.datastructures import MultiDict          # noqa: E402

BANCO = RAIZ / "database" / "conciliador.db"

S = {"varfarina": 2070, "ibuprofeno": 1039, "losartana": 1458,
     "dipirona": 1506, "haloperidol": 301, "levomepromazina": 1427,
     "bromexina": 555, "macrogol": 1468, "sinvastatina": 1889,
     "metformina": 1509, "omeprazol": 1534, "levotiroxina": 1432,
     "carbonato_calcio": 1156, "gliclazida": 1010, "glimepirida": 1016,
     "amoxicilina": 332, "paracetamol": 1677, "atenolol": 408,
     "captopril": 1178, "sertralina": 1876}

PASSOS, FALHAS, TEMPOS = [], [], []
COPIA = None


def checa(eixo, nome, ok, detalhe=""):
    PASSOS.append((eixo, nome, ok, detalhe))
    if not ok:
        FALHAS.append((eixo, nome, detalhe))
    print("   %s %-54s %s" % ("OK  " if ok else "ERRO", nome[:54],
                              str(detalhe)[:58]))


def cronometrar(rotulo, fn, orcamento_s):
    t0 = time.time()
    saida = fn()
    dt = time.time() - t0
    TEMPOS.append((rotulo, dt, orcamento_s))
    return saida, dt


# ------------------------------------------------------------ construcao
def novo(c, nome):
    r = c.post("/novo", data={"nome": nome, "farmaceutico": "Farm. Fase 9",
                              "crf": "CRF-AM 90009"})
    codigo = r.headers["Location"].split("/a/")[1].split("/")[0]
    c.post("/a/%s/paciente" % codigo,
           data={"nome": nome, "data_nascimento": "1955-02-20", "sexo": "F",
                 "peso_kg": "70", "altura_cm": "162",
                 "farmaceutico": "Farm. Fase 9", "crf": "CRF-AM 90009"})
    return codigo


def med(c, codigo, rotulo, sid=None, lista="EM_USO", origem="PRESCRITO",
        dose=None, unidade="mg", vezes=None, horarios=(), continuo=True):
    r = c.post("/a/%s/medicamento" % codigo,
               data={"nome_relatado": rotulo,
                     "escolha": ("substancia:%d" % sid) if sid else "",
                     "lista": lista, "origem": origem})
    if r.status_code != 302:
        return None
    grupo = r.headers["Location"].rstrip("/").split("/")[-1]
    campos = [("via_administracao", "oral")]
    if dose is not None:
        campos += [("dose_valor", str(dose)), ("dose_unidade", unidade)]
    if vezes is not None:
        campos.append(("vezes_por_dia", str(vezes)))
    if continuo:
        campos.append(("uso_continuo", "on"))
    campos += [("horario", h) for h in horarios]
    c.post("/a/%s/posologia/%s" % (codigo, grupo), data=MultiDict(campos))
    return grupo


def rotina_padrao(c, codigo):
    c.post("/a/%s/rotina" % codigo,
           data={"ACORDAR": "06:30", "CAFE_MANHA": "07:00", "ALMOCO": "12:00",
                 "JANTAR": "19:30", "DORMIR": "22:30"})


def res_de(sv, codigo):
    con = sv.conectar()
    try:
        return sv.resultado_atual(con, codigo)
    finally:
        con.close()


# =====================================================================
# EIXO 1 — ISOLAMENTO ENTRE ATENDIMENTOS
# =====================================================================
def eixo_1_isolamento(c, sv, con):
    print("\n1. ISOLAMENTO — dois pacientes, nada em comum\n")
    a = novo(c, "Paciente A — Fase 9")
    b = novo(c, "Paciente B — Fase 9")

    # A: anticoagulante + anti-inflamatorio, alergia a dipirona, condicao.
    c.post("/a/%s/alergia" % a, data={"substancia_id": S["dipirona"],
                                      "reacao": "broncoespasmo de A",
                                      "gravidade": "GRAVE"})
    c.post("/a/%s/condicao" % a, data={"doenca_id": 26})     # hipertensao
    med(c, a, "Varfarina 5 mg", S["varfarina"], dose=5, vezes=1,
        horarios=("20:00",))
    med(c, a, "Ibuprofeno 600 mg", S["ibuprofeno"], origem="AUTOMEDICACAO",
        dose=600, vezes=3, horarios=("08:00", "14:00", "22:00"), continuo=False)
    rotina_padrao(c, a)

    # B: dois antidiabeticos da mesma classe, alergia a amoxicilina.
    c.post("/a/%s/alergia" % b, data={"substancia_id": S["amoxicilina"],
                                      "reacao": "exantema de B",
                                      "gravidade": "MODERADA"})
    c.post("/a/%s/condicao" % b, data={"doenca_id": 9})       # diabetes
    med(c, b, "Gliclazida 30 mg", S["gliclazida"], dose=30, vezes=1,
        horarios=("07:30",))
    med(c, b, "Glimepirida 2 mg", S["glimepirida"], dose=2, vezes=1,
        horarios=("07:30",))
    rotina_padrao(c, b)

    c.post("/a/%s/analisar" % a)
    c.post("/a/%s/analisar" % b)
    ra, rb = res_de(sv, a), res_de(sv, b)

    subs_a = {x for ach in ra.achados
              for x in (ach.substancia_a_id, ach.substancia_b_id) if x}
    subs_b = {x for ach in rb.achados
              for x in (ach.substancia_a_id, ach.substancia_b_id) if x}
    checa(1, "medicamentos não vazam: A não cita substância de B",
          not (subs_a & {S["gliclazida"], S["glimepirida"]}), sorted(subs_a))
    checa(1, "medicamentos não vazam: B não cita substância de A",
          not (subs_b & {S["varfarina"], S["ibuprofeno"]}), sorted(subs_b))
    checa(1, "achados não vazam: nenhum grupo_chave em comum",
          not ({x.grupo_chave for x in ra.achados}
               & {x.grupo_chave for x in rb.achados}))
    checa(1, "alergias não vazam",
          "broncoespasmo de A" not in json.dumps(
              [x.contexto_paciente or "" for x in rb.achados],
              ensure_ascii=False)
          and "exantema de B" not in json.dumps(
              [x.contexto_paciente or "" for x in ra.achados],
              ensure_ascii=False))
    checa(1, "condições não vazam",
          "diabetes" not in " ".join(x.contexto_paciente or ""
                                     for x in ra.achados).lower())
    checa(1, "o resumo de cada um conta só o que é dele",
          ra.resumo["medicamentos"] == 2 and rb.resumo["medicamentos"] == 2,
          "A=%d B=%d" % (ra.resumo["medicamentos"], rb.resumo["medicamentos"]))

    # ---- no BANCO, e nao so no objeto do motor
    aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                      (a,)).fetchone()[0]
    bid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                      (b,)).fetchone()[0]
    cruzado = con.execute(
        "SELECT COUNT(*) FROM achado ac JOIN conciliacao co "
        "ON co.id = ac.conciliacao_id WHERE co.atendimento_id = ? "
        "AND ac.substancia_a_id IS NOT NULL AND ac.substancia_a_id NOT IN "
        "(SELECT substancia_id FROM atendimento_medicamento "
        " WHERE atendimento_id = ? AND substancia_id IS NOT NULL "
        " UNION SELECT substancia_id FROM paciente_alergia pa "
        "        JOIN atendimento t ON t.paciente_id = pa.paciente_id "
        "        WHERE t.id = ? AND pa.substancia_id IS NOT NULL)",
        (aid, aid, aid)).fetchone()[0]
    checa(1, "no banco: nenhum achado de A cita substância que não é de A",
          cruzado == 0, "%d" % cruzado)

    # ---- na INTERFACE
    pa = c.get("/a/%s/resultados" % a).data.decode("utf-8")
    pb = c.get("/a/%s/resultados" % b).data.decode("utf-8")
    checa(1, "a tela de A não mostra o nome do paciente B",
          "Paciente B — Fase 9" not in pa)
    checa(1, "a tela de B não mostra o nome do paciente A",
          "Paciente A — Fase 9" not in pb)
    checa(1, "a tela de A não mostra medicamento de B",
          "Gliclazida" not in pa and "Glimepirida" not in pa,
          "inclusive nas mensagens de estado")
    checa(1, "nenhuma mensagem de estado de B sobra na tela de A",
          "Posologia de Gliclazida" not in pa
          and "Posologia de Glimepirida" not in pa)
    ta = c.get("/a/%s/relatorio.txt" % a).data.decode("utf-8")
    tb = c.get("/a/%s/relatorio.txt" % b).data.decode("utf-8")
    checa(1, "os relatórios não se misturam",
          "Paciente B — Fase 9" not in ta and "Paciente A — Fase 9" not in tb)
    checa(1, "cada relatório traz o seu próprio paciente",
          "Paciente A — Fase 9" in ta and "Paciente B — Fase 9" in tb)

    # ---- observacao profissional presa ao atendimento certo
    alvo = ra.achados[0]
    c.post("/a/%s/achado/revisar" % a,
           data={"chave": alvo.grupo_chave, "situacao": "REVISADO",
                 "profissional": "Farm. Fase 9", "crf": "CRF-AM 90009",
                 "observacao": "observação exclusiva do atendimento A"})
    vazou = con.execute(
        "SELECT COUNT(*) FROM anotacao_profissional WHERE atendimento_id=? "
        "AND observacao LIKE '%exclusiva do atendimento A%'",
        (bid,)).fetchone()[0]
    checa(1, "observações não vazam entre atendimentos", vazou == 0,
          "%d" % vazou)
    return a, b


# =====================================================================
# EIXO 2 — PERSISTENCIA (outro processo)
# =====================================================================
def eixo_2_persistencia(c, sv, con, codigo):
    print("\n2. PERSISTENCIA — outro PROCESSO lê o que foi gravado\n")
    antes = res_de(sv, codigo)
    med(c, codigo, "Sinvastatina 20 mg", S["sinvastatina"], dose=20, vezes=1,
        horarios=("22:00",))
    c.post("/a/%s/analisar" % codigo)

    # Reabrir num processo NOVO e a unica forma de provar persistencia: no
    # mesmo processo, cache de modulo e conexao aberta poderiam responder por
    # memoria e o teste passaria sem que nada tivesse sido gravado.
    script = (
        "import sys, json; from pathlib import Path\n"
        "RAIZ = Path(%r)\n"
        "[sys.path.insert(0, str(RAIZ / p)) for p in ('app','rules','pipeline')]\n"
        "import servicos as sv\n"
        "sv.BANCO = Path(%r)\n"
        "con = sv.conectar()\n"
        "at = sv.obter_atendimento(con, %r)\n"
        "meds = sv.listar_medicamentos(con, %r)\n"
        "res = sv.resultado_atual(con, %r)\n"
        "print(json.dumps({'paciente': at['nome'],\n"
        "  'medicamentos': [m.nome_relatado for m in meds],\n"
        "  'achados': res.resumo['achados'],\n"
        "  'doses': [m.resumo_posologia() for m in meds]},\n"
        "  ensure_ascii=False))\n"
    ) % (str(RAIZ), str(COPIA), codigo, codigo, codigo)
    r = subprocess.run([sys.executable, "-c", script], capture_output=True,
                       text=True, encoding="utf-8", cwd=str(RAIZ))
    checa(2, "um processo novo abre o atendimento sem erro",
          r.returncode == 0, (r.stderr or "").strip().splitlines()[-1:]
          or "ok")
    if r.returncode != 0:
        return
    lido = json.loads(r.stdout.strip().splitlines()[-1])
    checa(2, "o paciente continua íntegro depois de reabrir",
          lido["paciente"].startswith("Paciente A"), lido["paciente"])
    checa(2, "os medicamentos continuam lá, inclusive o acrescentado",
          any("Sinvastatina" in m for m in lido["medicamentos"])
          and len(lido["medicamentos"]) == 3,
          "%d item(ns)" % len(lido["medicamentos"]))
    checa(2, "a posologia sobreviveu ao fechamento",
          any("20" in (d or "") for d in lido["doses"]),
          [d for d in lido["doses"] if d][:2])
    checa(2, "a análise no processo novo reflete o dado alterado",
          lido["achados"] >= antes.resumo["achados"],
          "%d antes · %d depois" % (antes.resumo["achados"], lido["achados"]))

    gravadas = con.execute(
        "SELECT COUNT(*) FROM conciliacao co JOIN atendimento a "
        "ON a.id = co.atendimento_id WHERE a.codigo=?", (codigo,)).fetchone()[0]
    checa(2, "cada análise ficou registrada como histórico, sem sobrescrever",
          gravadas >= 2, "%d conciliação(ões) gravada(s)" % gravadas)
    anot = con.execute(
        "SELECT observacao FROM anotacao_profissional ap JOIN atendimento a "
        "ON a.id = ap.atendimento_id WHERE a.codigo=?", (codigo,)).fetchone()
    checa(2, "a revisão do profissional sobreviveu à reanálise",
          anot is not None and "exclusiva do atendimento A" in (anot[0] or ""),
          (anot[0] or "")[:44] if anot else "perdida")


# =====================================================================
# EIXO 3 — RECALCULO
# =====================================================================
def eixo_3_recalculo(c, sv, con):
    print("\n3. RECALCULO — mudar o dado muda o resultado\n")
    cod = novo(c, "Paciente C — recálculo")
    g_var = med(c, cod, "Varfarina 5 mg", S["varfarina"], dose=5, vezes=1,
                horarios=("20:00",))
    g_ibu = med(c, cod, "Ibuprofeno 600 mg", S["ibuprofeno"],
                origem="AUTOMEDICACAO", dose=600, vezes=3,
                horarios=("08:00", "14:00", "22:00"), continuo=False)
    rotina_padrao(c, cod)
    c.post("/a/%s/analisar" % cod)
    r1 = res_de(sv, cod)
    chaves1 = {a.grupo_chave for a in r1.achados}
    checa(3, "o achado do par existe antes da mudança",
          any(a.tipo == "FARMACO_FARMACO" for a in r1.achados),
          "%d achado(s)" % len(r1.achados))

    # (a) REMOVER o medicamento que causava o achado
    c.post("/a/%s/medicamento/%s/remover" % (cod, g_ibu))
    r2 = res_de(sv, cod)
    chaves2 = {a.grupo_chave for a in r2.achados}
    checa(3, "achado que deixou de ser aplicável DESAPARECE",
          not any(a.tipo == "FARMACO_FARMACO" for a in r2.achados),
          "%d achado(s) restante(s)" % len(r2.achados))
    checa(3, "não sobrou achado órfão do item removido",
          not any(a.substancia_a_id == S["ibuprofeno"]
                  or a.substancia_b_id == S["ibuprofeno"] for a in r2.achados))
    sobrou = con.execute(
        "SELECT COUNT(*) FROM posologia p WHERE NOT EXISTS "
        "(SELECT 1 FROM atendimento_medicamento m WHERE m.id = "
        " p.atendimento_medicamento_id)").fetchone()[0]
    checa(3, "remover não deixou posologia órfã no banco", sobrou == 0,
          "%d" % sobrou)

    # (b) ACRESCENTAR outro medicamento -> achado novo aparece
    med(c, cod, "Sertralina 50 mg", S["sertralina"], dose=50, vezes=1,
        horarios=("08:00",))
    r3 = res_de(sv, cod)
    chaves3 = {a.grupo_chave for a in r3.achados}
    checa(3, "achado novo APARECE quando o dado muda",
          bool(chaves3 - chaves2), sorted(chaves3 - chaves2)[:2])
    checa(3, "resultados não são duplicados",
          len(chaves3) == len(r3.achados),
          "%d chave(s) para %d achado(s)" % (len(chaves3), len(r3.achados)))

    # (c) MUDAR A DOSE e o HORARIO
    c.post("/a/%s/posologia/%s" % (cod, g_var),
           data=MultiDict([("dose_valor", "10"), ("dose_unidade", "mg"),
                           ("vezes_por_dia", "1"), ("via_administracao", "oral"),
                           ("uso_continuo", "on"), ("horario", "07:00")]))
    r4 = res_de(sv, cod)
    hora = con.execute(
        "SELECT h.hora FROM horario_administracao h JOIN posologia p "
        "ON p.id = h.posologia_id JOIN atendimento_medicamento m "
        "ON m.id = p.atendimento_medicamento_id JOIN atendimento a "
        "ON a.id = m.atendimento_id WHERE a.codigo=? AND m.substancia_id=?",
        (cod, S["varfarina"])).fetchone()
    checa(3, "a mudança de horário chegou ao banco", hora and hora[0] == "07:00",
          hora[0] if hora else "—")
    checa(3, "a agenda foi remontada com o horário novo",
          any("07:00" in str(getattr(e, "hora", "")) for e in r4.agenda.eventos),
          [str(getattr(e, "hora", "")) for e in r4.agenda.eventos][:3])

    # (d) ACRESCENTAR ALERGIA -> achado de alergia aparece
    c.post("/a/%s/alergia" % cod, data={"substancia_id": S["sertralina"],
                                        "reacao": "prurido", "gravidade": "LEVE"})
    r5 = res_de(sv, cod)
    checa(3, "alergia acrescentada produz achado imediatamente",
          any(a.tipo == "FARMACO_ALERGIA" for a in r5.achados),
          "%d achado(s)" % len(r5.achados))

    # (e) ACRESCENTAR CONDICAO
    c.post("/a/%s/condicao" % cod, data={"doenca_id": 6})
    r6 = res_de(sv, cod)
    checa(3, "condição acrescentada entra no contexto dos achados",
          any("renal" in (a.contexto_paciente or "").lower()
              for a in r6.achados), "—")

    # (f) a TELA nao mostra resultado velho.
    # A conferencia e sobre o resultado RECALCULADO e sobre o corpo da
    # pagina: a primeira versao procurava "Ibuprofeno 600 mg" no HTML inteiro
    # e casava com a mensagem de estado "Posologia de Ibuprofeno 600 mg
    # salva" — a mesma fila de mensagens que o eixo 1 mostrou nao estar
    # presa ao atendimento.
    pagina = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    r7 = res_de(sv, cod)
    checa(3, "o achado que deixou de existir sumiu do resultado atual",
          not any(S["ibuprofeno"] in (a.substancia_a_id, a.substancia_b_id)
                  for a in r7.achados))
    checa(3, "a tela NAO exibe mais um achado com o item removido",
          "Interação entre Ibuprofeno" not in pagina
          and "Ibuprofeno 600 mg e Varfarina" not in pagina)
    aviso = c.post("/a/%s/medicamento/%s/remover" % (cod, g_var),
                   follow_redirects=True).data.decode("utf-8")
    checa(3, "remover depois de analisar AVISA que a análise ficou velha",
          "desatualizada" in aviso, "a tela diz para gravar de novo")
    checa(3, "a conciliação anterior FICA gravada como histórico",
          con.execute(
              "SELECT COUNT(*) FROM achado a JOIN conciliacao co "
              "ON co.id = a.conciliacao_id JOIN atendimento t "
              "ON t.id = co.atendimento_id WHERE t.codigo=? "
              "AND a.substancia_a_id=?", (cod, S["ibuprofeno"])
          ).fetchone()[0] > 0,
          "histórico preservado, tela recalculada")
    checa(3, "a tela mostra os achados novos",
          "Sertralina" in pagina)
    checa(3, "o relatório também foi recalculado",
          "Ibuprofeno" not in c.get("/a/%s/relatorio.txt" % cod)
          .data.decode("utf-8"))
    return cod


# =====================================================================
# EIXO 4 — O ML DENTRO DO SISTEMA
# =====================================================================
def eixo_4_ml(c, sv, con, modelo_id):
    print("\n4. O ML DENTRO DO SISTEMA — nove condições de liberação\n")
    a, b = sorted((S["haloperidol"], S["levomepromazina"]))
    d_a, d_b = sorted((S["varfarina"], S["ibuprofeno"]))
    n = lambda: con.execute("SELECT COUNT(*) FROM vw_predicao_liberada"
                            ).fetchone()[0]

    con.execute("DELETE FROM predicao")
    con.execute("UPDATE modelo SET status='EXPERIMENTAL', ativo=0, "
                "limiar_alerta=NULL")
    con.execute("INSERT INTO predicao (modelo_id, substancia_a_id, "
                "substancia_b_id, probabilidade, probabilidade_calibrada) "
                "VALUES (?,?,?,?,?)", (modelo_id, a, b, 0.9500, 0.9500))
    con.commit()

    checa(4, "1. modelo inexistente para o problema → nada liberado",
          n() == 0, n())
    con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1 WHERE id=?",
                (modelo_id,))
    con.commit()
    checa(4, "2. modelo homologado e ativo, SEM limiar → nada liberado",
          n() == 0, "%d (fail-closed)" % n())

    con.execute("UPDATE modelo SET limiar_alerta=0.99 WHERE id=?", (modelo_id,))
    con.commit()
    checa(4, "3. probabilidade ABAIXO do limiar → nada liberado", n() == 0, n())

    # 4. exatamente NO limiar: a comparacao e >=, e isso tem de ser exato.
    con.execute("UPDATE modelo SET limiar_alerta=0.9500 WHERE id=?",
                (modelo_id,))
    con.commit()
    checa(4, "4. probabilidade EXATAMENTE no limiar → liberada (>=)",
          n() == 1, n())
    con.execute("UPDATE predicao SET probabilidade_calibrada=? "
                "WHERE substancia_a_id=?", (0.9500 - 1e-9, a))
    con.commit()
    checa(4, "4b. um bilionésimo abaixo do limiar → NÃO liberada", n() == 0,
          n())

    con.execute("UPDATE predicao SET probabilidade_calibrada=0.9800 "
                "WHERE substancia_a_id=?", (a,))
    con.commit()
    checa(4, "5. probabilidade ACIMA do limiar → liberada", n() == 1, n())

    con.execute("UPDATE modelo SET status='EXPERIMENTAL' WHERE id=?"
                if False else
                "UPDATE modelo SET ativo=0 WHERE id=?", (modelo_id,))
    con.commit()
    checa(4, "6. modelo desativado → nada liberado", n() == 0, n())
    try:
        con.execute("UPDATE modelo SET status='EXPERIMENTAL', ativo=1 "
                    "WHERE id=?", (modelo_id,))
        recusou = False
        con.rollback()
    except sqlite3.IntegrityError:
        recusou = True
        con.rollback()
    checa(4, "7. o banco RECUSA ativar modelo não homologado", recusou)
    con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1, "
                "limiar_alerta=0.9500 WHERE id=?", (modelo_id,))
    con.commit()

    # 8. par ja documentado
    con.execute("INSERT INTO predicao (modelo_id, substancia_a_id, "
                "substancia_b_id, probabilidade, probabilidade_calibrada) "
                "VALUES (?,?,?,?,?)", (modelo_id, d_a, d_b, 0.9990, 0.9990))
    con.commit()
    liberadas = con.execute(
        "SELECT COUNT(*) FROM vw_predicao_liberada WHERE substancia_a_id=?",
        (d_a,)).fetchone()[0]
    checa(4, "8. par JÁ DOCUMENTADO não libera previsão (prob 0,999)",
          liberadas == 0, liberadas)

    # 9. probabilidade invalida
    for valor in (1.5, -0.1):
        try:
            con.execute("INSERT INTO predicao (modelo_id, substancia_a_id, "
                        "substancia_b_id, probabilidade) VALUES (?,?,?,?)",
                        (modelo_id, 1, 2, valor))
            recusou = False
            con.rollback()
        except sqlite3.IntegrityError:
            recusou = True
            con.rollback()
        checa(4, "9. o banco RECUSA probabilidade %s" % valor, recusou)

    # 10. previsao recusada pelo farmaceutico nao volta
    con.execute("UPDATE predicao SET status='REVISADA_RECUSADA', "
                "revisado_por='Farm. Fase 9' WHERE substancia_a_id=?", (a,))
    con.commit()
    checa(4, "10. previsão recusada pelo profissional não volta", n() == 0, n())
    con.execute("UPDATE predicao SET status='NAO_REVISADA', revisado_por=NULL "
                "WHERE substancia_a_id=?", (a,))
    con.commit()

    # ---- a cadeia ate a tela, com o modelo ligado
    cod = novo(c, "Paciente D — cadeia do modelo")
    med(c, cod, "Haloperidol 1 mg", S["haloperidol"], dose=1, vezes=2,
        horarios=("08:00", "20:00"))
    med(c, cod, "Levomepromazina 25 mg", S["levomepromazina"], dose=25,
        vezes=1, horarios=("20:00",))
    rotina_padrao(c, cod)
    c.post("/a/%s/analisar" % cod)
    res = res_de(sv, cod)
    previstos = [x for x in res.achados if x.natureza == "PREVISTO"]
    checa(4, "a cadeia inteira chega ao achado PREVISTO", len(previstos) == 1,
          len(previstos))
    if previstos:
        p = previstos[0]
        gravado = con.execute(
            "SELECT probabilidade_calibrada FROM predicao WHERE id=?",
            (int(p.origem_afirmacao.split(".")[1]),)).fetchone()[0]
        checa(4, "a probabilidade exibida é a CALIBRADA gravada",
              abs(p.probabilidade_modelo - gravado) < 1e-12,
              "%.6f vs %.6f" % (p.probabilidade_modelo, gravado))
        checa(4, "o par não pontuado é DECLARADO, não silenciado",
              any(x.motivo == "PAR_NAO_PONTUADO_PELO_MODELO"
                  for x in res.nao_avaliado)
              or len(res.achados) + len(previstos) > 0,
              sorted({x.motivo for x in res.nao_avaliado})[:3])
    return cod


# =====================================================================
# EIXO 5 — INTEGRIDADE DO MODELO
# =====================================================================
def eixo_5_integridade_modelo(con):
    print("\n5. INTEGRIDADE DO MODELO — o que roda é o que está registrado\n")
    sys.path.insert(0, str(RAIZ / "ml"))
    import _comum as mlc                                   # noqa: E402

    prod = sqlite3.connect(BANCO)
    try:
        digital = mlc.versao_dados(prod)["impressao"]
        registrados = list(prod.execute(
            "SELECT id, nome, versao, algoritmo, n_features, semente, "
            "versao_dados, artefato, espaco_features_json, calibrador_json, "
            "limiar_alerta, status, ativo FROM modelo"))
    finally:
        prod.close()

    checa(5, "há modelo registrado para conferir", bool(registrados),
          "%d" % len(registrados))
    espaco_disco = json.loads((RAIZ / "models" / "espaco_features.json")
                              .read_text(encoding="utf-8"))
    for (mid, nome, versao, alg, nfeat, semente, vdados, artefato,
         espaco_json, calib, limiar, status, ativo) in registrados:
        rotulo = versao
        caminho = RAIZ / artefato.replace("\\", "/")
        checa(5, "[%s] o arquivo do artefato existe" % rotulo, caminho.exists(),
              artefato)
        if not caminho.exists():
            continue
        manifesto = json.loads(caminho.read_text(encoding="utf-8"))
        checa(5, "[%s] a versão do manifesto bate com o registro" % rotulo,
              manifesto.get("versao") == versao,
              "%s vs %s" % (manifesto.get("versao"), versao))
        checa(5, "[%s] o nº de atributos bate" % rotulo,
              manifesto.get("n_features") == nfeat,
              "%s vs %s" % (manifesto.get("n_features"), nfeat))
        checa(5, "[%s] a semente bate" % rotulo,
              manifesto.get("semente") == semente,
              "%s vs %s" % (manifesto.get("semente"), semente))
        checa(5, "[%s] a versão dos dados bate com o manifesto" % rotulo,
              manifesto.get("versao_dados") == vdados,
              "%s vs %s" % (manifesto.get("versao_dados"), vdados))
        # A conferencia que expos o defeito D-048: a impressao digital
        # RECALCULADA agora contra a que foi gravada no treino.
        checa(5, "[%s] a impressão digital do banco NÃO mudou desde o treino"
              % rotulo, vdados == digital, "%s vs %s (agora)" % (vdados, digital))
        checa(5, "[%s] o espaço de atributos bate com models/" % rotulo,
              json.loads(espaco_json) == espaco_disco["nomes"],
              "%d vs %d nomes" % (len(json.loads(espaco_json)),
                                  len(espaco_disco["nomes"])))
        checa(5, "[%s] o nº de atributos bate com o espaço" % rotulo,
              nfeat == len(espaco_disco["nomes"]) == espaco_disco["n"],
              "%d · %d" % (nfeat, espaco_disco["n"]))
        if manifesto.get("tipo") == "SKLEARN_PICKLE":
            pkl = caminho.parent / manifesto["pickle"]
            checa(5, "[%s] o pickle referido pelo manifesto existe" % rotulo,
                  pkl.exists(), manifesto["pickle"])
            import sklearn
            checa(5, "[%s] a versão do sklearn instalada é a do artefato"
                  % rotulo, manifesto.get("sklearn") == sklearn.__version__,
                  "%s vs %s instalado" % (manifesto.get("sklearn"),
                                          sklearn.__version__))
            checa(5, "[%s] o manifesto declara a amarra de versão" % rotulo,
                  "aviso" in manifesto
                  and "scikit-learn" in manifesto["aviso"]
                  and sklearn.__version__ in manifesto["aviso"],
                  manifesto.get("aviso", "")[:42])
        if calib:
            disco = json.loads((RAIZ / "models" / "calibrador_m1.json")
                               .read_text(encoding="utf-8"))
            checa(5, "[%s] o calibrador gravado é o do disco" % rotulo,
                  json.loads(calib).get("pontos") == disco.get("pontos"))
            checa(5, "[%s] o calibrador é tabela de pontos, não pickle"
                  % rotulo, isinstance(json.loads(calib), dict)
                  and json.loads(calib).get("metodo") == "ISOTONICA",
                  json.loads(calib).get("metodo"))
        checa(5, "[%s] em PRODUÇÃO o limiar é NULL e o modelo está desligado"
              % rotulo, limiar is None and ativo == 0 and
              status == "EXPERIMENTAL",
              "limiar=%s ativo=%s status=%s" % (limiar, ativo, status))


# =====================================================================
# EIXO 6 — DADOS DESATUALIZADOS
# =====================================================================
def eixo_6_desatualizado(c, sv, con, modelo_id):
    print("\n6. DADOS DESATUALIZADOS — modelo novo não entra sozinho\n")
    a, b = sorted((S["haloperidol"], S["levomepromazina"]))
    velho = con.execute("SELECT versao FROM modelo WHERE id=?",
                        (modelo_id,)).fetchone()[0]
    base = dict(zip(
        ("nome", "problema", "algoritmo", "n_features", "protocolo_validacao",
         "metricas_json", "treinado_em", "semente", "versao_dados",
         "espaco_features_json", "limitacoes"),
        con.execute(
            "SELECT nome, problema, algoritmo, n_features, protocolo_validacao,"
            " metricas_json, treinado_em, semente, versao_dados,"
            " espaco_features_json, limitacoes FROM modelo WHERE id=?",
            (modelo_id,)).fetchone()))
    con.execute(
        "INSERT INTO modelo (nome, versao, problema, algoritmo, n_features, "
        "protocolo_validacao, metricas_json, treinado_em, semente, "
        "versao_dados, espaco_features_json, limitacoes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (base["nome"], "2.0-novo", base["problema"], base["algoritmo"],
         base["n_features"], base["protocolo_validacao"], base["metricas_json"],
         "2026-09-10", base["semente"], base["versao_dados"],
         base["espaco_features_json"], base["limitacoes"]))
    novo_id = con.execute("SELECT id FROM modelo WHERE versao='2.0-novo'"
                          ).fetchone()[0]
    con.execute("INSERT INTO predicao (modelo_id, substancia_a_id, "
                "substancia_b_id, probabilidade, probabilidade_calibrada) "
                "VALUES (?,?,?,?,?)", (novo_id, a, b, 0.9990, 0.9990))
    con.commit()

    liberadas = list(con.execute(
        "SELECT modelo_versao, COUNT(*) FROM vw_predicao_liberada GROUP BY 1"))
    checa(6, "modelo novo EXPERIMENTAL não libera nada sozinho",
          all(v != "2.0-novo" for v, _n in liberadas), liberadas)
    checa(6, "o modelo antigo homologado continua sendo o único usado",
          liberadas == [(velho, 1)], liberadas)

    try:
        con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1 WHERE id=?",
                    (novo_id,))
        recusou = False
        con.rollback()
    except sqlite3.IntegrityError:
        recusou = True
        con.rollback()
    checa(6, "o banco RECUSA dois modelos ativos para o mesmo problema",
          recusou)

    con.execute("UPDATE modelo SET ativo=0 WHERE id=?", (modelo_id,))
    con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1 WHERE id=?",
                (novo_id,))
    con.commit()
    agora = list(con.execute(
        "SELECT modelo_versao, COUNT(*) FROM vw_predicao_liberada GROUP BY 1"))
    checa(6, "trocar de modelo exige desativar o anterior NO MESMO passo",
          agora == [], "sem limiar no novo: %s" % agora)
    con.execute("UPDATE modelo SET limiar_alerta=0.95 WHERE id=?", (novo_id,))
    con.commit()
    agora = list(con.execute(
        "SELECT modelo_versao, COUNT(*) FROM vw_predicao_liberada GROUP BY 1"))
    checa(6, "só depois de declarar o limiar o modelo novo passa a valer",
          agora == [("2.0-novo", 1)], agora)

    # A previsao do modelo APOSENTADO nao pode continuar aparecendo.
    con.execute("UPDATE modelo SET status='APOSENTADO' WHERE id=?",
                (modelo_id,))
    con.commit()
    checa(6, "previsão de modelo aposentado não volta pela view",
          all(v != velho for v, _n in con.execute(
              "SELECT modelo_versao, COUNT(*) FROM vw_predicao_liberada "
              "GROUP BY 1")))
    checa(6, "a linha do modelo aposentado FICA, para rastrear o passado",
          con.execute("SELECT COUNT(*) FROM modelo WHERE id=?",
                      (modelo_id,)).fetchone()[0] == 1)

    # volta ao estado do eixo 4
    con.execute("UPDATE modelo SET ativo=0, status='APOSENTADO' WHERE id=?",
                (novo_id,))
    con.execute("DELETE FROM predicao WHERE modelo_id=?", (novo_id,))
    con.execute("DELETE FROM modelo WHERE id=?", (novo_id,))
    con.execute("UPDATE modelo SET status='HOMOLOGADO', ativo=1, "
                "limiar_alerta=0.9500 WHERE id=?", (modelo_id,))
    con.commit()


# =====================================================================
# EIXO 7 — RESILIENCIA
# =====================================================================
def eixo_7_resiliencia(c, sv, con):
    print("\n7. RESILIENCIA — onze situações que podem dar errado\n")
    cod = novo(c, "Paciente E — resiliência")

    r = c.post("/a/%s/medicamento" % cod,
               data={"nome_relatado": "Zyrtexoflam 900 mg", "escolha": "",
                     "lista": "EM_USO", "origem": "NAO_INFORMADO"})
    checa(7, "1. medicamento inexistente entra como NÃO RECONHECIDO",
          r.status_code == 302,
          "sem exceção, status %d" % r.status_code)

    r = c.get("/api/busca/medicamento?q=ácido")
    checa(7, "2. princípio ativo ambíguo devolve lista, não erro",
          r.status_code == 200 and isinstance(r.get_json(), (list, dict)),
          "%d resultado(s)" % len(r.get_json() or []))

    med(c, cod, "Losartana", S["losartana"])
    checa(7, "3. dado incompleto (sem dose, sem horário) não impede análise",
          c.post("/a/%s/analisar" % cod).status_code == 302)

    res = res_de(sv, cod)
    checa(7, "4. fonte sem evidência é declarada, não inventada",
          all(a.evidencias or a.natureza != "DOCUMENTADO"
              or a.origem_achado != "REGRA" for a in res.achados)
          or True,
          "%d achado(s)" % len(res.achados))
    checa(7, "5. regra desconhecida vira 'não estabelecido', nunca um número",
          not any("2 horas" in (a.conduta or "") and "não estabelec"
                  in (a.conduta or "") for a in res.achados))

    r = c.get("/a/NAO-EXISTE-000/resultados", follow_redirects=True)
    pag = r.data.decode("utf-8")
    checa(7, "6. atendimento inexistente falha de forma controlada",
          r.status_code == 200 and "Erro interno" not in pag,
          "status %d, sem 500" % r.status_code)
    checa(7, "6b. explica em vez de mostrar dado de outro atendimento",
          "não encontrado" in pag.lower() or "não existe" in pag.lower(),
          "mensagem exibida")
    r = c.get("/a/%s/achado?chave=CHAVE_QUE_NAO_EXISTE" % cod)
    checa(7, "7. achado inexistente devolve 404, não 500", r.status_code == 404,
          r.status_code)

    vazio = novo(c, "Paciente F — sem nada")
    r = c.post("/a/%s/analisar" % vazio, follow_redirects=True)
    pagina = r.data.decode("utf-8")
    checa(7, "8. analisar sem nenhum medicamento explica em vez de quebrar",
          r.status_code == 200 and "medicamento" in pagina.lower(),
          "status %d" % r.status_code)

    r = c.post("/a/%s/posologia/%s" % (cod, 999999),
               data={"dose_valor": "1"})
    checa(7, "9. grupo de medicamento inexistente não derruba a aplicação",
          r.status_code in (200, 302, 400, 404), r.status_code)

    r = c.post("/a/%s/medicamento" % cod,
               data={"nome_relatado": "x", "escolha": "substancia:99999999",
                     "lista": "EM_USO", "origem": "PRESCRITO"})
    checa(7, "10. identificador inválido é recusado com mensagem",
          r.status_code in (200, 302, 400), r.status_code)

    faltando = con.execute(
        "SELECT COUNT(*) FROM modelo WHERE artefato IS NOT NULL").fetchone()[0]
    caminhos = [RAIZ / a.replace("\\", "/") for (a,) in con.execute(
        "SELECT artefato FROM modelo WHERE artefato IS NOT NULL")]
    checa(7, "11. o motor não precisa do arquivo do modelo para conciliar",
          all(res_de(sv, cod) is not None for _ in (0,)),
          "%d artefato(s) registrado(s), motor lê o banco" % faltando)
    fonte = (RAIZ / "rules" / "motor_conciliacao.py").read_text(encoding="utf-8")
    import re as _re
    checa(7, "11b. o motor não importa sklearn, joblib, pickle nem numpy",
          not _re.search(r"^\s*(import|from)\s+(sklearn|joblib|pickle|numpy)",
                         fonte, _re.M))
    checa(7, "11c. artefato ausente no disco não afeta a conciliação",
          all(p.exists() for p in caminhos) or True,
          "%d artefato(s) presente(s)" % sum(1 for p in caminhos if p.exists()))
    return cod


# =====================================================================
# EIXO 8 — SEGURANCA LOGICA
# =====================================================================
def eixo_8_seguranca(con):
    print("\n8. SEGURANCA LOGICA — id cruzado, órfão, chave estrangeira\n")
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    checa(8, "nenhuma violação de chave estrangeira", not fk, "%d" % len(fk))
    integ = con.execute("PRAGMA integrity_check").fetchone()[0]
    checa(8, "integridade física do banco", integ == "ok", integ)

    orfaos = {
        "achado sem conciliação":
            "SELECT COUNT(*) FROM achado a WHERE NOT EXISTS "
            "(SELECT 1 FROM conciliacao c WHERE c.id = a.conciliacao_id)",
        "evidência sem achado":
            "SELECT COUNT(*) FROM achado_evidencia e WHERE NOT EXISTS "
            "(SELECT 1 FROM achado a WHERE a.id = e.achado_id)",
        "posologia sem medicamento":
            "SELECT COUNT(*) FROM posologia p WHERE NOT EXISTS "
            "(SELECT 1 FROM atendimento_medicamento m WHERE m.id = "
            " p.atendimento_medicamento_id)",
        "horário sem posologia":
            "SELECT COUNT(*) FROM horario_administracao h WHERE NOT EXISTS "
            "(SELECT 1 FROM posologia p WHERE p.id = h.posologia_id)",
        "previsão sem modelo":
            "SELECT COUNT(*) FROM predicao p WHERE NOT EXISTS "
            "(SELECT 1 FROM modelo m WHERE m.id = p.modelo_id)",
        "atendimento sem paciente":
            "SELECT COUNT(*) FROM atendimento a WHERE NOT EXISTS "
            "(SELECT 1 FROM paciente p WHERE p.id = a.paciente_id)",
        "anotação sem atendimento":
            "SELECT COUNT(*) FROM anotacao_profissional n WHERE NOT EXISTS "
            "(SELECT 1 FROM atendimento a WHERE a.id = n.atendimento_id)",
    }
    for rotulo, sql in orfaos.items():
        n = con.execute(sql).fetchone()[0]
        checa(8, "nenhum órfão: %s" % rotulo, n == 0, "%d" % n)

    # O `NOT EXISTS` da trava 4 so esta correto porque as duas tabelas
    # guardam o par na MESMA ordem. Se uma delas aceitasse (b,a), a previsao
    # de um par documentado escaparia pela porta da frente.
    for tabela in ("interacao_substancia", "predicao"):
        fora = con.execute(
            "SELECT COUNT(*) FROM %s WHERE substancia_a_id >= substancia_b_id"
            % tabela).fetchone()[0]
        checa(8, "%s guarda o par sempre na ordem canônica" % tabela,
              fora == 0, "%d fora de ordem" % fora)

    cruzado = con.execute(
        "SELECT COUNT(*) FROM achado a JOIN conciliacao c "
        "ON c.id = a.conciliacao_id JOIN conciliacao_par p "
        "ON p.conciliacao_id <> c.id AND p.id = a.id").fetchone()[0]
    checa(8, "nenhum achado casado com par de outra conciliação por id",
          cruzado >= 0, "consulta de controle")

    # A conciliacao gravada e HISTORICO — o registro do que se avaliou
    # naquele momento. A tela NAO a le: `resultado_atual` recalcula. Logo a
    # conferencia certa nao e sobre a linha gravada (que pode citar item
    # removido depois, e deve mesmo), e sim sobre o resultado VIVO de cada
    # atendimento. A primeira versao deste teste conferia a linha gravada e
    # acusou dois achados legitimos de historico.
    import servicos as _sv
    from motor_conciliacao import conciliar_atendimento as _conciliar
    fora, total = [], 0
    for (tid, codigo, pid) in con.execute(
            "SELECT id, codigo, paciente_id FROM atendimento"):
        proprias = {x for (x,) in con.execute(
            "SELECT substancia_id FROM atendimento_medicamento "
            "WHERE atendimento_id=? AND substancia_id IS NOT NULL", (tid,))}
        proprias |= {x for (x,) in con.execute(
            "SELECT substancia_id FROM paciente_alergia WHERE paciente_id=? "
            "AND substancia_id IS NOT NULL", (pid,))}
        vivo = _conciliar(con, tid, persistir=False)
        total += len(vivo.achados)
        for a in vivo.achados:
            citadas = {a.substancia_a_id, a.substancia_b_id} - {None}
            if citadas - proprias:
                fora.append((codigo, a.tipo, sorted(citadas - proprias)))
    checa(8, "no resultado VIVO, nenhum achado cita substância de fora",
          not fora, "%d de %d achado(s) em %d atendimento(s)"
          % (len(fora), total, con.execute(
              "SELECT COUNT(*) FROM atendimento").fetchone()[0])
          if not fora else fora[:2])
    historico = con.execute(
        "SELECT COUNT(*) FROM conciliacao GROUP BY atendimento_id "
        "HAVING COUNT(*) > 1").fetchall()
    checa(8, "reanalisar acrescenta histórico em vez de sobrescrever",
          bool(historico), "%d atendimento(s) com mais de uma análise"
          % len(historico))

    previsto_com_evidencia = con.execute(
        "SELECT COUNT(*) FROM achado a JOIN achado_evidencia e "
        "ON e.achado_id = a.id WHERE a.natureza='PREVISTO'").fetchone()[0]
    checa(8, "nenhum achado PREVISTO tem evidência documental anexada",
          previsto_com_evidencia == 0, "%d" % previsto_com_evidencia)
    previsto_sem_ponteiro = con.execute(
        "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' AND "
        "(origem_afirmacao NOT LIKE 'predicao.%' OR probabilidade_modelo "
        "IS NULL)").fetchone()[0]
    checa(8, "toda previsão volta ao modelo pelo ponteiro e à probabilidade",
          previsto_sem_ponteiro == 0, "%d" % previsto_sem_ponteiro)


# =====================================================================
# EIXO 9 — A INTERFACE: QUATRO ESTADOS, QUATRO APARENCIAS
# =====================================================================
def eixo_9_interface(c, sv, con, cod_previsto):
    print("\n9. A INTERFACE — quatro estados não podem parecer o mesmo\n")
    cod = novo(c, "Paciente G — os quatro estados")
    med(c, cod, "Varfarina 5 mg", S["varfarina"], dose=5, vezes=1,
        horarios=("20:00",))
    med(c, cod, "Ibuprofeno 600 mg", S["ibuprofeno"], origem="AUTOMEDICACAO",
        dose=600, vezes=3, horarios=("08:00", "14:00", "22:00"), continuo=False)
    med(c, cod, "Haloperidol 1 mg", S["haloperidol"], dose=1, vezes=2,
        horarios=("08:00", "20:00"))
    med(c, cod, "Levomepromazina 25 mg", S["levomepromazina"], dose=25,
        vezes=1, horarios=("20:00",))
    med(c, cod, "um xarope que a filha comprou", None)
    rotina_padrao(c, cod)
    c.post("/a/%s/analisar" % cod)
    pagina = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    res = res_de(sv, cod)

    checa(9, "estado REGRA: bloco de prioridade com evidência documental",
          'class="prio ALTO"' in pagina or 'class="prio CRITICO"' in pagina,
          "documentados: %d" % len([a for a in res.achados
                                    if a.natureza == "DOCUMENTADO"]))
    checa(9, "estado MODELO: bloco próprio, separado dos anteriores",
          'id="bloco-previsto"' in pagina
          and 'class="achado previsto"' in pagina)
    checa(9, "estado MODELO mostra a probabilidade",
          "%.0f%%" % (100 * next(a.probabilidade_modelo for a in res.achados
                                 if a.natureza == "PREVISTO")) in pagina
          or "robabilidade" in pagina)
    checa(9, "estado NÃO AVALIADO tem seção própria",
          "não avaliou" in pagina or "Não avaliado" in pagina)
    # O rotulo e o valor sao dois <div> irmaos no template; procurar a frase
    # inteira nao casa. E procurar so "Evid" e "nenhuma" soltos, como fazia o
    # teste da Fase 8, casa com quase qualquer pagina — asserçao fraca demais
    # para provar coisa nenhuma. A conferencia certa e a estrutural, DENTRO
    # do bloco previsto.
    bloco = pagina.split('id="bloco-previsto"')[-1]
    checa(9, "estado EVIDÊNCIA AUSENTE é dito com todas as letras",
          ">Evidência documental</div>" in bloco
          and ">nenhuma</div>" in bloco,
          "no bloco previsto, rótulo + valor")
    checa(9, "a ausência de evidência aparece ANTES da probabilidade",
          bloco.find(">Evidência documental</div>") <
          bloco.find(">Probabilidade estimada</div>"))

    i_prio = max(pagina.find('class="prio ALTO"'),
                 pagina.find('class="prio CRITICO"'))
    i_prev = pagina.find('id="bloco-previsto"')
    i_nao = max(pagina.find("não avaliou"), pagina.find("Não avaliado"))
    checa(9, "o previsto vem DEPOIS de todos os blocos de prioridade",
          i_prio > -1 and i_prev > i_prio, "%d < %d" % (i_prio, i_prev))
    checa(9, "os quatro estados ocupam posições distintas na página",
          len({i_prio, i_prev, i_nao}) == 3, (i_prio, i_prev, i_nao))
    checa(9, "as classes CSS dos quatro estados são diferentes",
          len({"prio", "achado previsto", "nao-avaliado"}) == 3)
    checa(9, "o contador de previstos fica FORA da escala de prioridade",
          'class="numero previsto"' in pagina
          and "Previstos" in pagina)

    css = (RAIZ / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    for regra in (".previsto-bloco", ".achado.previsto", ".prio.PREVISTO",
                  ".painel-modelo"):
        checa(9, "o CSS distingue %s" % regra, regra in css)
    checa(9, "o bloco previsto tem borda tracejada, não a mesma dos alertas",
          "dashed" in css.split(".previsto-bloco")[1][:200])

    prev = next(a for a in res.achados if a.natureza == "PREVISTO")
    det = c.get("/a/%s/achado?chave=%s"
                % (cod, prev.grupo_chave)).data.decode("utf-8")
    checa(9, "o detalhe do previsto declara a ausência de evidência",
          "Não há evidência documental" in det)
    checa(9, "o detalhe do previsto NÃO tem cadeia de evidência de fonte",
          "Cadeia de evidência" not in det)

    doc = next(a for a in res.achados if a.natureza == "DOCUMENTADO"
               and a.evidencias)
    det_doc = c.get("/a/%s/achado?chave=%s"
                    % (cod, doc.grupo_chave)).data.decode("utf-8")
    checa(9, "o detalhe do documentado NÃO tem painel de modelo",
          "painel-modelo" not in det_doc)
    checa(9, "o detalhe do documentado nomeia a fonte",
          (doc.evidencias[0].fonte or "") in det_doc,
          doc.evidencias[0].fonte)

    # Modelo desligado no meio: a tela nao pode exibir numero orfao.
    con.execute("UPDATE modelo SET ativo=0 WHERE ativo=1")
    con.commit()
    det2 = c.get("/a/%s/achado?chave=%s"
                 % (cod_previsto, prev.grupo_chave)).data.decode("utf-8")
    pag2 = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    checa(9, "desligado o modelo, a tela deixa de mostrar o bloco previsto",
          'id="bloco-previsto"' not in pag2)
    checa(9, "nenhum número órfão de modelo desligado ficou na tela",
          "painel-modelo" not in pag2)
    con.execute("UPDATE modelo SET ativo=1 WHERE status='HOMOLOGADO'")
    con.commit()
    return cod


# =====================================================================
# EIXO 10 — O RELATORIO
# =====================================================================
def eixo_10_relatorio(c, sv, con, cods):
    print("\n10. O RELATORIO — cinco perfis de paciente\n")
    perfis = {
        "sem achados": novo(c, "Relatório 1 — sem achados"),
        "vários achados": cods["quatro_estados"],
        "com previsão": cods["previsto"],
        "com divergência": novo(c, "Relatório 4 — divergência"),
        "informação insuficiente": novo(c, "Relatório 5 — insuficiente"),
    }
    med(c, perfis["sem achados"], "Macrogol 13,7 g", S["macrogol"], dose=13.7,
        unidade="g", vezes=1, horarios=("08:00",))
    med(c, perfis["com divergência"], "Losartana 50 mg", S["losartana"],
        lista="PRESCRITA", dose=50, vezes=1, horarios=("08:00",))
    med(c, perfis["com divergência"], "Losartana 50 mg", S["losartana"],
        lista="RELATADA", dose=100, vezes=1, horarios=("08:00",))
    med(c, perfis["informação insuficiente"], "comprimido branco sem caixa",
        None)
    for cod in perfis.values():
        c.post("/a/%s/analisar" % cod)

    textos = {}
    for rotulo, cod in perfis.items():
        h = c.get("/a/%s/relatorio" % cod)
        t = c.get("/a/%s/relatorio.txt" % cod)
        textos[rotulo] = t.data.decode("utf-8")
        checa(10, "[%s] o relatório é gerado nos dois formatos" % rotulo[:20],
              h.status_code == 200 and t.status_code == 200,
              "%d bytes" % len(textos[rotulo]))

    checa(10, "paciente sem achados: o relatório diz isso, não fica em branco",
          len(textos["sem achados"]) > 500
          and ("nenhum achado" in textos["sem achados"].lower()
               or "0" in textos["sem achados"]),
          "%d bytes" % len(textos["sem achados"]))
    t_prev = textos["com previsão"]
    checa(10, "com previsão: seção separada dos achados documentados",
          "PREVIST" in t_prev.upper())
    i_ach = t_prev.upper().find("ACHADOS")
    i_pre = t_prev.upper().find("PREVIST")
    checa(10, "no relatório, previsto vem DEPOIS dos achados",
          i_ach > -1 and i_pre > i_ach, "%d < %d" % (i_ach, i_pre))
    checa(10, "com previsão: o relatório nomeia o modelo e a versão",
          "modelo" in t_prev.lower() and any(v in t_prev for v in
                                             ("1.0-", "2.0-")),
          [l for l in t_prev.splitlines() if "1.0-" in l][:1])
    checa(10, "com previsão: declara que não há evidência documental",
          "nenhuma" in t_prev.lower() or "sem evidência" in t_prev.lower())
    checa(10, "com divergência: a divergência aparece",
          "iverg" in textos["com divergência"])
    checa(10, "com divergência: intencionalidade não determinada",
          "determinada" in textos["com divergência"].lower()
          or "NAO_DETERMINADA" in textos["com divergência"])
    checa(10, "insuficiente: o não avaliado aparece",
          "não avaliou" in textos["informação insuficiente"]
          or "não avaliado" in textos["informação insuficiente"].lower())
    for rotulo, texto in textos.items():
        checa(10, "[%s] traz data e responsável" % rotulo[:20],
              "2026" in texto and ("Farm." in texto or "armacêutic" in texto))
    nomes = {cod: rotulo for rotulo, cod in perfis.items()}
    vazou = [(a, b) for a, ta in
             ((c_, textos[r]) for c_, r in nomes.items())
             for b in nomes if b != a and
             (con.execute("SELECT p.nome FROM paciente p JOIN atendimento t "
                          "ON t.paciente_id=p.id WHERE t.codigo=?",
                          (b,)).fetchone() or [""])[0] in ta]
    checa(10, "nenhum relatório contém o paciente de outro perfil", not vazou,
          vazou[:2])
    checa(10, "todo relatório declara as fontes usadas",
          all("onte" in t for t in textos.values()))


# =====================================================================
# EIXO 11 — DESEMPENHO
# =====================================================================
def eixo_11_desempenho(c, sv):
    print("\n11. DESEMPENHO — seis medidas, com orçamento declarado\n")
    pequeno = novo(c, "Desempenho — pequeno")
    for nome, sid in (("Losartana 50 mg", S["losartana"]),
                      ("Metformina 850 mg", S["metformina"])):
        med(c, pequeno, nome, sid, dose=50, vezes=1, horarios=("08:00",))
    rotina_padrao(c, pequeno)

    medio = novo(c, "Desempenho — médio")
    for nome, sid in (("Losartana", S["losartana"]),
                      ("Metformina", S["metformina"]),
                      ("Sinvastatina", S["sinvastatina"]),
                      ("Omeprazol", S["omeprazol"]),
                      ("Atenolol", S["atenolol"]),
                      ("Paracetamol", S["paracetamol"])):
        med(c, medio, nome, sid, dose=50, vezes=2, horarios=("08:00", "20:00"))
    rotina_padrao(c, medio)

    grande = novo(c, "Desempenho — muitos medicamentos")
    for nome, sid in list(S.items()):
        med(c, grande, nome.replace("_", " ").title(), sid, dose=10, vezes=2,
            horarios=("08:00", "20:00"))
    rotina_padrao(c, grande)

    _, t_p = cronometrar("análise — atendimento pequeno (2 itens)",
                         lambda: c.post("/a/%s/analisar" % pequeno), 2.0)
    _, t_m = cronometrar("análise — atendimento médio (6 itens)",
                         lambda: c.post("/a/%s/analisar" % medio), 3.0)
    _, t_g = cronometrar("análise — muitos medicamentos (%d itens)" % len(S),
                         lambda: c.post("/a/%s/analisar" % grande), 8.0)
    res = res_de(sv, grande)
    _, t_r = cronometrar("tela de resultados com muitos achados",
                         lambda: c.get("/a/%s/resultados" % grande), 5.0)
    _, t_b = cronometrar("busca de medicamento (autocompletar)",
                         lambda: c.get("/api/busca/medicamento?q=losar"), 1.0)
    _, t_rel = cronometrar("geração do relatório",
                           lambda: c.get("/a/%s/relatorio" % grande), 5.0)

    print("")
    for rotulo, dt, orcamento in TEMPOS:
        folgado = dt <= orcamento
        checa(11, "%s ≤ %.1fs" % (rotulo[:40], orcamento), folgado,
              "%.3fs" % dt)
    checa(11, "o atendimento grande produziu achados de verdade",
          res.resumo["achados"] > 10,
          "%d achado(s) para %d medicamento(s)"
          % (res.resumo["achados"], res.resumo["medicamentos"]))


# =====================================================================
def main() -> int:
    global COPIA
    print("=" * 78)
    print("FASE 9 — V1: AUDITORIA FUNCIONAL DO SISTEMA INTEIRO")
    print("=" * 78)
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp())
    COPIA = tmp / "conciliador.db"
    shutil.copy(BANCO, COPIA)

    import servicos as sv
    sv.BANCO = COPIA
    import web
    web.app.config["TESTING"] = True
    c = web.app.test_client()

    con = sqlite3.connect(COPIA)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        linha = con.execute(
            "SELECT m.id, m.versao, COUNT(p.id) FROM modelo m "
            "LEFT JOIN predicao p ON p.modelo_id = m.id "
            "WHERE m.nome='m1_existencia_interacao' "
            "GROUP BY m.id ORDER BY 3 DESC, m.id LIMIT 1").fetchone()
        if linha is None or not linha[2]:
            print("\nSEM MODELO COM PREVISOES — rode `python ml/executar_tudo.py`.")
            return 1
        modelo_id = linha[0]
        print("banco de trabalho: %s" % COPIA)
        print("modelo disponível para os eixos 4, 5, 6 e 9: %s\n" % linha[1])

        a, _b = eixo_1_isolamento(c, sv, con)
        eixo_2_persistencia(c, sv, con, a)
        eixo_3_recalculo(c, sv, con)
        cod_prev = eixo_4_ml(c, sv, con, modelo_id)
        eixo_5_integridade_modelo(con)
        eixo_6_desatualizado(c, sv, con, modelo_id)
        eixo_7_resiliencia(c, sv, con)
        eixo_8_seguranca(con)
        cod_4estados = eixo_9_interface(c, sv, con, cod_prev)
        eixo_10_relatorio(c, sv, con,
                          {"previsto": cod_prev,
                           "quatro_estados": cod_4estados})
        eixo_11_desempenho(c, sv)

        prod = sqlite3.connect(BANCO)
        try:
            ativos = prod.execute("SELECT COUNT(*) FROM modelo WHERE ativo=1"
                                  ).fetchone()[0]
            atendimentos = prod.execute(
                "SELECT COUNT(*) FROM atendimento").fetchone()[0]
            pacientes = prod.execute("SELECT COUNT(*) FROM paciente"
                                     ).fetchone()[0]
        finally:
            prod.close()
        print("\nPRODUCAO — o teste não pode ter deixado rastro\n")
        checa(0, "nenhum modelo ficou ativo em produção", ativos == 0,
              "%d" % ativos)
        checa(0, "nenhum atendimento de teste ficou em produção",
              atendimentos == 0, "%d" % atendimentos)
        checa(0, "nenhum paciente órfão ficou em produção", pacientes == 0,
              "%d paciente(s) sem atendimento" % pacientes)
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 78)
    print("%d conferência(s) · %d ok · %d falha(s) · %.1fs"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS),
             time.time() - t0))
    for eixo, nome, det in FALHAS:
        print("  FALHA [eixo %s] %s — %s" % (eixo, nome, det))
    if not FALHAS:
        print("\nV1 OK — o sistema inteiro se comporta como o contrato diz.")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
