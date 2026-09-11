# -*- coding: utf-8 -*-
"""
Testa o esquema canonico: cria o banco em memoria e verifica que as
invariantes estruturais REJEITAM o que precisam rejeitar.

Um CHECK que nunca foi testado e uma suposicao, nao uma garantia.

Cobre as 8 invariantes originais e os 9 problemas achados na revisao
pre-carga (docs/REVISAO_SCHEMA.md).

Uso:  python tests/teste_schema.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA = RAIZ / "database" / "schema.sql"

COLS_ACHADO = ("conciliacao_id,modulo,subtipo,prioridade,classificacao,natureza,titulo,item_a,explicacao,origem_afirmacao,confianca_sistema,confianca_extracao,status_informacao,metodo_deteccao,justificativa_prioridade,grupo_chave")
VALS_ACHADO = ("1,'FARMACO_FARMACO','INTERACAO_DOCUMENTADA','ALTO','CONFIRMADO','DOCUMENTADO','x','a','e','i.1','MEDIA','CARGA_DIRETA','DOCUMENTADO','TESTE','porque sim','G:1'")

falhas = []


def conectar():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys = ON")
    return con


def deve_recusar(con, descricao, sql, params=()):
    try:
        con.execute(sql, params)
        con.commit()
    except sqlite3.Error as e:
        print("  [OK ] recusou (%s): %s" % (type(e).__name__, descricao))
        return
    print("  [FALHA] ACEITOU o que deveria recusar: %s" % descricao)
    falhas.append(descricao)


def deve_aceitar(con, descricao, sql, params=()):
    try:
        con.execute(sql, params)
        con.commit()
        print("  [OK ] aceitou: %s" % descricao)
    except sqlite3.Error as e:
        print("  [FALHA] recusou o que deveria aceitar: %s -> %s" % (descricao, e))
        falhas.append(descricao)


def confere(descricao, condicao, detalhe=""):
    if condicao:
        print("  [OK ] %s %s" % (descricao, detalhe))
    else:
        print("  [FALHA] %s %s" % (descricao, detalhe))
        falhas.append(descricao)


def semear(con):
    con.execute("INSERT INTO fonte (id,nome,tipo,confiabilidade) "
                "VALUES (1,'DDInter','BASE_CIENTIFICA','ALTA')")
    con.execute("INSERT INTO fonte (id,nome,tipo,confiabilidade) "
                "VALUES (2,'db_drug_interactions','COMPILACAO','MEDIA')")
    con.execute("INSERT INTO carga (id,fonte_id,script,documento_origem,registros_lidos) "
                "VALUES (1,1,'teste','ddinter_A.csv',10)")
    for i, nome in ((1, 'varfarina'), (2, 'omeprazol'), (3, 'levotiroxina')):
        con.execute("INSERT INTO substancia (id,nome_dcb,chave_normalizada) "
                    "VALUES (?,?,?)", (i, nome, nome))
    con.execute("INSERT INTO item_nao_medicamentoso (id,nome,chave_normalizada,tipo) "
                "VALUES (1,'carbonato de cálcio','calcio','MINERAL')")
    con.execute("INSERT INTO paciente (id,nome) VALUES (1,'Teste')")
    con.execute("INSERT INTO atendimento (id,paciente_id,codigo) VALUES (1,1,'AT-001')")
    con.execute("INSERT INTO atendimento_medicamento "
                "(id,atendimento_id,substancia_id,nome_relatado,origem,reconhecimento) "
                "VALUES (1,1,3,'Puran T4','PRESCRITO','NOME_EXATO')")
    con.execute("INSERT INTO conciliacao (id,atendimento_id,versao_motor,n_medicamentos) "
                "VALUES (1,1,'1.0',1)")
    con.execute("INSERT INTO modelo (id,nome,versao,problema,algoritmo,n_features,"
                "protocolo_validacao,metricas_json,treinado_em,semente,"
                "versao_dados,espaco_features_json,limitacoes) "
                "VALUES (1,'existencia','1.0','existe interacao?','LR',10,"
                "'split por farmaco','{}','2026-09-09',1,'abc','[]','teste')")
    con.execute("INSERT INTO produto (id,nome_comercial,situacao) "
                "VALUES (1,'TESTE','ATIVO')")
    con.commit()


def main() -> int:
    print("ESQUEMA — criação")
    con = conectar()
    n = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    v = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='view'").fetchone()[0]
    print("  %d tabelas, %d views criadas" % (n, v))
    semear(con)

    print("\nINVARIANTE 1 — ML nunca atribui gravidade")
    deve_recusar(con, "predição com gravidade_sugerida preenchida",
                 "INSERT INTO predicao (modelo_id,substancia_a_id,substancia_b_id,"
                 "probabilidade,gravidade_sugerida) VALUES (1,1,2,0.9,'MAIOR')")
    deve_aceitar(con, "predição com gravidade_sugerida NULL",
                 "INSERT INTO predicao (modelo_id,substancia_a_id,substancia_b_id,"
                 "probabilidade) VALUES (1,1,2,0.9)")

    print("\nINVARIANTE 2 — previsão não se disfarça de fato")
    deve_recusar(con, "achado PREVISTO sem probabilidade do modelo",
                 "INSERT INTO achado (conciliacao_id,modulo,prioridade,natureza,"
                 "titulo,item_a,explicacao,origem_afirmacao) "
                 "VALUES (1,'FARMACO_FARMACO','ALTO','PREVISTO','x','a','e','predicao.1')")
    deve_recusar(con, "achado DOCUMENTADO sem nível de evidência",
                 "INSERT INTO achado (%s) VALUES (%s)" % (COLS_ACHADO,
                                                          VALS_ACHADO))
    deve_aceitar(con, "achado DOCUMENTADO com evidência",
                 "INSERT INTO achado (%s,nivel_evidencia) VALUES (%s,"
                 "'RESPALDADA')" % (COLS_ACHADO, VALS_ACHADO))

    print()
    print("INVARIANTE 2b — os eixos do achado não se disfarçam (Fase 5)")
    deve_recusar(con, "natureza PREVISTO com status que diz outra coisa",
                 "INSERT INTO achado (%s,probabilidade_modelo,origem_achado) "
                 "VALUES (%s,0.8,'MODELO')" % (
                     COLS_ACHADO.replace("'DOCUMENTADO','x'", "'PREVISTO','x'"),
                     VALS_ACHADO.replace("'DOCUMENTADO','x','a'",
                                         "'PREVISTO','x','a'")))
    deve_recusar(con, "achado de REGRA carregando probabilidade de modelo",
                 "INSERT INTO achado (%s,nivel_evidencia,probabilidade_modelo) "
                 "VALUES (%s,'RESPALDADA',0.9)" % (COLS_ACHADO, VALS_ACHADO))
    deve_recusar(con, "achado se dizendo REVISADO sem extração revisada",
                 "INSERT INTO achado (%s,nivel_evidencia) VALUES (%s,"
                 "'RESPALDADA')" % (
                     COLS_ACHADO,
                     VALS_ACHADO.replace("'CARGA_DIRETA','DOCUMENTADO'",
                                         "'CARGA_DIRETA','REVISADO'")))
    deve_recusar(con, "conflito declarado sem natureza conflitante",
                 "INSERT INTO achado (%s,nivel_evidencia,conflito_tipo) "
                 "VALUES (%s,'RESPALDADA','GRAVIDADE')" % (COLS_ACHADO,
                                                           VALS_ACHADO))
    deve_recusar(con, "achado agrupado sem apontar o representante",
                 "INSERT INTO achado (%s,nivel_evidencia,status) VALUES (%s,"
                 "'RESPALDADA','AGRUPADO')" % (COLS_ACHADO, VALS_ACHADO))

    print()
    print("INVARIANTE 2d — previsão é rastreável até o modelo (Fase 7)")
    prev = (COLS_ACHADO.replace("'DOCUMENTADO','x'", "'PREVISTO','x'"),
            VALS_ACHADO.replace("'DOCUMENTADO','x','a'", "'PREVISTO','x','a'")
                       .replace("'CARGA_DIRETA','DOCUMENTADO'",
                                "'CALCULADO','PREVISTO'"))
    deve_recusar(con, "achado PREVISTO apontando para uma regra, não para a previsão",
                 "INSERT INTO achado (%s,probabilidade_modelo,origem_achado) "
                 "VALUES (%s,0.8,'MODELO')" % prev)
    ok = (prev[0], prev[1].replace("'i.1'", "'predicao.1'"))
    deve_aceitar(con, "achado PREVISTO apontando para predicao.1",
                 "INSERT INTO achado (%s,probabilidade_modelo,origem_achado) "
                 "VALUES (%s,0.8,'MODELO')" % ok)
    deve_recusar(con, "achado PREVISTO com nível de evidência de publicação",
                 "INSERT INTO achado (%s,probabilidade_modelo,origem_achado,"
                 "nivel_evidencia) VALUES (%s,0.8,'MODELO','RESPALDADA')" % ok)
    deve_recusar(con, "achado de MODELO com natureza que não é previsão",
                 "INSERT INTO achado (%s,probabilidade_modelo,origem_achado,"
                 "nivel_evidencia) VALUES (%s,0.8,'MODELO','RESPALDADA')"
                 % (COLS_ACHADO, VALS_ACHADO.replace("'i.1'", "'predicao.1'")))

    print()
    print("INVARIANTE 2e — modelo não é trocado em silêncio (Fase 7)")
    base = ("INSERT INTO modelo (nome,versao,problema,algoritmo,n_features,"
            "protocolo_validacao,metricas_json,treinado_em,semente,"
            "versao_dados,espaco_features_json,limitacoes,status,ativo) VALUES "
            "('existencia','%s','existe interacao?','LR',10,'split por farmaco',"
            "'{}','2026-09-09',1,'abc','[]','teste','%s',%d)")
    deve_recusar(con, "modelo ativo sem estar homologado",
                 base % ("2.0", "EXPERIMENTAL", 1))
    deve_aceitar(con, "modelo homologado e ativo", base % ("2.0", "HOMOLOGADO", 1))
    deve_recusar(con, "segundo modelo ativo para o mesmo problema",
                 base % ("3.0", "HOMOLOGADO", 1))
    deve_aceitar(con, "segundo modelo, inativo", base % ("3.0", "HOMOLOGADO", 0))
    deve_recusar(con, "previsão revisada sem quem revisou",
                 "INSERT INTO predicao (modelo_id,substancia_a_id,substancia_b_id,"
                 "probabilidade,status) VALUES (1,1,3,0.9,'REVISADA_ACEITA')")

    print()
    print("INVARIANTE 2c — o sistema não decide intencionalidade")
    deve_recusar(con, "divergência classificada como erro sem assinatura",
                 "INSERT INTO conciliacao_par (conciliacao_id,item_relatado_id,"
                 "nome_exibicao,situacao,tipo_divergencia,intencionalidade) "
                 "VALUES (1,NULL,'x','DIVERGENCIA','SO_NO_RELATO',"
                 "'NAO_INTENCIONAL')")
    deve_recusar(con, "par de conciliação sem nenhum dos dois lados",
                 "INSERT INTO conciliacao_par (conciliacao_id,nome_exibicao,"
                 "situacao,tipo_divergencia) "
                 "VALUES (1,'x','DIVERGENCIA','SO_NO_RELATO')")
    deve_aceitar(con, "divergência com intencionalidade não determinada",
                 "INSERT INTO conciliacao_par (conciliacao_id,item_relatado_id,"
                 "nome_exibicao,situacao,tipo_divergencia) "
                 "VALUES (1,1,'x','DIVERGENCIA','SO_NO_RELATO')")
    deve_recusar(con, "par conciliado com tipo de divergência",
                 "INSERT INTO conciliacao_par (conciliacao_id,item_relatado_id,"
                 "nome_exibicao,situacao,tipo_divergencia) "
                 "VALUES (1,NULL,'x','CONCILIADO','SO_NO_RELATO')")

    print("\nINVARIANTE 3 — intervalo não estabelecido é NULL, não número inventado")
    deve_aceitar(con, "regra_separacao sem intervalo (fonte não publica)",
                 "INSERT INTO regra_separacao (substancia_id,alvo_tipo,alvo_item_id,"
                 "motivo,origem,fonte_id) VALUES (3,'ITEM',1,'quelação',"
                 "'FONTE_EXTERNA',1)")
    deve_recusar(con, "intervalo absurdo (48 h)",
                 "INSERT INTO regra_separacao (substancia_id,alvo_tipo,"
                 "alvo_substancia_id,intervalo_horas,motivo,origem,fonte_id) "
                 "VALUES (3,'SUBSTANCIA',1,48,'x','CURADORIA',1)")
    deve_recusar(con, "alvo_tipo ITEM apontando para substância",
                 "INSERT INTO regra_separacao (substancia_id,alvo_tipo,"
                 "alvo_substancia_id,motivo,origem,fonte_id) "
                 "VALUES (3,'ITEM',1,'x','CURADORIA',1)")

    print("\nINVARIANTE 4 — par ordenado, sem A-B e B-A duplicados")
    deve_recusar(con, "interação com a_id > b_id",
                 "INSERT INTO interacao_substancia (substancia_a_id,substancia_b_id,"
                 "tipo,gravidade,origem,fonte_id) VALUES (2,1,'FARMACOCINETICA',"
                 "'MAIOR','FONTE_EXTERNA',1)")
    deve_aceitar(con, "interação com a_id < b_id",
                 "INSERT INTO interacao_substancia (substancia_a_id,substancia_b_id,"
                 "tipo,gravidade,origem,fonte_id) VALUES (1,2,'FARMACOCINETICA',"
                 "'MAIOR','FONTE_EXTERNA',1)")

    print("\nINVARIANTE 5 — horário é hora válida, não texto livre")
    deve_aceitar(con, "posologia estruturada",
                 "INSERT INTO posologia (id,atendimento_medicamento_id,dose_valor,"
                 "dose_unidade,vezes_por_dia,uso_continuo) VALUES (1,1,50,'mcg',1,1)")
    deve_recusar(con, "horário 'de manhã'",
                 "INSERT INTO horario_administracao (posologia_id,hora,definido_por) "
                 "VALUES (1,'de manhã','PACIENTE')")
    deve_aceitar(con, "horário 06:30",
                 "INSERT INTO horario_administracao (posologia_id,hora,definido_por) "
                 "VALUES (1,'06:30','PACIENTE')")

    print("\nINVARIANTE 6 — uso contínuo não tem data de término prevista")
    deve_recusar(con, "uso contínuo com data de término",
                 "INSERT INTO posologia (atendimento_medicamento_id,uso_continuo,"
                 "data_fim_prevista) VALUES (1,1,'2026-12-01')")

    print("\nP-01 — duas fontes podem afirmar o mesmo par (e o conflito aparece)")
    deve_aceitar(con, "mesmo par, segunda fonte",
                 "INSERT INTO interacao_substancia (substancia_a_id,substancia_b_id,"
                 "tipo,gravidade,origem,fonte_id) VALUES (1,2,'FARMACOCINETICA',"
                 "'MODERADA','FONTE_EXTERNA',2)")
    deve_recusar(con, "mesmo par, mesma fonte, duas vezes",
                 "INSERT INTO interacao_substancia (substancia_a_id,substancia_b_id,"
                 "tipo,gravidade,origem,fonte_id) VALUES (1,2,'FARMACODINAMICA',"
                 "'MENOR','FONTE_EXTERNA',2)")
    conf = con.execute("SELECT fonte_a,gravidade_a,fonte_b,gravidade_b "
                       "FROM vw_conflito_gravidade").fetchall()
    confere("conflito de gravidade detectado", len(conf) == 1, str(conf))

    print("\nINVARIANTE 7 — a view não deixa passar inferência não revisada")
    con.execute("INSERT INTO interacao_substancia (substancia_a_id,substancia_b_id,"
                "tipo,gravidade,origem,fonte_id,status_revisao) VALUES (1,3,"
                "'FARMACODINAMICA','MODERADA','INFERENCIA_MECANISTICA',1,'PENDENTE')")
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM interacao_substancia").fetchone()[0]
    lib = con.execute("SELECT COUNT(*) FROM vw_interacao_liberada").fetchone()[0]
    confere("inferência pendente barrada pela view", total == 3 and lib == 2,
            "(total=%d liberadas=%d)" % (total, lib))

    print("\nINVARIANTE 8 — separação sem intervalo produz texto honesto")
    txt = con.execute("SELECT orientacao_pt FROM vw_regra_separacao_liberada").fetchone()
    confere("orientação declara ausência do intervalo",
            bool(txt) and "não estabelecido" in txt[0], txt[0] if txt else "")

    print("\nP-03 — hora fora de 00:00–23:59")
    deve_recusar(con, "hora 29:59",
                 "INSERT INTO horario_administracao (posologia_id,hora,definido_por) "
                 "VALUES (1,'29:59','PACIENTE')")
    deve_aceitar(con, "hora 23:59",
                 "INSERT INTO horario_administracao (posologia_id,hora,definido_por) "
                 "VALUES (1,'23:59','PACIENTE')")

    print("\nP-04 — identificadores externos")
    deve_aceitar(con, "DrugBank ID",
                 "INSERT INTO substancia_identificador (substancia_id,sistema,valor) "
                 "VALUES (1,'DRUGBANK','DB00682')")
    deve_recusar(con, "sistema de identificador não previsto",
                 "INSERT INTO substancia_identificador (substancia_id,sistema,valor) "
                 "VALUES (1,'INVENTADO','X')")

    print("\nP-05 — ambiguidade é registrada, não resolvida por sorteio")
    deve_aceitar(con, "termo ambíguo com 2 candidatos",
                 "INSERT INTO resolucao_ambigua (termo_origem,chave_normalizada,"
                 "fonte_id,candidatos,n_candidatos) "
                 "VALUES ('ibuprofen','ibuprofeno',1,'[1,2]',2)")
    deve_recusar(con, "'ambiguidade' com 1 só candidato",
                 "INSERT INTO resolucao_ambigua (termo_origem,chave_normalizada,"
                 "fonte_id,candidatos,n_candidatos) VALUES ('x','x',1,'[]',1)")

    print("\nP-06 — EAN repete, GGREM não")
    deve_aceitar(con, "duas apresentações distintas",
                 "INSERT INTO apresentacao (id,produto_id,codigo_ggrem,descricao) "
                 "VALUES (1,1,'G1','a'),(2,1,'G2','b')")
    deve_aceitar(con, "o mesmo EAN em duas apresentações (ocorre na CMED)",
                 "INSERT INTO apresentacao_ean (apresentacao_id,ean) "
                 "VALUES (1,'7896181924098'),(2,'7896181924098')")
    deve_aceitar(con, "segunda barra da mesma apresentação",
                 "INSERT INTO apresentacao_ean (apresentacao_id,ean,ordem) "
                 "VALUES (1,'7896016806469',2)")
    deve_recusar(con, "EAN com letra",
                 "INSERT INTO apresentacao_ean (apresentacao_id,ean) "
                 "VALUES (1,'789618192409X')")
    deve_recusar(con, "EAN de 5 dígitos",
                 "INSERT INTO apresentacao_ean (apresentacao_id,ean) "
                 "VALUES (1,'78961')")
    deve_recusar(con, "dois GGREM iguais",
                 "INSERT INTO apresentacao (produto_id,codigo_ggrem,descricao) "
                 "VALUES (1,'G1','c')")

    print("\nP-02 — rastreabilidade até a carga")
    deve_aceitar(con, "evidência ligada a fonte e carga",
                 "INSERT INTO evidencia (tabela_alvo,id_alvo,fonte_id,carga_id,"
                 "documento,nivel_evidencia,metodo_extracao) VALUES "
                 "('interacao_substancia',1,1,1,'ddinter_A.csv','RESPALDADA',"
                 "'CARGA_DIRETA')")
    r = con.execute("SELECT fonte,documento_origem,data_importacao IS NOT NULL "
                    "FROM vw_rastreabilidade WHERE id_alvo=1").fetchone()
    confere("afirmação rastreável até fonte, arquivo e data",
            bool(r) and r[0] == 'DDInter' and r[1] == 'ddinter_A.csv' and r[2] == 1,
            str(r))

    print("\nP-08 — índices em colunas de junção")
    idx = {x[0] for x in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    esperados = {'ix_atend_med_subst', 'ix_inter_item_subst', 'ix_evidencia_fonte',
                 'ix_apresentacao_produto', 'ix_apres_subst'}
    confere("índices de junção presentes", not (esperados - idx),
            str(esperados - idx) if (esperados - idx) else "")

    print("\nINTEGRIDADE REFERENCIAL")
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    confere("nenhuma violação de chave estrangeira", not fk, str(fk[:3]))
    deve_recusar(con, "interação apontando para substância inexistente",
                 "INSERT INTO interacao_substancia (substancia_a_id,substancia_b_id,"
                 "tipo,gravidade,origem,fonte_id) VALUES (1,999,'FARMACOCINETICA',"
                 "'MAIOR','FONTE_EXTERNA',1)")

    print("\n" + "=" * 62)
    if falhas:
        print("FALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("TODAS AS VERIFICAÇÕES DO ESQUEMA PASSARAM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
