# -*- coding: utf-8 -*-
"""
Validacao estrutural do banco. Roda ao fim de toda carga.

Sai com codigo 1 se qualquer garantia for violada -- para que uma carga
defeituosa falhe ruidosamente em vez de virar dado silenciosamente errado.

Isto NAO substitui as verificacoes independentes em tests/: aqui e a
verificacao 1 (funciona?), la e a 2 (outra evidencia mostra o mesmo?).

Uso: python pipeline/90_validacao.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import BANCO, conectar  # noqa: E402

falhas = []
avisos = []


def checa(desc, sql, esperado=0, comp="=="):
    v = con.execute(sql).fetchone()[0]
    ok = (v == esperado) if comp == "==" else (v > esperado)
    print("  [%s] %-58s %s" % ("OK " if ok else "FALHA", desc, v))
    if not ok:
        falhas.append((desc, v, esperado))
    return v


def informa(desc, sql):
    v = con.execute(sql).fetchone()[0]
    print("  %-64s %s" % (desc, v))
    return v


con = conectar()
print("VALIDACAO ESTRUTURAL — %s\n" % BANCO.name)

print("INTEGRIDADE")
fk = con.execute("PRAGMA foreign_key_check").fetchall()
print("  [%s] %-58s %d" % ("OK " if not fk else "FALHA",
                           "violacoes de chave estrangeira", len(fk)))
if fk:
    falhas.append(("foreign_key_check", len(fk), 0))
ic = con.execute("SELECT * FROM pragma_integrity_check").fetchone()[0]
print("  [%s] %-58s %s" % ("OK " if ic == "ok" else "FALHA",
                           "integrity_check do SQLite", ic))
if ic != "ok":
    falhas.append(("integrity_check", ic, "ok"))

print("\nINVARIANTES DE SEGURANCA CLINICA")
checa("predicao com gravidade atribuida pelo modelo",
      "SELECT COUNT(*) FROM predicao WHERE gravidade_sugerida IS NOT NULL")
checa("achado PREVISTO sem probabilidade do modelo",
      "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' "
      "AND probabilidade_modelo IS NULL")
checa("achado DOCUMENTADO sem nivel de evidencia",
      "SELECT COUNT(*) FROM achado WHERE natureza='DOCUMENTADO' "
      "AND nivel_evidencia IS NULL")
# --- Fase 7: previsao nunca se apresenta como fato, nem por descuido ---
checa("achado PREVISTO sem apontar a linha de predicao que o sustenta",
      "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' "
      "AND origem_afirmacao NOT LIKE 'predicao.%'")
checa("achado PREVISTO com nivel de evidencia de publicacao",
      "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' "
      "AND nivel_evidencia IS NOT NULL AND nivel_evidencia <> 'NAO_AVALIADA'")
checa("achado de origem MODELO que nao se declara previsao",
      "SELECT COUNT(*) FROM achado WHERE origem_achado='MODELO' "
      "AND natureza <> 'PREVISTO'")
checa("mais de um modelo ativo para o mesmo problema",
      "SELECT COUNT(*) FROM (SELECT problema FROM modelo WHERE ativo=1 "
      "GROUP BY problema HAVING COUNT(*)>1)")
checa("modelo ativo sem estar homologado",
      "SELECT COUNT(*) FROM modelo WHERE ativo=1 AND status<>'HOMOLOGADO'")
checa("modelo sem semente, versao de dados ou espaco de atributos",
      "SELECT COUNT(*) FROM modelo WHERE semente IS NULL "
      "OR versao_dados IS NULL OR espaco_features_json IS NULL")
checa("predicao revisada sem quem revisou",
      "SELECT COUNT(*) FROM predicao WHERE status<>'NAO_REVISADA' "
      "AND revisado_por IS NULL")
# --- Fase 8: a integracao nao pode abrir porta que o esquema fechou ---
checa("previsao liberada para par que TEM interacao documentada",
      "SELECT COUNT(*) FROM vw_predicao_liberada v WHERE EXISTS "
      "(SELECT 1 FROM interacao_substancia i "
      "  WHERE i.substancia_a_id=v.substancia_a_id "
      "    AND i.substancia_b_id=v.substancia_b_id)")
checa("previsao liberada por modelo sem limiar de alerta declarado",
      "SELECT COUNT(*) FROM vw_predicao_liberada WHERE limiar_alerta IS NULL")
checa("previsao liberada abaixo do limiar do proprio modelo",
      "SELECT COUNT(*) FROM vw_predicao_liberada "
      "WHERE probabilidade_exibida < limiar_alerta")
checa("previsao recusada por farmaceutico ainda liberada",
      "SELECT COUNT(*) FROM vw_predicao_liberada "
      "WHERE status_predicao='REVISADA_RECUSADA'")
checa("achado previsto com evidencia documental anexada",
      "SELECT COUNT(*) FROM achado_evidencia e JOIN achado a "
      "ON a.id=e.achado_id WHERE a.natureza='PREVISTO'")
checa("achado previsto acima de INFORMATIVO",
      "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' "
      "AND prioridade <> 'INFORMATIVO'")
checa("achado previsto com confianca do sistema diferente de BAIXA",
      "SELECT COUNT(*) FROM achado WHERE natureza='PREVISTO' "
      "AND confianca_sistema <> 'BAIXA'")
checa("achado previsto e achado documentado no mesmo grupo",
      "SELECT COUNT(*) FROM achado p JOIN achado d "
      "ON d.conciliacao_id=p.conciliacao_id AND d.grupo_chave=p.grupo_chave "
      "WHERE p.natureza='PREVISTO' AND d.natureza<>'PREVISTO'")
checa("predicao apontando para modelo aposentado e ainda em uso",
      "SELECT COUNT(*) FROM predicao p JOIN modelo m ON m.id=p.modelo_id "
      "JOIN achado a ON a.origem_afirmacao = 'predicao.' || p.id "
      "WHERE m.status='APOSENTADO'")
checa("interacao com par fora de ordem (A > B)",
      "SELECT COUNT(*) FROM interacao_substancia "
      "WHERE substancia_a_id >= substancia_b_id")
checa("regra de separacao com intervalo fora de 0,25-24 h",
      "SELECT COUNT(*) FROM regra_separacao WHERE intervalo_horas IS NOT NULL "
      "AND (intervalo_horas < 0.25 OR intervalo_horas > 24)")
checa("horario invalido",
      "SELECT COUNT(*) FROM horario_administracao WHERE NOT "
      "(hora GLOB '[0-1][0-9]:[0-5][0-9]' OR hora GLOB '2[0-3]:[0-5][0-9]')")

print("\nINVARIANTES DA FASE 5 — INTERACAO, ACHADO E CONCILIACAO")
checa("interacao afirmando gravidade que a fonte nao gradua "
      "(db_drug_interactions)",
      "SELECT COUNT(*) FROM interacao_substancia i JOIN fonte f "
      "ON f.id=i.fonte_id WHERE f.nome='db_drug_interactions' "
      "AND i.gravidade <> 'NAO_DETERMINADA'")
checa("interacao com efeito em portugues igual ao original em ingles",
      "SELECT COUNT(*) FROM interacao_substancia "
      "WHERE efeito_esperado IS NOT NULL "
      "AND efeito_esperado = descricao_original")
checa("interacao sem evidencia de origem",
      "SELECT COUNT(*) FROM interacao_substancia i WHERE NOT EXISTS "
      "(SELECT 1 FROM evidencia e WHERE e.tabela_alvo='interacao_substancia' "
      " AND e.id_alvo=i.id)")
checa("contraindicacao de bula sem trecho literal que a sustente",
      "SELECT COUNT(*) FROM interacao_doenca WHERE origem='BULA_ANVISA' "
      "AND (trecho_origem IS NULL OR trecho_origem='')")
checa("contraindicacao de bula com gravidade inventada",
      "SELECT COUNT(*) FROM interacao_doenca WHERE origem='BULA_ANVISA' "
      "AND gravidade <> 'NAO_DETERMINADA'")
checa("extracao por regex apresentada como revisada",
      "SELECT COUNT(*) FROM evidencia e WHERE e.metodo_extracao IN "
      "('REGEX','NLP') AND e.revisado_por IS NOT NULL")
checa("papel farmacocinetico sem potencia declarada",
      "SELECT COUNT(*) FROM papel_farmacocinetico "
      "WHERE potencia IS NULL OR potencia=''")

# As invariantes de `achado` valem quando ha conciliacao gravada. Sem
# nenhuma gravada, a contagem e zero e o teste passa trivialmente -- por isso
# o motor tem a sua propria bateria em tests/.
checa("achado com natureza PREVISTO e status divergente",
      "SELECT COUNT(*) FROM achado WHERE (natureza='PREVISTO') "
      "<> (status_informacao='PREVISTO')")
checa("achado de regra carregando probabilidade de modelo",
      "SELECT COUNT(*) FROM achado WHERE origem_achado='REGRA' "
      "AND probabilidade_modelo IS NOT NULL")
checa("achado marcado REVISADO sem extracao revisada",
      "SELECT COUNT(*) FROM achado WHERE status_informacao='REVISADO' "
      "AND confianca_extracao <> 'REVISADA'")
checa("achado com informacao insuficiente acima de informativo",
      "SELECT COUNT(*) FROM achado WHERE classificacao='INFORMACAO_INSUFICIENTE' "
      "AND prioridade <> 'INFORMATIVO'")
checa("achado sem justificativa de prioridade",
      "SELECT COUNT(*) FROM achado WHERE justificativa_prioridade IS NULL "
      "OR justificativa_prioridade=''")
checa("achado agrupado sem representante existente",
      "SELECT COUNT(*) FROM achado a WHERE a.status='AGRUPADO' "
      "AND NOT EXISTS (SELECT 1 FROM achado b WHERE b.id=a.agrupado_em)")
checa("achado exibindo gravidade que nenhuma evidencia declara",
      "SELECT COUNT(*) FROM achado a WHERE a.gravidade_fonte IS NOT NULL "
      "AND a.gravidade_fonte <> 'NAO_DETERMINADA' "
      "AND NOT EXISTS (SELECT 1 FROM achado_evidencia e "
      "  WHERE e.achado_id=a.id AND e.gravidade_declarada=a.gravidade_fonte)")
checa("intencionalidade decidida sem profissional identificado",
      "SELECT COUNT(*) FROM conciliacao_par "
      "WHERE intencionalidade <> 'NAO_DETERMINADA' AND avaliado_por IS NULL")


print("\nRASTREABILIDADE")
checa("substancia sem evidencia de origem",
      "SELECT COUNT(*) FROM substancia s WHERE NOT EXISTS (SELECT 1 FROM "
      "evidencia e WHERE e.tabela_alvo='substancia' AND e.id_alvo=s.id)")
checa("apresentacao sem evidencia de origem",
      "SELECT COUNT(*) FROM apresentacao a WHERE NOT EXISTS (SELECT 1 FROM "
      "evidencia e WHERE e.tabela_alvo='apresentacao' AND e.id_alvo=a.id)")
checa("evidencia apontando para fonte inexistente",
      "SELECT COUNT(*) FROM evidencia e WHERE NOT EXISTS "
      "(SELECT 1 FROM fonte f WHERE f.id=e.fonte_id)")
checa("carga sem contagem registrada",
      "SELECT COUNT(*) FROM carga WHERE registros_lidos IS NULL")

print("\nQUALIDADE DOS DADOS")
checa("substancia sem produto ativo",
      "SELECT COUNT(*) FROM substancia WHERE n_produtos_ativos < 1")
checa("CAS fora do formato oficial",
      "SELECT COUNT(*) FROM substancia WHERE cas IS NOT NULL "
      "AND cas NOT GLOB '*[0-9]-[0-9][0-9]-[0-9]'")
checa("EAN fora do padrao GS1",
      "SELECT COUNT(*) FROM apresentacao_ean WHERE ean GLOB '*[^0-9]*' "
      "OR length(ean) NOT IN (8,12,13,14)")
checa("esqueleto duplicado entre substancias",
      "SELECT COUNT(*) FROM (SELECT chave_normalizada FROM substancia "
      "GROUP BY chave_normalizada HAVING COUNT(*) > 1)")
checa("ambiguidade marcada sem registro para curadoria",
      "SELECT COUNT(*) FROM substancia s WHERE s.status_resolucao='AMBIGUA' "
      "AND NOT EXISTS (SELECT 1 FROM resolucao_ambigua r "
      "WHERE r.chave_normalizada = s.chave_normalizada)")
checa("classe ATC apontando para pai inexistente",
      "SELECT COUNT(*) FROM classe_atc c WHERE c.codigo_pai IS NOT NULL "
      "AND NOT EXISTS (SELECT 1 FROM classe_atc p WHERE p.codigo=c.codigo_pai)")

print("\nVOLUME CARREGADO")
for tabela in ("fonte", "carga", "evidencia", "substancia",
               "substancia_sinonimo", "substancia_identificador",
               "resolucao_ambigua", "produto", "apresentacao",
               "apresentacao_ean", "apresentacao_substancia", "classe_atc",
               "interacao_substancia", "interacao_doenca", "interacao_item",
               "interacao_habito", "papel_farmacocinetico", "doenca",
               "regra_administracao", "regra_separacao"):
    informa(tabela, "SELECT COUNT(*) FROM %s" % tabela)

print("\nCOBERTURA — o que o sistema sabe e o que nao sabe")
total = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
for desc, sql in [
    ("substancias com codigo ATC",
     "SELECT COUNT(*) FROM substancia WHERE atc_codigo IS NOT NULL"),
    ("substancias com CAS",
     "SELECT COUNT(*) FROM substancia WHERE cas IS NOT NULL"),
    ("substancias com numero DCB",
     "SELECT COUNT(*) FROM substancia WHERE dcb_numero IS NOT NULL"),
    ("substancias com canal de dispensacao",
     "SELECT COUNT(*) FROM substancia WHERE canal_dispensacao IS NOT NULL"),
    ("substancias ligadas a alguma apresentacao",
     "SELECT COUNT(DISTINCT substancia_id) FROM apresentacao_substancia"),
]:
    v = con.execute(sql).fetchone()[0]
    print("  %-52s %6d  (%.1f%%)" % (desc, v, 100 * v / max(1, total)))

trad = con.execute(
    "SELECT COUNT(*) FROM classe_atc WHERE nome_pt <> nome_en").fetchone()[0]
tot_atc = con.execute("SELECT COUNT(*) FROM classe_atc").fetchone()[0]
print("  %-52s %6d  (%.1f%%)" % ("classes ATC com nome em portugues",
                                 trad, 100 * trad / max(1, tot_atc)))
if trad < tot_atc:
    avisos.append("%d classes ATC ainda em ingles (declaradas, nao traduzidas "
                  "pela metade)" % (tot_atc - trad))

print("\nCOBERTURA DOS MODULOS DO MOTOR DE CONCILIACAO")
total_s = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
for desc, sql in [
    ("modulo 1  farmaco x farmaco",
     "SELECT COUNT(DISTINCT s) FROM (SELECT substancia_a_id AS s FROM "
     "interacao_substancia UNION SELECT substancia_b_id FROM "
     "interacao_substancia)"),
    ("modulo 2  farmaco x doenca",
     "SELECT COUNT(DISTINCT substancia_id) FROM interacao_doenca"),
    ("modulos 4-6  farmaco x alimento, planta e suplemento",
     "SELECT COUNT(DISTINCT substancia_id) FROM interacao_item"),
    ("modulo 7  farmaco x habito",
     "SELECT COUNT(DISTINCT substancia_id) FROM interacao_habito"),
    ("modulo 7b farmaco x CYP",
     "SELECT COUNT(DISTINCT substancia_id) FROM papel_farmacocinetico"),
    ("modulo 8  duplicidade (substancias com ATC de 4o nivel)",
     "SELECT COUNT(*) FROM substancia WHERE LENGTH(atc_codigo)>=5"),
    ("modulos 10-11 regra de administracao",
     "SELECT COUNT(DISTINCT substancia_id) FROM regra_administracao"),
]:
    v = con.execute(sql).fetchone()[0]
    print("  %-52s %6d  (%.1f%%)" % (desc, v, 100 * v / max(1, total_s)))

grad = con.execute("SELECT COUNT(*) FROM interacao_substancia "
                   "WHERE gravidade <> 'NAO_DETERMINADA'").fetchone()[0]
tot_i = con.execute("SELECT COUNT(*) FROM interacao_substancia").fetchone()[0]
if tot_i:
    print("  %-52s %6d  (%.1f%%)" % ("linhas de interacao COM gravidade graduada",
                                     grad, 100 * grad / tot_i))
    avisos.append("%d de %d linhas de interacao (%.1f%%) estao "
                  "NAO_DETERMINADA porque a fonte nao gradua"
                  % (tot_i - grad, tot_i, 100 * (tot_i - grad) / tot_i))

print("\n" + "=" * 72)
if avisos:
    print("AVISOS (nao bloqueiam):")
    for a in avisos:
        print("  -", a)
if falhas:
    print("\nVALIDACAO FALHOU: %d garantia(s) violada(s)" % len(falhas))
    for d, v, e in falhas:
        print("  - %s: obtido %s, esperado %s" % (d, v, e))
    con.close()
    sys.exit(1)
print("VALIDACAO COMPLETA — todas as garantias satisfeitas")
con.close()
sys.exit(0)
