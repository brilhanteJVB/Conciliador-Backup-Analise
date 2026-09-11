# -*- coding: utf-8 -*-
"""
Carga das regras de administracao e separacao.

FONTE: DrugBank food-interactions (1.423 farmacos). O campo nao e so
'interacao com alimento': carrega a orientacao de administracao (jejum, com
alimento, com agua) e as separacoes por quelacao (antiacido, calcio, ferro,
laticinio). Classificacao em pipeline/_diretivas.py.

Vinculo com o Brasil: nome em ingles -> esqueleto fonetico -> substancia.
So entram farmacos que existem no Brasil.

INTERVALO: gravado apenas quando a fonte o declara. Frase que manda separar
sem dizer quanto vira regra com intervalo NULL, e a interface diz
'Requer separacao -- intervalo nao estabelecido na fonte'. Nunca um numero
por analogia (DECISIONS.md D-013).

Uso: python pipeline/50_regras_administracao.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (ACERVO, abrir_carga, chaves_candidatas, conectar,  # noqa: E402
                    fechar_carga, id_fonte, registrar_evidencia, resumo)
from _diretivas import classificar  # noqa: E402
from normalizacao import skeleton  # noqa: E402

ARQ = "Drug to Food interactions Dataset.json"
FONTE = "DrugBank - interacoes com alimento"

# Codigo ATC dos antiacidos: a separacao por antiacido e por CLASSE, nao por
# substancia -- vale para todo o grupo A02A.
ATC_ANTIACIDO = "A02A"


def esq(nome: str) -> str:
    if not nome:
        return ""
    s = skeleton(nome)
    return s if s and len(s) >= 3 else ""


def id_item(con, nome: str, tipo: str) -> int:
    """Cria (ou recupera) o item nao medicamentoso, em portugues."""
    r = con.execute("SELECT id FROM item_nao_medicamentoso WHERE nome=?",
                    (nome,)).fetchone()
    if r:
        return r[0]
    cur = con.execute(
        "INSERT INTO item_nao_medicamentoso (nome,chave_normalizada,tipo) "
        "VALUES (?,?,?)", (nome, esq(nome) or nome, tipo))
    return cur.lastrowid


def main() -> int:
    con = conectar()
    fid = id_fonte(con, FONTE)
    carga = abrir_carga(con, FONTE, "50_regras_administracao.py", ARQ,
                        versao="DrugBank 6.0")

    indice = {}
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        indice.setdefault(chave, sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        indice.setdefault(chave, sid)

    dados = json.loads((ACERVO / ARQ).read_text(encoding="utf-8"))
    lidos = len(dados)

    n_adm = n_sep = n_item = n_hab = 0
    com_intervalo = sem_intervalo = 0
    nao_br = 0
    tipos = Counter()
    itens_criados = {}

    for reg in dados:
        nome_en = (reg.get("name") or "").strip()
        texto = " ".join(reg.get("food_interactions") or []).strip()
        if not nome_en or not texto:
            continue
        # tenta o esqueleto direto e o candidato '-ic acid' -> '-ate':
        # 'alendronic acid' (EN) e 'alendronato de sodio' (BR) sao o mesmo
        # farmaco e nao casavam pelo esqueleto direto.
        sid = None
        for chave in chaves_candidatas(nome_en):
            sid = indice.get(chave)
            if sid:
                break
        if sid is None:
            nao_br += 1
            continue

        d = classificar(texto)

        # --- regras de administracao
        for a in d["administracao"]:
            cur = con.execute(
                "INSERT OR IGNORE INTO regra_administracao (substancia_id,tipo,"
                "intervalo_refeicao_min,texto_orientacao,origem,fonte_id,"
                "status_revisao) VALUES (?,?,?,?,'FONTE_EXTERNA',?,'PENDENTE')",
                (sid, a["tipo"], a["intervalo_refeicao_min"],
                 a["texto_orientacao"], fid))
            if cur.rowcount:
                n_adm += 1
                tipos[a["tipo"]] += 1
                registrar_evidencia(con, "regra_administracao", cur.lastrowid,
                                    fid, carga, ARQ, "LIMITADA", "REGEX", texto[:400])

        # --- regras de separacao
        for s in d["separacao"]:
            if s["tipo_item"] == "CLASSE_ATC":
                existe = con.execute("SELECT 1 FROM classe_atc WHERE codigo=?",
                                     (ATC_ANTIACIDO,)).fetchone()
                if not existe:
                    continue
                campos = ("CLASSE_ATC", None, None, ATC_ANTIACIDO)
            else:
                iid = itens_criados.get(s["item"])
                if iid is None:
                    iid = id_item(con, s["item"], s["tipo_item"])
                    itens_criados[s["item"]] = iid
                campos = ("ITEM", None, iid, None)
            cur = con.execute(
                "INSERT OR IGNORE INTO regra_separacao (substancia_id,alvo_tipo,"
                "alvo_substancia_id,alvo_item_id,alvo_classe_atc,intervalo_horas,"
                "motivo,origem,fonte_id,status_revisao) "
                "VALUES (?,?,?,?,?,?,?,'FONTE_EXTERNA',?,'PENDENTE')",
                (sid, campos[0], campos[1], campos[2], campos[3],
                 s["intervalo_horas"], s["motivo"], fid))
            if cur.rowcount:
                n_sep += 1
                if s["intervalo_horas"] is None:
                    sem_intervalo += 1
                else:
                    com_intervalo += 1
                registrar_evidencia(con, "regra_separacao", cur.lastrowid, fid,
                                    carga, ARQ, "LIMITADA", "REGEX", texto[:400])

        # --- interacao com item (alimento, planta, mineral)
        for i in d["itens"]:
            iid = itens_criados.get(i["item"])
            if iid is None:
                iid = id_item(con, i["item"], i["tipo_item"])
                itens_criados[i["item"]] = iid
            cur = con.execute(
                "INSERT OR IGNORE INTO interacao_item (substancia_id,item_id,"
                "efeito_esperado,descricao_original,gravidade,origem,fonte_id,"
                "status_revisao) VALUES (?,?,?,?,?,'FONTE_EXTERNA',?,'PENDENTE')",
                (sid, iid, i["efeito"], texto[:500], i["gravidade"], fid))
            if cur.rowcount:
                n_item += 1
                registrar_evidencia(con, "interacao_item", cur.lastrowid, fid,
                                    carga, ARQ, "LIMITADA", "REGEX", texto[:400])

        # --- interacao com habito
        for h in d["habitos"]:
            cur = con.execute(
                "INSERT OR IGNORE INTO interacao_habito (substancia_id,habito,"
                "efeito_esperado,gravidade,origem,fonte_id,status_revisao) "
                "VALUES (?,?,?,?,'FONTE_EXTERNA',?,'PENDENTE')",
                (sid, h["habito"], h["efeito"], h["gravidade"], fid))
            if cur.rowcount:
                n_hab += 1
                registrar_evidencia(con, "interacao_habito", cur.lastrowid, fid,
                                    carga, ARQ, "LIMITADA", "REGEX", texto[:400])


    # Duas entradas do DrugBank podem cair na MESMA substancia brasileira:
    # 'Fenofibrate' e 'Fenofibric acid' chegam a fenofibrato pela chave
    # candidata '-ic acid' -> '-ate'. Quando isso traz orientacoes
    # alimentares excludentes, a fonte passa a afirmar duas coisas
    # contrarias para o mesmo farmaco. Por D-023 nenhuma e gravada: o caso
    # vai para auditoria e a decisao fica com o farmaceutico.
    EXCLUSIVOS = ("JEJUM", "COM_ALIMENTO", "APOS_ALIMENTO",
                  "ANTES_ALIMENTO", "INDIFERENTE_ALIMENTO")
    marcadores = ",".join("?" * len(EXCLUSIVOS))
    contraditorias = con.execute(
        "SELECT substancia_id, fonte_id FROM regra_administracao "
        "WHERE tipo IN (%s) GROUP BY substancia_id, fonte_id "
        "HAVING COUNT(DISTINCT tipo) > 1" % marcadores, EXCLUSIVOS).fetchall()
    n_contradicoes = 0
    for sid_c, fid_c in contraditorias:
        tipos_c = [t for (t,) in con.execute(
            "SELECT DISTINCT tipo FROM regra_administracao "
            "WHERE substancia_id=? AND fonte_id=? AND tipo IN (%s)" % marcadores,
            (sid_c, fid_c) + EXCLUSIVOS)]
        nome_c = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                             (sid_c,)).fetchone()[0]
        fonte_c = con.execute("SELECT nome FROM fonte WHERE id=?",
                              (fid_c,)).fetchone()[0]
        ids = [i for (i,) in con.execute(
            "SELECT id FROM regra_administracao WHERE substancia_id=? "
            "AND fonte_id=? AND tipo IN (%s)" % marcadores,
            (sid_c, fid_c) + EXCLUSIVOS)]
        for rid in ids:
            con.execute("DELETE FROM evidencia WHERE tabela_alvo='regra_administracao' "
                        "AND id_alvo=?", (rid,))
            con.execute("DELETE FROM regra_administracao WHERE id=?", (rid,))
        con.execute(
            "INSERT OR IGNORE INTO auditoria_conflito (tabela_alvo,id_alvo,descricao,"
            "fonte_a,valor_a,fonte_b,valor_b,decisao,justificativa) "
            "VALUES ('regra_administracao',?,?,?,?,?,?,'NAO_RESOLVIDO',?)",
            (sid_c,
             "%s: a mesma fonte afirma orientacoes alimentares excludentes"
             % nome_c,
             fonte_c, tipos_c[0], fonte_c, tipos_c[1],
             "Provavel colisao de entidades: duas entradas da fonte caem na "
             "mesma substancia brasileira. Nenhuma regra foi mantida; "
             "requer leitura humana."))
        n_contradicoes += 1
        n_adm -= len(ids)

    con.commit()
    fechar_carga(con, carga, lidos, n_adm + n_sep + n_item + n_hab, nao_br,
                 "ignorados = farmacos sem produto ativo no Brasil")

    subst_com_regra = con.execute(
        "SELECT COUNT(DISTINCT substancia_id) FROM regra_administracao"
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]

    resumo("REGRAS DE ADMINISTRACAO", [
        ("farmacos no DrugBank", lidos),
        ("  sem produto ativo no Brasil (ignorados)", nao_br),
        ("regras de administracao", n_adm),
        ("regras de separacao", n_sep),
        ("  com intervalo declarado pela fonte", com_intervalo),
        ("  SEM intervalo (fonte nao publica)", sem_intervalo),
        ("interacoes com item (alimento/planta/mineral)", n_item),
        ("interacoes com habito (alcool/cafeina)", n_hab),
        ("itens nao medicamentosos criados", len(itens_criados)),
        ("contradicoes intra-fonte removidas", n_contradicoes),
        ("substancias BR com regra de administracao", "%d de %d (%.1f%%)" %
         (subst_com_regra, total, 100 * subst_com_regra / max(1, total))),
    ])
    print("\n  por tipo de regra:")
    for t, n in tipos.most_common():
        print("    %-30s %d" % (t, n))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
