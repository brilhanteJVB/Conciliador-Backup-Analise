# -*- coding: utf-8 -*-
"""
Carga de substancias: identidade farmacologica brasileira.

ANCORA: substancias de produtos com registro ATIVO na ANVISA -- o que
existe no Brasil. NOMENCLATURA: DCB (IN 462), que da nome oficial,
numero DCB e CAS.

RESOLUCAO DE ENTIDADES, em niveis (especificacao da Fase 2):
  N1 identificador exato ...... CO_SUBSTANCIA da ANVISA
  N2 identificador alternativo  numero DCB e CAS
  N3 normalizacao textual ..... esqueleto fonetico (pipeline/normalizacao.py)
  N4 fuzzy controlado ......... nao usado aqui; o esqueleto ja resolve
  N5 revisao de ambiguidade ... gravado em resolucao_ambigua, nunca fundido

Uma substancia = uma fracao ativa. 'cloridrato de fluoxetina' e
'fluoxetina' sao a MESMA substancia para efeito de interacao; a forma com
sal vira sinonimo, nao entidade separada.

Uso: python pipeline/20_substancias.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (ACERVO, campo, conectar, abrir_carga, fechar_carga,  # noqa: E402
                    id_fonte, inserir_unico, ler_csv, registrar_evidencia,
                    resumo)
from _substancia_texto import dividir  # noqa: E402
from normalizacao import skeleton  # noqa: E402

ARQ_ANVISA = "TA_CONSULTA_MEDICAMENTOS.CSV"
ARQ_DCB = ("fontes_novas/03_dcb_denominacoes/"
           "DCB_lista_consolidada_jul2026_IN462_VIGENTE.xlsx")

# A coluna CAS da DCB traz marcador de nota de rodape ("[Ref. 8]") quando a
# substancia nao tem CAS -- vacinas, botanicos e biologicos. Gravar isso como
# identificador quimico seria inventar dado, entao so passa o formato oficial
# do CAS Registry Number: 2 a 7 digitos, 2 digitos, 1 digito de verificacao.
RE_CAS = re.compile(r"^\d{2,7}-\d{2}-\d$")


def cas_valido(v):
    v = (v or "").strip()
    return v if RE_CAS.match(v) else None


def esq(nome: str) -> str:
    if not nome:
        return ""
    s = skeleton(nome)
    return s if s and len(s) >= 3 else ""


# --------------------------------------------------------------------- DCB

def ler_dcb():
    """skeleton -> lista de {numero, nome, cas, classificacao}."""
    import openpyxl
    wb = openpyxl.load_workbook(ACERVO / ARQ_DCB, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    por_esq = defaultdict(list)
    lidas = 0
    for i, linha in enumerate(ws.iter_rows(values_only=True)):
        if i < 2:                      # linha 0 titulo, linha 1 cabecalho
            continue
        numero, nome, cas, classif = (linha + (None,) * 5)[:4]
        if not nome:
            continue
        lidas += 1
        nome = str(nome).strip()
        e = esq(nome)
        if not e:
            continue
        por_esq[e].append({
            "numero": str(numero).strip() if numero else None,
            "nome": nome,
            "cas": cas_valido(str(cas)) if cas else None,
            "classificacao": str(classif).strip() if classif else None,
        })
    wb.close()
    return por_esq, lidas


def canonico(entradas):
    """Escolhe a forma base entre variantes de sal do mesmo esqueleto.

    'abacavir' e 'sulfato de abacavir' reduzem ao mesmo esqueleto. A forma
    base e a de menos palavras; empate resolve pelo menor numero DCB, que e
    deterministico e reproduzivel.
    """
    def chave(e):
        n_palavras = len(e["nome"].split())
        try:
            num = int(e["numero"]) if e["numero"] else 10 ** 9
        except ValueError:
            num = 10 ** 9
        return (n_palavras, num, e["nome"])
    return sorted(entradas, key=chave)[0]


# ------------------------------------------------------------------ ANVISA

def ler_anvisa():
    """Coleta substancias por esqueleto, separando ativas de inativas."""
    grafias = defaultdict(Counter)     # esqueleto -> Counter(grafia)
    ativos = Counter()                 # esqueleto -> n produtos ativos
    co_subst = defaultdict(set)        # esqueleto -> {CO_SUBSTANCIA}
    linhas = 0
    for idx, l in ler_csv(ARQ_ANVISA):
        linhas += 1
        bruto = campo(idx, l, "SUBSTANCIAS_MEDICAMENTOS")
        if not bruto:
            continue
        ativo = campo(idx, l, "VALIDADE_SITUACAO") == "Ativo"
        co = campo(idx, l, "CO_SUBSTANCIA")
        for parte in dividir(bruto):
            e = esq(parte)
            if not e:
                continue
            grafias[e][parte.lower()] += 1
            if ativo:
                ativos[e] += 1
            if co and co.isdigit():
                co_subst[e].add(co)
    return grafias, ativos, co_subst, linhas


def main() -> int:
    con = conectar()
    fonte_anvisa = id_fonte(con, "ANVISA - Medicamentos registrados")
    fonte_dcb = id_fonte(con, "DCB - Denominacoes Comuns Brasileiras")

    print("Lendo DCB (IN 462)...", flush=True)
    dcb, dcb_lidas = ler_dcb()
    colapsados = sum(len(v) - 1 for v in dcb.values() if len(v) > 1)
    print("  %d denominacoes -> %d esqueletos (%d variantes de sal colapsadas)"
          % (dcb_lidas, len(dcb), colapsados))

    print("Lendo cadastro ANVISA...", flush=True)
    grafias, ativos, co_subst, linhas = ler_anvisa()
    print("  %d registros; %d esqueletos distintos; %d com produto ativo"
          % (linhas, len(grafias), len(ativos)))

    carga_a = abrir_carga(con, "ANVISA - Medicamentos registrados",
                          "20_substancias.py", ARQ_ANVISA)
    carga_d = abrir_carga(con, "DCB - Denominacoes Comuns Brasileiras",
                          "20_substancias.py", ARQ_DCB, versao="IN 462 (jul/2026)")

    inseridas = com_dcb = ambiguas = sinonimos = ident = 0
    reaproveitadas = 0
    nomes_desta_execucao = {}
    # Ancora: so entra substancia com pelo menos um produto ATIVO no Brasil
    for e in sorted(ativos):
        entradas = dcb.get(e)
        if entradas:
            base = canonico(entradas)
            nome = base["nome"]
            numero, cas = base["numero"], base["cas"]
            com_dcb += 1
        else:
            # sem DCB: usa a grafia mais frequente da ANVISA
            nome = grafias[e].most_common(1)[0][0]
            numero = cas = None

        # N5: mais de uma forma base plausivel nao e fundida em silencio
        status = "RESOLVIDA"
        if entradas and len({x["nome"].split()[-1] for x in entradas}) > 1:
            bases = {x["nome"] for x in entradas
                     if len(x["nome"].split()) == len(base["nome"].split())}
            if len(bases) > 1:
                status = "AMBIGUA"
                ambiguas += 1
                con.execute(
                    "INSERT OR IGNORE INTO resolucao_ambigua (termo_origem,"
                    "chave_normalizada,fonte_id,carga_id,candidatos,n_candidatos) "
                    "VALUES (?,?,?,?,?,?)",
                    (nome, e, fonte_dcb, carga_d,
                     json.dumps(sorted(bases), ensure_ascii=False), len(bases)))

        # Duas grafias distintas nao podem virar a mesma substancia DENTRO da
        # mesma execucao: isso seria colisao de entidade, e antes o banco a
        # recusava com IntegrityError. `inserir_unico` reaproveita a linha, o
        # que e certo entre execucoes e errado dentro de uma — por isso o
        # controle explicito abaixo.
        if nome in nomes_desta_execucao:
            raise RuntimeError(
                "colisao de entidade: os esqueletos %r e %r produzem o mesmo "
                "nome_dcb %r" % (nomes_desta_execucao[nome], e, nome))
        nomes_desta_execucao[nome] = e

        sid, novo = inserir_unico(
            con, "substancia",
            dict(nome_dcb=nome, chave_normalizada=e, dcb_numero=numero,
                 cas=cas, n_produtos_ativos=ativos[e], status_resolucao=status),
            "nome_dcb = ?", (nome,))
        if novo:
            inseridas += 1
        else:
            reaproveitadas += 1

        registrar_evidencia(con, "substancia", sid, fonte_anvisa, carga_a,
                            ARQ_ANVISA, "RESPALDADA", "CARGA_DIRETA")
        if entradas:
            registrar_evidencia(con, "substancia", sid, fonte_dcb, carga_d,
                                ARQ_DCB, "RESPALDADA", "CARGA_DIRETA")

        # sinonimos: grafias da ANVISA + variantes de sal da DCB
        vistos = {nome.lower()}
        for grafia, _ in grafias[e].most_common():
            if grafia not in vistos:
                vistos.add(grafia)
                con.execute(
                    "INSERT OR IGNORE INTO substancia_sinonimo (substancia_id,"
                    "nome,chave_normalizada,tipo) VALUES (?,?,?,?)",
                    (sid, grafia, e, "DCB_ALTERNATIVA"))
                sinonimos += 1
        for x in (entradas or []):
            if x["nome"].lower() not in vistos:
                vistos.add(x["nome"].lower())
                con.execute(
                    "INSERT OR IGNORE INTO substancia_sinonimo (substancia_id,"
                    "nome,chave_normalizada,tipo) VALUES (?,?,?,?)",
                    (sid, x["nome"], e, "DCB_ALTERNATIVA"))
                sinonimos += 1

        # identificadores (N1 e N2)
        for sistema, valor in (("DCB", numero), ("CAS", cas)):
            if valor:
                con.execute(
                    "INSERT OR IGNORE INTO substancia_identificador "
                    "(substancia_id,sistema,valor) VALUES (?,?,?)",
                    (sid, sistema, valor))
                ident += 1
        for co in sorted(co_subst.get(e, ()))[:5]:
            con.execute(
                "INSERT OR IGNORE INTO substancia_identificador "
                "(substancia_id,sistema,valor) VALUES (?,?,?)",
                (sid, "CO_SUBSTANCIA_ANVISA", co))
            ident += 1

    con.commit()
    processadas = inseridas + reaproveitadas
    fechar_carga(con, carga_a, linhas, processadas, len(grafias) - len(ativos),
                 "ignorados = esqueletos sem nenhum produto ativo")
    fechar_carga(con, carga_d, dcb_lidas, com_dcb, dcb_lidas - com_dcb,
                 "ignorados = denominacoes DCB sem produto ativo no Brasil")

    resumo("SUBSTANCIAS", [
        ("registros ANVISA lidos", linhas),
        ("denominacoes DCB lidas", dcb_lidas),
        ("substancias com produto ativo", processadas),
        ("  inseridas agora", inseridas),
        ("  ja existiam (carga incremental)", reaproveitadas),
        ("  com nomenclatura DCB oficial", "%d (%.1f%%)" %
         (com_dcb, 100 * com_dcb / max(1, processadas))),
        ("  sem DCB (nome da ANVISA)", processadas - com_dcb),
        ("  marcadas AMBIGUA para curadoria", ambiguas),
        ("sinonimos", sinonimos),
        ("identificadores externos", ident),
    ])
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
