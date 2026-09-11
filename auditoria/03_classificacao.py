# -*- coding: utf-8 -*-
"""
FASE 2 - CLASSIFICACAO DOS ARQUIVOS DO ACERVO
=============================================
Le auditoria/saida/inventario_bruto.json (fatos medidos) e atribui a cada
arquivo: categoria, papel no sistema, decisao de uso e tratamento necessario.

As regras abaixo sao decisoes de curadoria tomadas a partir do conteudo
verificado na Fase 1 -- nao do nome do arquivo. Cada regra cita o motivo.

Saidas:
  auditoria/saida/classificacao.csv   (uma linha por arquivo)
  auditoria/saida/classificacao.json  (agregados por categoria/decisao)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SAIDA = Path(r"C:\Sistema Conciliador projeto") / "auditoria" / "saida"

# ---------------------------------------------------------------------------
# Vocabulario controlado
# ---------------------------------------------------------------------------
# DECISAO: USAR | USAR_PARCIAL | APOIO | REDUNDANTE | DESCARTAR | ANALISE_MANUAL
#          SISTEMA_PRONTO (artefato ja construido) | DOCUMENTACAO | CODIGO

REGRAS = [
    # ---------------------------------------------------------------- sistema
    (r"^banco/conciliador\.db$",
     "sistema/banco construido", "SISTEMA_PRONTO",
     "Banco curado: 49 tabelas, 9 visoes, 408.997 linhas. Passa 15_validacao.py.",
     "Importar como fonte de primeira ordem; nao reconstruir do zero."),
    (r"^banco/conciliador_backup.*\.db$",
     "sistema/backup", "REDUNDANTE",
     "Backup datado anterior a uma migracao. 12 arquivos, 1,03 GB somados.",
     "Manter os 2 mais recentes; arquivar o resto fora do projeto."),
    (r"^banco/conciliador_piloto_congelado.*\.db$",
     "sistema/banco congelado", "USAR",
     "Versao congelada para o piloto de concordancia entre farmaceuticos.",
     "Preservar intacto: alterar invalida o kappa."),
    (r"^banco/schema.*\.sql$",
     "sistema/DDL", "USAR",
     "Esquema com CHECKs e FKs que sustentam as invariantes clinicas.",
     "Base do esquema canonico do projeto novo."),
    (r"^banco/etl/",
     "sistema/ETL", "USAR",
     "Pipeline numerado 10->37 que constroi o banco a partir das fontes.",
     "Portar para pipeline/ preservando a ordem."),
    (r"^banco/ml/",
     "sistema/ML", "USAR",
     "Dataset, treino, predicao, validacao externa e espaco de features.",
     "Portar para ml/; manter _features.py como fonte unica do espaco."),
    (r"^banco/app/",
     "sistema/motor+interface", "USAR",
     "Motor deterministico de 8 modulos, interface Flask e casos de avaliacao.",
     "Portar para app/; e o motor hibrido ja funcionando."),
    (r"^banco/curadoria/",
     "curadoria humana", "USAR",
     "Curadoria assinada: tabaco, referencias, gravidade, inventario.",
     "INSUBSTITUIVEL: nao e regeneravel por script. Copiar antes de tudo."),
    (r"^ml_teste/",
     "experimento de ML", "APOIO",
     "Bancada de experimentos: PU learning, familias de modelo, propagacao.",
     "Preservar como registro de metodo; nao entra em producao."),

    # ------------------------------------------------- fontes oficiais BR
    (r"^TA_CONSULTA_MEDICAMENTOS\.CSV$",
     "fonte primaria BR/registro", "USAR",
     "Cadastro ANVISA: 43.441 registros, 2.153 substancias ativas. Ancora do sistema.",
     "Recarregar com ';' e ISO-8859-1; 3.081 quebras de linha dentro de campo."),
    (r"^fontes_novas/01_anvisa_bulario/.*\.(csv|CSV)$",
     "fonte primaria BR/bula", "USAR",
     "Bulario eletronico ANVISA: manifesto e secoes extraidas de 150 bulas.",
     "TA_CONSULTA_BULA_*.CSV nao tem cabecalho: mapear colunas pelo dicionario."),
    (r"^fontes_novas/01_anvisa_bulario/pdf/",
     "fonte primaria BR/bula (PDF)", "USAR_PARCIAL",
     "150 bulas em PDF, 63 MB. Materia-prima para NLP (Fase 12).",
     "Texto ja extraido em texto/ e secoes/; PDF fica como prova de origem."),
    (r"^fontes_novas/01_anvisa_bulario/(texto|secoes)/",
     "fonte primaria BR/bula (texto)", "USAR",
     "Texto e secoes ja extraidos das 150 bulas.",
     "Entrada pronta para extracao de entidades."),
    (r"^fontes_novas/02_cmed_precos_drogaria/.*\.csv$",
     "fonte primaria BR/mercado", "USAR",
     "CMED: preco, EAN, apresentacao, CAS por produto. Base do leitor de caixa.",
     "Cabecalho real no registro 41/53: pular banner institucional."),
    (r"^fontes_novas/03_dcb_denominacoes/",
     "fonte primaria BR/nomenclatura", "USAR",
     "DCB vigente (IN 462) + chave de normalizacao com CAS e ATC.",
     "chave_substancia_br.csv e a ponte PT<->EN ja construida."),
    (r"^fontes_novas/04_rename_renisus/",
     "fonte primaria BR/politica", "USAR",
     "RENAME 2024, RENISUS e Memento Fitoterapico.",
     "RENAME_2024_digitalizado_sem_texto.pdf exige OCR: sem camada de texto."),
    (r"^fontes_novas/05_atc_classes/",
     "fonte primaria/classificacao", "USAR",
     "WHO ATC-DDD: cobre 51,2% das substancias BR ativas -- a maior cobertura.",
     "Usar como espinha dorsal de classe farmacologica."),
    (r"^fontes_novas/06_vendas_sngpc/",
     "fonte primaria BR/consumo", "APOIO",
     "SNGPC: 7,3 mi de vendas, 802 ativos. So 0,14% tem CID-10.",
     "Serve para priorizar curadoria por impacto, nao para regra clinica."),
    (r"^fontes_novas/07_complementares/VigiMed_.*\.csv$",
     "fonte primaria BR/farmacovigilancia", "USAR",
     "1.093.739 reacoes MedDRA em portugues; 94% vinculam ao medicamento. NAO USADO HOJE.",
     "Maior ativo inexplorado. Exige desproporcionalidade, nao contagem bruta."),
    (r"^fontes_novas/07_complementares/TA_RESTRICAO_MEDICAMENTO\.csv$",
     "fonte primaria BR/restricao", "USAR",
     "16.395 registros de restricao de prescricao, uso e faixa etaria.",
     "Alimenta restricao pediatrica/geriatrica, hoje ausente."),
    (r"^fontes_novas/07_complementares/DADOS_ABERTOS_MEDICAMENTOS\.csv$",
     "fonte primaria BR/registro", "APOIO",
     "43.445 produtos com classe terapeutica e principio ativo.",
     "Sobrepoe TA_CONSULTA_MEDICAMENTOS; usar para conferencia cruzada."),
    (r"^fontes_novas/07_fda_ddi/",
     "fonte primaria/regulatoria", "USAR",
     "Tabela de farmacos-indice da FDA: 31 linhas, CYP com papel e potencia.",
     "Pequena e de alto valor: define potencia de inibicao/inducao."),
    (r"^fontes_novas/08_iuphar_gtopdb/",
     "fonte primaria/alvo molecular", "USAR",
     "IUPHAR/BPS: alvo, acao e direcao. Cobre 39,3% das substancias BR.",
     "Licenca CC BY-SA: exige atribuicao. Filtrar Species=Human."),
    (r"^lista-de-medicamentos-ean-marco-2026\.pdf$",
     "fonte primaria BR/EAN", "USAR",
     "Lista de EAN da Farmacia Popular, marco/2026.",
     "Ja carregada pelo ETL 35."),

    # ------------------------------------------------ fontes internacionais
    (r"^DDInter/",
     "fonte internacional/interacao", "USAR",
     "222.383 pares graduados. 50.072 pares BRxBR -- a maior contribuicao util.",
     "Unica fonte que gradua gravidade. 47.182 vem como 'Unknown'."),
    (r"^db_drug_interactions\.csv$",
     "fonte internacional/interacao", "USAR_PARCIAL",
     "190.045 pares unicos, 43.928 BRxBR, mas NAO gradua gravidade.",
     "Usar para existencia da interacao e texto; nunca para gravidade."),
    (r"^Drug to Food interactions Dataset\.json$",
     "fonte internacional/alimento", "USAR",
     "1.423 farmacos com interacao alimentar; 600 existem no Brasil.",
     "Base do modulo 4. Citacao unica do DrugBank em todos os registros."),
    (r"^Drug to Food interactions Dataset\.xsl$",
     "fonte internacional/alimento", "REDUNDANTE",
     "Byte a byte identico ao .json homonimo, com extensao errada.",
     "Descartar: e JSON com nome .xsl."),
    (r"^DDI (2\.0|Database)\.json$",
     "compilacao secundaria/interacao", "APOIO",
     "80 e 180 registros com mecanismo redigido e alternativa segura.",
     "Referencias nao verificaveis (so nome de periodico). Nunca como evidencia."),
    (r"^Drug finder db w_o brands",
     "compilacao secundaria/monografia", "USAR_PARCIAL",
     "717 farmacos, 462 BR. Traz contraindicacao e categoria de gravidez.",
     "Colunas trocadas entre si em parte das linhas; exige revisao humana."),
    (r"^Drug-disease/drugsInfo\.csv$",
     "fonte internacional/farmacologia", "APOIO",
     "1.410 farmacos com alvo, farmacodinamica, mecanismo e SMILES.",
     "583 existem no Brasil. Mecanismo em texto livre: entrada de NLP."),
    (r"^Drug-disease/diseasesInfo\.csv$",
     "fonte internacional/doenca", "APOIO",
     "1.573 doencas MeSH com descricao e via.",
     "Sem CID-10: exige ponte MeSH->CID para uso clinico no Brasil."),
    (r"^Drug-disease/mapping\.csv$",
     "fonte internacional/doenca", "DESCARTAR",
     "42.200 pares farmaco-doenca sem dizer se e indicacao ou contraindicacao.",
     "Semantica ambigua: usar geraria alerta invertido."),
    (r"^medicine_dataset\.csv$",
     "fonte internacional/mercado indiano", "DESCARTAR",
     "85 MB, 248.218 linhas. 0% casa com substancia BR: sao marcas indianas.",
     "Classes redundantes com WHO ATC. Nao entra no banco."),

    # ---------------------------------------------------- analise e documentos
    (r"^analise_dados/scripts/",
     "codigo de analise", "USAR",
     "Inventario, cobertura e lib_norm (normalizador fonetico determinístico).",
     "lib_norm e dependencia critica de todo join PT<->EN."),
    (r"^analise_dados/saida/",
     "saida de analise", "APOIO",
     "Resultados intermediarios das analises anteriores.",
     "Regeneravel; manter como referencia historica."),
    (r"^analise_dados/.*\.md$",
     "documentacao de metodo", "DOCUMENTACAO",
     "25 documentos numerados que registram decisoes, testes e descartes.",
     "Leitura obrigatoria antes de mexer na area correspondente."),
    (r"^analise_dados/inventario\.csv$",
     "auditoria anterior", "APOIO",
     "Inventario por coluna, mas cobre apenas 19 dos 689 arquivos.",
     "Superado por auditoria/saida/inventario_bruto.json."),
    (r"^fontes_novas/.*README\.md$|^fontes_novas/COBERTURA\.md$",
     "documentacao de fonte", "DOCUMENTACAO",
     "Um README por pasta com origem, uso e ressalvas da fonte.",
     "Consultar antes de recarregar qualquer fonte."),
    (r"\.(md)$",
     "documentacao", "DOCUMENTACAO",
     "Documento de apoio do projeto.", "Preservar."),
    (r"^fontes_novas/.*\.pdf$",
     "dicionario de dados/manual", "APOIO",
     "Dicionarios de dados e manuais das fontes oficiais.",
     "Necessario para interpretar codigos das tabelas ANVISA."),
    (r"^fontes_novas/.*\.py$|^ferramentas/",
     "codigo de coleta", "USAR",
     "Scripts de download e agregacao das fontes.",
     "Guardam os cabecalhos que driblam o Cloudflare da ANVISA."),
    (r"\.(py)$",
     "codigo", "CODIGO", "Script Python do projeto.", "Avaliar caso a caso."),
    (r"\.(txt)$",
     "texto auxiliar", "APOIO", "Log, lacuna ou texto extraido.", "Preservar."),
    (r"^\.vscode/|^\.claude/|\.code-workspace$",
     "configuracao de ambiente", "DESCARTAR",
     "Configuracao do editor, sem valor de dado.",
     "Nao migrar."),
    (r"^~\$|/~\$",
     "lixo temporario", "DESCARTAR",
     "Arquivo de bloqueio do Word (~$).", "Ignorar."),
]


def classificar(rel: str):
    for padrao, categoria, decisao, motivo, tratamento in REGRAS:
        if re.search(padrao, rel):
            return categoria, decisao, motivo, tratamento
    return ("nao classificado", "ANALISE_MANUAL",
            "Nenhuma regra casou: exige leitura humana.", "Analisar manualmente.")


def main() -> int:
    inv = json.loads((SAIDA / "inventario_bruto.json").read_text(encoding="utf-8"))

    linhas = []
    por_categoria = Counter()
    por_decisao = Counter()
    bytes_por_decisao = Counter()
    exemplos = defaultdict(list)

    for a in inv["arquivos"]:
        rel = a["caminho_relativo"]
        # o lixo do Word aparece como '~$ferencial_teorico.md': tratar antes
        if a["nome"].startswith("~$"):
            cat, dec, mot, trat = ("lixo temporario", "DESCARTAR",
                                   "Arquivo de bloqueio do Word (~$).", "Ignorar.")
        else:
            cat, dec, mot, trat = classificar(rel)
        an = a.get("analise", {})
        linhas.append({
            "caminho": rel,
            "categoria": cat,
            "decisao": dec,
            "motivo": mot,
            "tratamento": trat,
            "formato": an.get("formato", ""),
            "bytes": a.get("tamanho_bytes", 0),
            "tamanho": a.get("tamanho_legivel", ""),
            "registros": an.get("n_linhas_dados") or an.get("n_registros")
                         or an.get("total_linhas") or an.get("n_paginas") or "",
            "colunas": an.get("n_colunas", ""),
            "encoding": an.get("encoding_usado", ""),
            "delimitador": an.get("delimitador", ""),
            "idioma": an.get("idioma", ""),
            "modificado": a.get("modificado", ""),
        })
        por_categoria[cat] += 1
        por_decisao[dec] += 1
        bytes_por_decisao[dec] += a.get("tamanho_bytes", 0)
        if len(exemplos[dec]) < 6:
            exemplos[dec].append(rel)

    destino_csv = SAIDA / "classificacao.csv"
    with open(destino_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(sorted(linhas, key=lambda x: (x["decisao"], x["caminho"])))

    resumo = {
        "n_arquivos": len(linhas),
        "por_decisao": [{"decisao": d, "arquivos": n,
                         "bytes": bytes_por_decisao[d],
                         "MB": round(bytes_por_decisao[d] / 1048576, 1),
                         "exemplos": exemplos[d]}
                        for d, n in por_decisao.most_common()],
        "por_categoria": dict(por_categoria.most_common()),
    }
    (SAIDA / "classificacao.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")

    print("Classificados: %d arquivos -> %s" % (len(linhas), destino_csv))
    print()
    print("%-16s %7s %11s" % ("DECISAO", "ARQUIVOS", "TAMANHO"))
    for d, n in por_decisao.most_common():
        print("%-16s %7d %10.1f MB" % (d, n, bytes_por_decisao[d] / 1048576))
    nao = por_decisao.get("ANALISE_MANUAL", 0)
    print("\nSem regra (exigem leitura humana): %d" % nao)
    if nao:
        for l in linhas:
            if l["decisao"] == "ANALISE_MANUAL":
                print("   ", l["caminho"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
