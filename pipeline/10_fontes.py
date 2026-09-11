# -*- coding: utf-8 -*-
"""
Cria o banco e registra as fontes.

Roda primeiro: nenhuma afirmacao pode entrar sem fonte_id, entao o catalogo
de fontes precede toda carga.

A confiabilidade abaixo e a da FONTE (procedencia editorial), medida na
auditoria -- nao e nivel de evidencia da afirmacao nem confianca de modelo.

Uso: python pipeline/10_fontes.py [--recriar]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import conectar, resumo  # noqa: E402

# nome, tipo, url, licenca, confiabilidade, observacao
FONTES = [
    ("ANVISA - Medicamentos registrados", "REGULATORIA",
     "https://dados.anvisa.gov.br", "Dados abertos", "ALTA",
     "Cadastro oficial. Ancora de identidade das substancias brasileiras."),
    ("ANVISA - Bulario eletronico", "BULA",
     "https://consultas.anvisa.gov.br/#/bulario/", "Dados abertos", "ALTA",
     "150 bulas baixadas. Fonte regulatoria em portugues."),
    ("CMED - Lista de precos", "REGULATORIA",
     "https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed", "Dados abertos", "ALTA",
     "Preco, EAN, apresentacao e CAS por produto. Cabecalho no registro 41."),
    ("ANVISA - Dados abertos de medicamentos", "REGULATORIA",
     "https://dados.anvisa.gov.br", "Dados abertos", "ALTA",
     "Classe terapeutica e principio ativo por produto. Confere com o cadastro."),
    ("DCB - Denominacoes Comuns Brasileiras", "REGULATORIA",
     "https://www.gov.br/anvisa", "Dados abertos", "ALTA",
     "IN 462 vigente. Nomenclatura oficial + chave de normalizacao."),
    ("WHO - ATC/DDD", "BASE_CIENTIFICA",
     "https://atcddd.fhi.no/", "Uso academico", "ALTA",
     "Classificacao anatomo-terapeutica. Cobre 51,2% das substancias BR ativas."),
    ("DDInter", "BASE_CIENTIFICA",
     "http://ddinter.scbdd.com/", "CC BY-NC-SA", "ALTA",
     "Unica fonte do acervo que gradua gravidade. 47.182 pares vem como Unknown."),
    ("db_drug_interactions", "COMPILACAO",
     None, "nao declarada", "MEDIA",
     "190.045 pares, texto mecanistico. NAO gradua gravidade; nunca usar para isso."),
    ("DrugBank - interacoes com alimento", "BASE_CIENTIFICA",
     "https://go.drugbank.com/", "Restricao de uso comercial", "MEDIA",
     "Citacao unica para 1.423 registros. Diretivas de administracao uteis."),
    ("IUPHAR/BPS - Guide to Pharmacology", "BASE_CIENTIFICA",
     "https://www.guidetopharmacology.org/", "CC BY-SA (exige atribuicao)", "ALTA",
     "Alvo molecular, acao e direcao. Cobre 39,3% das substancias BR."),
    ("FDA - Tabela de farmacos-indice de interacao", "REGULATORIA",
     "https://www.fda.gov/", "Dominio publico", "ALTA",
     "31 linhas com papel e potencia de CYP. Pequena e de alto valor."),
    ("VigiMed - Farmacovigilancia ANVISA", "GOVERNAMENTAL",
     "https://www.gov.br/anvisa", "Dados abertos", "ALTA",
     "1.093.739 reacoes MedDRA em portugues. Notificacao espontanea: "
     "exige desproporcionalidade, NUNCA contagem bruta como incidencia."),
    ("RENAME 2024", "GOVERNAMENTAL",
     "https://www.gov.br/saude", "Dados abertos", "ALTA",
     "Relacao nacional de medicamentos essenciais."),
    ("RENISUS / Memento Fitoterapico", "GOVERNAMENTAL",
     "https://www.gov.br/saude", "Dados abertos", "ALTA",
     "Plantas medicinais de interesse do SUS."),
    ("SNGPC - Vendas", "GOVERNAMENTAL",
     "https://dados.anvisa.gov.br", "Dados abertos", "ALTA",
     "Prioriza curadoria por impacto real de balcao. Nao gera regra clinica."),
    ("ANVISA - Restricoes de medicamento", "REGULATORIA",
     "https://dados.anvisa.gov.br", "Dados abertos", "ALTA",
     "16.395 registros de restricao de prescricao, uso e faixa etaria."),
    ("Curadoria farmaceutica", "CURADORIA",
     None, None, "ALTA",
     "Curadoria humana assinada, incorporada do acervo. Nao regeneravel "
     "por script: e o unico conteudo que nenhuma fonte contem."),
    ("Compilacao DDI (DDI 2.0 / DDI Database)", "COMPILACAO",
     None, "nao declarada", "BAIXA",
     "Referencias nao verificaveis (so nome de periodico). Apoio para redacao "
     "de mecanismo; NUNCA evidencia primaria. Ver DECISIONS.md D-006."),
    ("Drug finder (compilacao)", "COMPILACAO",
     None, "nao declarada", "BAIXA",
     "Contraindicacao e categoria de gravidez que nenhuma outra fonte tem, "
     "com colunas trocadas entre si. Exige revisao humana linha a linha."),
]


def main() -> int:
    recriar = "--recriar" in sys.argv
    con = conectar(criar=recriar)
    inseridas, existentes = 0, 0
    for nome, tipo, url, licenca, conf, obs in FONTES:
        ja = con.execute("SELECT 1 FROM fonte WHERE nome=?", (nome,)).fetchone()
        if ja:
            existentes += 1
            continue
        con.execute(
            "INSERT INTO fonte (nome,tipo,url,licenca,confiabilidade,observacao) "
            "VALUES (?,?,?,?,?,?)", (nome, tipo, url, licenca, conf, obs))
        inseridas += 1
    con.commit()

    total = con.execute("SELECT COUNT(*) FROM fonte").fetchone()[0]
    por_tipo = con.execute(
        "SELECT tipo, COUNT(*) FROM fonte GROUP BY tipo ORDER BY 2 DESC").fetchall()
    resumo("FONTES", [("inseridas agora", inseridas),
                      ("ja existentes", existentes),
                      ("total no banco", total)])
    for t, n in por_tipo:
        print("  %-44s %d" % (t, n))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
