# -*- coding: utf-8 -*-
"""
Carga de produtos, apresentacoes e codigos de barras.

FONTE: CMED (lista de precos). Escolhida em vez do cadastro ANVISA porque
so ela traz, na mesma linha, GGREM + EAN + apresentacao + tarja -- e a
tarja da CMED vem ROTULADA ('Tarja Vermelha'), nao como codigo numerico.
O sistema anterior mapeou o codigo numerico da ANVISA ao contrario e
chegou a afirmar que tramadol era venda livre; ler o rotulo elimina essa
classe de erro inteira.

Vinculo com substancia: campo SUBSTANCIA da CMED, separado por ';'
(diferente da ANVISA, que usa ','), reduzido ao esqueleto fonetico.

Uso: python pipeline/30_produtos.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (abrir_carga, campo, conectar, fechar_carga,  # noqa: E402
                    id_fonte, ler_csv, registrar_evidencia, resumo)
from _substancia_texto import dividir  # noqa: E402
from normalizacao import skeleton  # noqa: E402

ARQ = "fontes_novas/02_cmed_precos_drogaria/TA_PRECO_MEDICAMENTO.csv"

# A CMED rotula a tarja por extenso. Mapa direto, sem codigo numerico.
TARJA = {
    "Tarja Sem Tarja": "MIP",
    "Tarja Vermelha": "TARJA_VERMELHA",
    "Tarja Vermelha sob restrição": "TARJA_VERMELHA_RETENCAO",
    "Tarja Preta": "TARJA_PRETA",
    "- (*)": "NAO_DETERMINADO",
}

# A apresentacao comeca pela concentracao: '500 MG COM CT BL...',
# '125 MG/ML SOL INJ...'. So aceitamos quando ha UM valor no inicio; se a
# apresentacao lista varias concentracoes (associacao em dose fixa,
# '10 MG/G + 0,443 MG/G'), a concentracao da apresentacao e ambigua e fica
# NULL -- a informacao correta esta por componente, que esta fonte nao da.
RE_CONC = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(MG/ML|MCG/ML|G/ML|MG/G|UI/ML|MG|MCG|G|ML|UI|%)\b",
    re.I)
# Segunda concentracao depois de um '+': a apresentacao lista mais de um
# ativo e a concentracao no nivel da apresentacao passa a ser ambigua.
# Nao basta olhar logo apos a unidade: '25 MG/0,5ML + 5 MG/0,5ML' tem
# digito DENTRO da unidade, e 86 apresentacoes escapavam por isso.
# Cuidado: '+ SERINGA', '+ COPO', '+ COL' sao dispositivo, nao concentracao.
RE_SEGUNDA_CONC = re.compile(
    r"\+\s*\d+(?:[.,]\d+)?\s*(?:MG|MCG|G|ML|UI|%)", re.I)

# EAN valido: so digitos, comprimento de padrao GS1
RE_EAN = re.compile(r"^\d{8}$|^\d{12,14}$")


def registro_do_produto(registro: str) -> str:
    """Registro no nivel do PRODUTO, nao da apresentacao.

    O numero da CMED tem 13 digitos e os ultimos identificam a
    apresentacao: ORENCIA aparece como 1018003900019 e 1018003900078.
    Usar o numero inteiro criava um produto por apresentacao (25.701
    produtos para 25.702 apresentacoes). Os 9 primeiros digitos sao o
    registro do produto.
    """
    d = re.sub(r"\D", "", registro or "")
    return d[:9] if len(d) >= 9 else (d or "")


def esq(nome: str) -> str:
    if not nome:
        return ""
    s = skeleton(nome)
    return s if s and len(s) >= 3 else ""


def extrair_concentracao(texto: str):
    """(valor, unidade) ou (None, None) quando a fonte nao permite afirmar."""
    if not texto or RE_SEGUNDA_CONC.search(texto):
        return None, None
    m = RE_CONC.match(texto)
    if not m:
        return None, None
    try:
        valor = float(m.group(1).replace(",", "."))
    except ValueError:
        return None, None
    return valor, m.group(2).upper()


def main() -> int:
    con = conectar()
    fonte = "CMED - Lista de precos"
    fid = id_fonte(con, fonte)
    carga = abrir_carga(con, fonte, "30_produtos.py", ARQ, versao="21/07/2026")

    # indice esqueleto -> substancia_id (inclui sinonimos)
    indice = {}
    for sid, chave in con.execute(
            "SELECT id, chave_normalizada FROM substancia"):
        indice.setdefault(chave, sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        indice.setdefault(chave, sid)
    print("indice de substancias: %d esqueletos" % len(indice))

    produtos = {}          # (registro, nome) -> id
    n_apres = n_ean = n_vinc = 0
    lidos = ignorados = 0
    sem_substancia = Counter()
    tarja_por_subst = defaultdict(Counter)
    ean_invalido = 0
    conc_ok = 0

    for idx, l in ler_csv(ARQ):
        lidos += 1
        ggrem = campo(idx, l, "CÓDIGO GGREM")
        nome_prod = campo(idx, l, "PRODUTO")
        if not ggrem or not nome_prod:
            ignorados += 1
            continue

        registro = campo(idx, l, "REGISTRO")
        registro_prod = registro_do_produto(registro)
        chave_prod = (registro_prod, nome_prod)
        pid = produtos.get(chave_prod)
        if pid is None:
            cur = con.execute(
                "INSERT OR IGNORE INTO produto (registro_anvisa,nome_comercial,"
                "empresa,cnpj,categoria,situacao) VALUES (?,?,?,?,?,'ATIVO')",
                (registro_prod or None, nome_prod, campo(idx, l, "LABORATÓRIO") or None,
                 campo(idx, l, "CNPJ") or None,
                 campo(idx, l, "TIPO DE PRODUTO (STATUS DO PRODUTO)") or None))
            if cur.lastrowid and cur.rowcount:
                pid = cur.lastrowid
            else:
                pid = con.execute(
                    "SELECT id FROM produto WHERE registro_anvisa IS ? "
                    "AND nome_comercial = ?", (registro_prod or None, nome_prod)
                ).fetchone()[0]
            produtos[chave_prod] = pid
            registrar_evidencia(con, "produto", pid, fid, carga, ARQ,
                                "RESPALDADA", "CARGA_DIRETA")

        descricao = campo(idx, l, "APRESENTAÇÃO") or nome_prod
        valor, unidade = extrair_concentracao(descricao)
        if valor is not None:
            conc_ok += 1
        cur = con.execute(
            "INSERT OR IGNORE INTO apresentacao (produto_id,codigo_ggrem,descricao,"
            "concentracao_valor,concentracao_unidade) VALUES (?,?,?,?,?)",
            (pid, ggrem, descricao, valor, unidade))
        if not cur.rowcount:
            ignorados += 1
            continue
        aid = cur.lastrowid
        n_apres += 1
        registrar_evidencia(con, "apresentacao", aid, fid, carga, ARQ,
                            "RESPALDADA", "CARGA_DIRETA")

        # ate tres codigos de barras por apresentacao
        for ordem, coluna in enumerate(("EAN 1", "EAN 2", "EAN 3"), start=1):
            ean = campo(idx, l, coluna)
            if not ean:
                continue
            if not RE_EAN.match(ean):
                ean_invalido += 1
                continue
            r = con.execute(
                "INSERT OR IGNORE INTO apresentacao_ean (apresentacao_id,ean,ordem) "
                "VALUES (?,?,?)", (aid, ean, ordem))
            n_ean += r.rowcount

        # vinculo com substancia: CMED separa associacao por ';'
        bruto = campo(idx, l, "SUBSTÂNCIA")
        tarja = TARJA.get(campo(idx, l, "TARJA"), "NAO_DETERMINADO")
        # ';' e o separador da CMED (a ANVISA usa ','), mas 'vacina
        # influenza (fragmentada, inativada)' tem virgula DENTRO do
        # parenteses: dividir cru gerava fragmentos como 'subunitaria)'.
        for parte in dividir(bruto.replace(";", ",")):
            if len(parte) < 3:
                continue
            e = esq(parte)
            sid = indice.get(e)
            if sid is None:
                sem_substancia[parte.lower()] += 1
                continue
            r = con.execute(
                "INSERT OR IGNORE INTO apresentacao_substancia "
                "(apresentacao_id,substancia_id) VALUES (?,?)", (aid, sid))
            n_vinc += r.rowcount
            if tarja != "NAO_DETERMINADO":
                tarja_por_subst[sid][tarja] += 1

    # canal de dispensacao: a tarja mais frequente entre as apresentacoes
    # da substancia. Empate ou ausencia -> NAO_DETERMINADO, nunca chute.
    n_canal = 0
    for sid, contagem in tarja_por_subst.items():
        mais = contagem.most_common()
        if len(mais) > 1 and mais[0][1] == mais[1][1]:
            continue
        con.execute("UPDATE substancia SET canal_dispensacao=? WHERE id=?",
                    (mais[0][0], sid))
        n_canal += 1

    con.commit()
    fechar_carga(con, carga, lidos, n_apres, ignorados,
                 "ignorados = linhas sem GGREM/produto ou GGREM repetido")

    resumo("PRODUTOS E APRESENTACOES", [
        ("linhas CMED lidas", lidos),
        ("produtos", len(produtos)),
        ("apresentacoes", n_apres),
        ("  com concentracao estruturada", "%d (%.1f%%)" %
         (conc_ok, 100 * conc_ok / max(1, n_apres))),
        ("codigos de barras", n_ean),
        ("  EAN recusados por formato", ean_invalido),
        ("vinculos apresentacao-substancia", n_vinc),
        ("substancias com canal de dispensacao", n_canal),
        ("strings de substancia sem correspondencia", len(sem_substancia)),
    ])
    if sem_substancia:
        print("\n  10 mais frequentes sem correspondencia:")
        for nome, n in sem_substancia.most_common(10):
            print("    %-52s %d" % (nome[:52], n))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
