# -*- coding: utf-8 -*-
"""
VERSAO DO PRODUTO — e das quatro coisas que versionam separadamente.

Nao ha uma versao so. Um sistema que apoia decisao clinica precisa saber
responder, para qualquer alerta que ja mostrou, sobre QUAL conhecimento e
QUAL modelo ele foi produzido. Por isso quatro numeros independentes:

    APLICACAO    o codigo: motores, servicos, telas
    ESQUEMA      a estrutura das tabelas
    CONHECIMENTO o conteudo: substancias, interacoes, regras, evidencias
                 (lido do banco, nao escrito aqui — e a impressao digital)
    MODELO       o artefato de ML, mesmo inativo

A aplicacao pode subir de versao sem que o conhecimento mude, e o
conhecimento pode ser atualizado sem trocar o `.exe`. Amarrar os dois num
numero so obrigaria a redistribuir o programa inteiro para corrigir uma
interacao — e e justamente isso que a Fase 10 quer evitar.

`DATA_BUILD` fica vazia em desenvolvimento e e preenchida pelo empacotador.
"""
from __future__ import annotations

# 1.0.0 porque o produto esta completo e validado como sistema (Fase 9), NAO
# porque esteja clinicamente validado — nao esta, e a interface diz isso.
APLICACAO = "1.0.0"

# Sobe quando `database/schema.sql` muda de forma que exija migracao.
ESQUEMA = "1.0"

NOME = "Conciliador de Medicamentos"
DESCRICAO = "Apoio à conciliação medicamentosa no balcão"
INSTITUICAO = "TCC de Farmácia — Centro Universitário Fametro"

# Preenchida por `scripts/build_exe.py`. Vazia = rodando do codigo-fonte.
DATA_BUILD = ""

# O que a interface tem de dizer, sempre, em qualquer versao.
LIMITACAO_CLINICA = (
    "Este sistema apoia a conciliação medicamentosa; não a substitui. "
    "Nenhum achado foi revisado por farmacêutico, nenhum modelo preditivo "
    "está homologado, e a decisão clínica permanece do profissional."
)


def completa() -> str:
    return "%s %s%s" % (NOME, APLICACAO,
                        (" (build %s)" % DATA_BUILD) if DATA_BUILD else
                        " (código-fonte)")


def dicionario(con=None) -> dict:
    """As quatro versoes. `con` aberto acrescenta as que vivem no banco."""
    d = {"aplicacao": APLICACAO, "esquema": ESQUEMA,
         "data_build": DATA_BUILD or None, "nome": NOME}
    if con is None:
        return d
    try:
        d["conhecimento"] = con.execute(
            "SELECT valor FROM propriedade WHERE chave='conhecimento.versao'"
        ).fetchone()[0]
    except Exception:                                       # noqa: BLE001
        d["conhecimento"] = None
    try:
        d["conhecimento_digital"] = con.execute(
            "SELECT valor FROM propriedade WHERE chave='conhecimento.digital'"
        ).fetchone()[0]
    except Exception:                                       # noqa: BLE001
        d["conhecimento_digital"] = None
    try:
        linhas = con.execute(
            "SELECT nome, versao, status, ativo FROM modelo ORDER BY id"
        ).fetchall()
        d["modelos"] = [{"nome": n, "versao": v, "status": s, "ativo": a}
                        for n, v, s, a in linhas]
        d["modelo_ativo"] = next((m for m in d["modelos"] if m["ativo"]), None)
    except Exception:                                       # noqa: BLE001
        d["modelos"], d["modelo_ativo"] = [], None
    return d


if __name__ == "__main__":
    print(completa())
    for k, v in dicionario().items():
        print("  %-14s %s" % (k, v))
