# -*- coding: utf-8 -*-
"""
TESTES DE REGRESSAO

Cada caso aqui corresponde a um defeito real, ja corrigido. O teste existe
para que ele nao volte. Quando um destes falhar, a causa e uma alteracao
recente -- nao um dado novo.

Fase 2:  CAS de nota de rodape · chave do produto · segunda concentracao ·
         hidratos superiores · 'acido' apos sal · EAN nao unico
Fase 6:  remover medicamento apos analisar - chave estavel da
         anotacao - intencionalidade sem assinatura - ML inexistente
Fase 5:  duplicidade no 5o nivel ATC (regra morta) - db_drug marcado
         como REGEX por um campo acessorio - chave de grupo presa a
         linha - rifampin/rifampicina - gravidade nunca inventada
Fase 3:  captopril · alendronato · diosmina · numeros por extenso ·
         forma acida x sal · separacao com e sem intervalo ·
         extracao automatica nunca vira revisada
Carga:   INSERT cru em tabela de afirmacao · regra_separacao duplicada ·
         conflito de auditoria duplicado · lote de carga por execucao ·
         lote fechado sobrescrito por reexecucao
Fase 9:  mensagem de um atendimento aparecendo na tela de outro · paciente
         orfao deixado em producao por teste · probabilidade calibrada
         saturada exibida como "100%" · codigo interno de subtipo chegando
         cru a tela

Uso: python tests/teste_regressao.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "pipeline"))
BANCO = RAIZ / "database" / "conciliador.db"

from _comum import chaves_candidatas          # noqa: E402
from _diretivas import classificar            # noqa: E402
from _substancia_texto import dividir         # noqa: E402
from normalizacao import skeleton             # noqa: E402

falhas = []


def confere(desc, ok, detalhe=""):
    print("  [%s] %s %s" % ("OK " if ok else "FALHA", desc, detalhe))
    if not ok:
        falhas.append(desc)


def main() -> int:
    con = sqlite3.connect("file:%s?mode=ro" % BANCO.as_posix(), uri=True)
    print("REGRESSÃO — defeitos corrigidos que não podem voltar\n")

    print("FASE 2 — carga e normalização")

    # D-2.1: CAS recebia '[Ref. 8]' da coluna de nota de rodape da DCB
    ruins = con.execute(
        "SELECT COUNT(*) FROM substancia WHERE cas IS NOT NULL "
        "AND cas NOT GLOB '*[0-9]-[0-9][0-9]-[0-9]'").fetchone()[0]
    confere("nenhum CAS com marcador de rodapé ('[Ref. 8]')", ruins == 0,
            "(%d)" % ruins)

    # D-2.2: um produto por apresentacao (registro incluia sufixo)
    prod = con.execute("SELECT COUNT(*) FROM produto").fetchone()[0]
    apres = con.execute("SELECT COUNT(*) FROM apresentacao").fetchone()[0]
    confere("produtos agrupam apresentações", prod < apres * 0.6,
            "%d produtos para %d apresentações" % (prod, apres))

    # D-2.3: apresentacao com duas concentracoes recebia so a primeira
    import re
    re2 = re.compile(r"\+\s*\d+(?:[.,]\d+)?\s*(?:MG|MCG|G|ML|UI|%)", re.I)
    indevidas = [d for (d,) in con.execute(
        "SELECT descricao FROM apresentacao WHERE concentracao_valor IS NOT NULL")
        if re2.search(d)]
    confere("associação em dose fixa fica sem concentração única",
            not indevidas, str(indevidas[:1]))

    # D-2.4: hidratos superiores nao estavam na tabela de sais
    confere("'sulfato de morfina pentaidratado' reduz a morfina",
            skeleton("sulfato de morfina pentaidratado") == skeleton("morfina"),
            skeleton("sulfato de morfina pentaidratado"))

    # D-2.5: 'acido' apos sal sobrevivia ao esqueleto
    confere("'maleato ácido de timolol' reduz a timolol",
            skeleton("maleato ácido de timolol") == skeleton("timolol"),
            skeleton("maleato ácido de timolol"))
    confere("'ácido acetilsalicílico' NÃO perde o 'ácido' inicial",
            skeleton("ácido acetilsalicílico") == skeleton("Acetylsalicylic acid"),
            skeleton("ácido acetilsalicílico"))

    # D-2.6: EAN nao e identidade unica
    dup = con.execute(
        "SELECT COUNT(*) FROM (SELECT ean FROM apresentacao_ean "
        "GROUP BY ean HAVING COUNT(*) > 1)").fetchone()[0]
    confere("EAN repetido é aceito (não é identidade)", dup > 0,
            "%d EANs em mais de uma apresentação" % dup)
    ggrem = con.execute(
        "SELECT COUNT(*) FROM (SELECT codigo_ggrem FROM apresentacao "
        "WHERE codigo_ggrem IS NOT NULL GROUP BY codigo_ggrem "
        "HAVING COUNT(*) > 1)").fetchone()[0]
    confere("GGREM continua único", ggrem == 0, "(%d)" % ggrem)

    # D-2.7: divisao dentro de parenteses gerava fragmento
    confere("parênteses não são divididos",
            dividir("crodabase cr2 (álc. cetoestearílico+óleo mineral)")
            == ["crodabase cr2"])
    frag = con.execute(
        "SELECT COUNT(*) FROM substancia WHERE nome_dcb LIKE '%)' "
        "AND nome_dcb NOT LIKE '%(%'").fetchone()[0]
    confere("nenhum nome é fragmento de parêntese", frag == 0, "(%d)" % frag)

    print("\nFASE 3 — regras de administração")

    def regras(termo):
        return {t for (t,) in con.execute(
            "SELECT r.tipo FROM regra_administracao r JOIN substancia s "
            "ON s.id = r.substancia_id WHERE s.nome_dcb LIKE ?",
            ("%" + termo + "%",))}

    # D-3.1: captopril ficava sem regra ('separate from meals', nao 'empty stomach')
    confere("captopril tem regra de jejum", "JEJUM" in regras("captopril"),
            str(sorted(regras("captopril"))))
    d = classificar("Take separate from meals. Take one hour prior to meals.")
    confere("'separate from meals' é reconhecido como jejum",
            any(a["tipo"] == "JEJUM" for a in d["administracao"]))

    # D-3.2: numeros por extenso perdiam o intervalo
    confere("'one hour prior to meals' vira 60 minutos",
            any(a["intervalo_refeicao_min"] == 60 for a in d["administracao"]),
            str([a["intervalo_refeicao_min"] for a in d["administracao"]]))

    # D-3.3: forma acida (EN) x sal (BR)
    confere("'Alendronic acid' gera candidato '-ate'",
            skeleton("alendronato") in chaves_candidatas("Alendronic acid"),
            str(chaves_candidatas("Alendronic acid")))
    confere("alendronato tem alguma regra carregada", bool(regras("alendronato")),
            str(sorted(regras("alendronato"))))

    # D-3.4: diosmina ficava com tres regras alimentares contraditorias
    alimentares = regras("diosmina") & {"JEJUM", "COM_ALIMENTO", "APOS_ALIMENTO",
                                        "ANTES_ALIMENTO", "INDIFERENTE_ALIMENTO"}
    confere("diosmina não tem regras alimentares contraditórias",
            len(alimentares) <= 1, str(sorted(alimentares)))

    # nenhuma substancia pode ter duas regras alimentares excludentes da MESMA fonte
    conflitantes = con.execute(
        "SELECT COUNT(*) FROM (SELECT substancia_id, fonte_id "
        "FROM regra_administracao WHERE tipo IN ('JEJUM','COM_ALIMENTO',"
        "'APOS_ALIMENTO','ANTES_ALIMENTO','INDIFERENTE_ALIMENTO') "
        "GROUP BY substancia_id, fonte_id HAVING COUNT(DISTINCT tipo) > 1)"
    ).fetchone()[0]
    confere("nenhuma fonte afirma duas regras alimentares para o mesmo fármaco",
            conflitantes == 0, "(%d)" % conflitantes)

    # D-3.5: 'avoid multivalent ions' nao gerava separacao
    d2 = classificar("Avoid multivalent ions. Calcium, antacids, and divalent "
                     "ions may interfere with the absorption of this medication.")
    confere("'avoid multivalent ions' gera separação",
            bool(d2["separacao"]), str([s["item"] for s in d2["separacao"]]))
    confere("e sem intervalo inventado",
            all(s["intervalo_horas"] is None for s in d2["separacao"]),
            str([s["intervalo_horas"] for s in d2["separacao"]]))

    # D-3.6: separacao com e sem intervalo convivem
    com = con.execute("SELECT COUNT(*) FROM regra_separacao "
                      "WHERE intervalo_horas IS NOT NULL").fetchone()[0]
    sem = con.execute("SELECT COUNT(*) FROM regra_separacao "
                      "WHERE intervalo_horas IS NULL").fetchone()[0]
    confere("existem separações com intervalo declarado", com > 0, "(%d)" % com)
    confere("e separações com intervalo desconhecido", sem > 0, "(%d)" % sem)
    textos = [t for (t,) in con.execute(
        "SELECT orientacao_pt FROM vw_regra_separacao_liberada "
        "WHERE intervalo_horas IS NULL")]
    confere("as sem intervalo declaram a ausência",
            all("não estabelecido" in t for t in textos),
            textos[0] if textos else "")
    confere("e nenhuma cita um número de horas",
            not [t for t in textos if re.search(r"\d+\s*hora", t)])

    # D-3.7: extracao automatica nunca aparece como revisada
    mentira = con.execute(
        "SELECT COUNT(*) FROM vw_regra_administracao_liberada r "
        "WHERE r.confianca_extracao = 'REVISADA' AND r.status_revisao <> 'APROVADO'"
    ).fetchone()[0]
    confere("nenhuma regra não aprovada se diz revisada", mentira == 0,
            "(%d)" % mentira)

    # D-3.8: tarja lida do rotulo, nao do codigo numerico
    esperado = {"dipirona": "MIP", "clonazepam": "TARJA_PRETA",
                "tramadol": "TARJA_VERMELHA_RETENCAO"}
    for termo, alvo in esperado.items():
        r = con.execute(
            "SELECT canal_dispensacao FROM substancia WHERE nome_dcb LIKE ? "
            "AND canal_dispensacao IS NOT NULL LIMIT 1",
            ("%" + termo + "%",)).fetchone()
        confere("tarja de %s" % termo, bool(r) and r[0] == alvo,
                r[0] if r else "(ausente)")

    print()
    print("FASE 5 — interações, conciliação e prioridade")

    # D-5.1: a duplicidade terapeutica estava escrita no 5o nivel ATC, que
    # identifica a propria substancia. A regra nunca poderia disparar.
    n5 = con.execute(
        "SELECT COUNT(*) FROM (SELECT atc_codigo FROM substancia "
        "WHERE LENGTH(atc_codigo)=7 GROUP BY 1 HAVING COUNT(*)>1)").fetchone()[0]
    n4 = con.execute(
        "SELECT COUNT(*) FROM (SELECT SUBSTR(atc_codigo,1,5) c FROM substancia "
        "WHERE LENGTH(atc_codigo)>=5 GROUP BY 1 HAVING COUNT(*)>1)").fetchone()[0]
    confere("duplicidade terapêutica usa o nível ATC que existe",
            n5 == 0 and n4 > 100,
            "5º nível: %d grupos (regra morta) · 4º nível: %d grupos" % (n5, n4))

    # D-5.2: a linha inteira do db_drug_interactions era marcada REGEX por
    # causa de um campo derivado, rebaixando 54 mil interacoes.
    regex_ii = con.execute(
        "SELECT COUNT(*) FROM evidencia WHERE tabela_alvo='interacao_substancia' "
        "AND metodo_extracao='REGEX'").fetchone()[0]
    confere("interação lida de coluna não se declara extraída por regex",
            regex_ii == 0, "(%d)" % regex_ii)

    # D-5.3: gravidade NUNCA e inventada. A fonte que nao gradua nao recebe
    # gravidade nenhuma, nem por precaucao.
    dbdi = con.execute(
        "SELECT COUNT(*) FROM interacao_substancia i JOIN fonte f "
        "ON f.id=i.fonte_id WHERE f.nome='db_drug_interactions' "
        "AND i.gravidade <> 'NAO_DETERMINADA'").fetchone()[0]
    confere("fonte que não gradua não recebe gravidade", dbdi == 0, "(%d)" % dbdi)

    # D-5.4: rifampin (USAN) nao casava com rifampicina (DCB), e o maior
    # indutor enzimatico da tabela da FDA ficava de fora.
    rif = con.execute(
        "SELECT COUNT(*) FROM papel_farmacocinetico p JOIN substancia s "
        "ON s.id=p.substancia_id WHERE s.nome_dcb='rifampicina' "
        "AND p.papel='INDUTOR'").fetchone()[0]
    confere("rifampicina entrou como indutor (USAN x DCB)", rif >= 4, "(%d)" % rif)

    # D-5.5: ML nunca atribui gravidade.
    ml = con.execute("SELECT COUNT(*) FROM predicao WHERE gravidade_sugerida "
                     "IS NOT NULL").fetchone()[0]
    confere("ML não atribui gravidade", ml == 0, "(%d)" % ml)

    # D-5.6: a chave de grupo do achado nao pode conter id de linha.
    presas = con.execute(
        "SELECT COUNT(*) FROM achado WHERE grupo_chave LIKE 'ADM:am%' "
        "OR grupo_chave LIKE 'DOSE:am%'").fetchone()[0]
    confere("nenhuma chave de grupo presa à linha do atendimento",
            presas == 0, "(%d)" % presas)

    # D-5.7: contraindicacao extraida por regex nunca se apresenta revisada.
    mentira5 = con.execute(
        "SELECT COUNT(*) FROM interacao_doenca WHERE status_revisao='APROVADO' "
        "AND origem='BULA_ANVISA'").fetchone()[0]
    confere("contraindicação de bula continua pendente de revisão",
            mentira5 == 0, "(%d)" % mentira5)

    # D-5.8: a bula nao gradua, entao a gravidade fica nao determinada.
    grav = con.execute(
        "SELECT COUNT(*) FROM interacao_doenca WHERE gravidade "
        "<> 'NAO_DETERMINADA'").fetchone()[0]
    confere("bula não gradua, então gravidade fica não determinada",
            grav == 0, "(%d)" % grav)

    print()
    print("FASE 6 — aplicação do farmacêutico")

    # D-6.1: sem ON DELETE CASCADE em conciliacao_par, remover um medicamento
    # DEPOIS de analisar era impossivel — o banco recusava e o farmaceutico
    # ficava preso ao primeiro resultado. Achado pela verificacao independente.
    fks = con.execute("PRAGMA foreign_key_list(conciliacao_par)").fetchall()
    para_am = [f for f in fks if f[2] == "atendimento_medicamento"]
    confere("remover medicamento após analisar continua possível",
            len(para_am) == 2 and all(f[6] == "CASCADE" for f in para_am),
            "%d referência(s), ações: %s"
            % (len(para_am), [f[6] for f in para_am]))

    # D-6.2: a anotacao do profissional e presa a uma chave ESTAVEL. Se fosse
    # o id do achado, uma reanalise apagaria toda a revisao ja feita.
    numericas = con.execute(
        "SELECT COUNT(*) FROM anotacao_profissional "
        "WHERE chave GLOB '[0-9]*' AND chave NOT GLOB '*[^0-9]*'").fetchone()[0]
    confere("anotação profissional usa chave estável, não id de linha",
            numericas == 0, "(%d)" % numericas)

    # D-6.3: a aplicacao nao decide intencionalidade de divergencia.
    sem_assinatura = con.execute(
        "SELECT COUNT(*) FROM conciliacao_par WHERE intencionalidade "
        "<> 'NAO_DETERMINADA' AND avaliado_por IS NULL").fetchone()[0]
    confere("intencionalidade nunca sem profissional identificado",
            sem_assinatura == 0, "(%d)" % sem_assinatura)

    # D-6.4: nao ha ML no projeto, e nenhum achado pode fingir que ha.
    ml = con.execute(
        "SELECT COUNT(*) FROM achado WHERE origem_achado <> 'REGRA' "
        "OR probabilidade_modelo IS NOT NULL").fetchone()[0]
    confere("nenhum achado se apresenta como previsão de modelo",
            ml == 0, "(%d)" % ml)

    print()
    print("CARGA INCREMENTAL — defeitos achados ao rodar o pipeline duas vezes")

    # D-C.1: `20_substancias.py` fazia um INSERT INTO substancia puro e a
    # segunda execucao abortava na primeira substancia ja existente. O modo
    # incremental documentado nunca tinha funcionado. Nenhum ETL pode voltar a
    # inserir em tabela de afirmacao sem OR IGNORE ou consulta previa.
    TABELAS_AFIRMACAO = (
        "substancia", "produto", "apresentacao", "classe_atc",
        "regra_administracao", "regra_separacao", "interacao_substancia",
        "interacao_item", "interacao_doenca", "interacao_habito",
        "papel_farmacocinetico", "auditoria_conflito", "evidencia")
    cruas = []
    for arq in sorted((RAIZ / "pipeline").glob("[0-9]*.py")):
        texto = arq.read_text(encoding="utf-8")
        for tabela in TABELAS_AFIRMACAO:
            if "INSERT INTO %s " % tabela in texto or \
               "INSERT INTO %s(" % tabela in texto:
                cruas.append("%s -> %s" % (arq.name, tabela))
    confere("nenhum ETL insere em tabela de afirmação sem OR IGNORE",
            not cruas, str(cruas) if cruas else "(13 tabelas conferidas)")

    # D-C.2: `regra_separacao` era a unica tabela de afirmacao sem chave de
    # unicidade. Cinco entradas do DrugBank caem em 'brometo de zinco', e as
    # mesmas 3 regras entravam 5 vezes: 15 linhas para 3 regras.
    dup_sep = con.execute(
        "SELECT COUNT(*) FROM (SELECT substancia_id, alvo_tipo, "
        "COALESCE(alvo_substancia_id,-1), COALESCE(alvo_item_id,-1), "
        "COALESCE(alvo_classe_atc,''), COALESCE(intervalo_horas,-1), sentido, "
        "motivo, fonte_id, COUNT(*) n FROM regra_separacao "
        "GROUP BY 1,2,3,4,5,6,7,8,9 HAVING n > 1)").fetchone()[0]
    confere("nenhuma regra de separação duplicada letra por letra",
            dup_sep == 0, "(%d)" % dup_sep)

    idx = {n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    confere("o índice que impede a duplicação existe",
            "ux_regra_separacao" in idx)

    # D-C.3: o mesmo conflito, detectado de novo, virava linha nova.
    dup_conf = con.execute(
        "SELECT COUNT(*) FROM (SELECT tabela_alvo, COALESCE(id_alvo,-1), "
        "descricao, fonte_a, valor_a, fonte_b, valor_b, COUNT(*) n "
        "FROM auditoria_conflito GROUP BY 1,2,3,4,5,6,7 HAVING n > 1)"
    ).fetchone()[0]
    confere("nenhum conflito de auditoria duplicado", dup_conf == 0,
            "(%d)" % dup_conf)
    confere("o índice que impede a duplicação existe",
            "ux_auditoria_conflito" in idx)

    # D-C.4: `carga` e o LOTE de dados, nao o log de execucoes. Cada passada
    # criava 11 linhas novas que nao correspondiam a dado nenhum — e isso
    # mudava a impressao digital do banco usada pela Fase 7.
    lotes = con.execute(
        "SELECT COUNT(*) FROM (SELECT script, documento_origem, COUNT(*) n "
        "FROM carga GROUP BY 1,2 HAVING n > 1)").fetchone()[0]
    confere("um lote de carga por (script, arquivo)", lotes == 0,
            "(%d repetidos)" % lotes)

    # D-C.6: o pipeline nao convergia numa passada. `40_atc.py` casa substancia
    # com codigo ATC usando um indice que inclui `substancia_sinonimo` — mas os
    # sinonimos INN sao criados depois, por `60_interacoes_substancia.py`. A
    # primeira passada perdia 6 vinculos que a segunda encontrava: 1.153 contra
    # 1.159 substancias com ATC. O resultado do pipeline dependia de quantas
    # vezes ele tinha rodado, e a impressao digital dos dados (que so olhava
    # CONTAGEM de linhas) nao via a diferenca. Corrigido pelo passo 68.
    com_atc = con.execute("SELECT COUNT(*) FROM substancia "
                          "WHERE atc_codigo IS NOT NULL").fetchone()[0]
    confere("o vínculo ATC convergiu (2ª passada já aplicada)",
            com_atc >= 1159, "(%d substâncias com ATC)" % com_atc)
    passo68 = con.execute(
        "SELECT COUNT(*) FROM carga WHERE script='68_vincular_atc_pendente.py'"
    ).fetchone()[0]
    confere("o passo 68 rodou e deixou lote registrado", passo68 == 1,
            "(%d lote)" % passo68)
    sem_atc_com_inn = con.execute(
        "SELECT COUNT(*) FROM substancia s WHERE s.atc_codigo IS NULL "
        "AND EXISTS (SELECT 1 FROM substancia_sinonimo x "
        "            JOIN classe_atc c ON c.nivel=5 "
        "            WHERE x.substancia_id=s.id AND x.tipo='INN' "
        "              AND x.chave_normalizada IS NOT NULL "
        "              AND c.codigo=s.atc_codigo)").fetchone()[0]
    confere("nenhum vínculo ATC ficou pendente por ordem de execução",
            sem_atc_com_inn == 0, "(%d)" % sem_atc_com_inn)

    # D-C.5: `fechar_carga` sobrescrevia os numeros do lote original com os
    # zeros de uma reexecucao, apagando "quantas linhas entraram deste arquivo".
    abertas = con.execute(
        "SELECT COUNT(*) FROM carga WHERE registros_lidos IS NULL").fetchone()[0]
    zeradas = con.execute(
        "SELECT COUNT(*) FROM carga WHERE registros_lidos = 0").fetchone()[0]
    confere("nenhum lote ficou aberto ou zerado por reexecução",
            abertas == 0 and zeradas == 0,
            "(abertas %d, zeradas %d)" % (abertas, zeradas))

    # =================================================================
    # FASE 9 — defeitos de integracao achados pela validacao do sistema
    # =================================================================
    print("\nFASE 9 — o que a validação do sistema inteiro encontrou")

    web_py = (RAIZ / "app" / "web.py").read_text(encoding="utf-8")
    base_html = (RAIZ / "app" / "templates" / "base.html").read_text(
        encoding="utf-8")

    # D-9.1: a fila de mensagens do Flask e da SESSAO, nao do atendimento.
    # Com dois atendimentos abertos, "Posologia de Gliclazida 30 mg salva"
    # saia na tela de quem toma varfarina.
    confere("mensagem de estado é presa ao atendimento que a gerou",
            "def avisar(" in web_py and "def mensagens_da_tela(" in web_py
            and "mensagens_da_tela(codigo" in base_html)
    cruas = [l.strip() for l in web_py.splitlines()
             if re.search(r"(?<!\w)flash\(", l)
             and "def avisar" not in l and "flash(texto," not in l]
    confere("nenhuma rota chama flash() direto, sem o atendimento",
            not cruas, cruas[:1])

    # D-9.2: `verificacao_aplicacao.py` apagava o atendimento do eixo 5 antes
    # de `limpar()` procurar o paciente por ele — cinco linhas "Integridade B"
    # ficaram para sempre no banco de producao.
    orfaos = con.execute(
        "SELECT COUNT(*) FROM paciente p WHERE NOT EXISTS "
        "(SELECT 1 FROM atendimento a WHERE a.paciente_id = p.id)"
    ).fetchone()[0]
    confere("nenhum paciente órfão sobrou de teste no banco",
            orfaos == 0, "(%d)" % orfaos)
    verif = (RAIZ / "tests" / "verificacao_aplicacao.py").read_text(
        encoding="utf-8")
    confere("a verificação da aplicação guarda o id do paciente ao criar",
            "for codigo, paciente_id in CRIADOS" in verif)

    # D-9.3: a calibracao isotonica satura em 1,0. Exibido como "100%", ao
    # lado de "nao ha evidencia documental", prometia certeza.
    sys.path.insert(0, str(RAIZ / "rules"))
    import _prioridade as _prio
    confere("probabilidade calibrada saturada não é exibida como 100%",
            _prio.percentual_previsao(1.0) == "acima de 99%"
            and _prio.percentual_previsao(0.0) == "abaixo de 1%",
            _prio.percentual_previsao(1.0))
    confere("probabilidade fora do teto continua saindo em percentual",
            _prio.percentual_previsao(0.72) == "72%",
            _prio.percentual_previsao(0.72))
    motor_py = (RAIZ / "rules" / "motor_conciliacao.py").read_text(
        encoding="utf-8")
    confere("o motor não formata a probabilidade por conta própria",
            "100 * prob_exib" not in motor_py)
    for arquivo in ("app/relatorio.py", "app/templates/relatorio.html",
                    "app/templates/resultados.html"):
        texto = (RAIZ / arquivo).read_text(encoding="utf-8")
        confere("%s usa o formatador único de probabilidade" % arquivo,
                "100 * a.probabilidade_modelo" not in texto
                and "percentual_previsao" in texto)

    # D-9.4: o subtipo chegava a tela como "interacao prevista", cru.
    rotulos_py = (RAIZ / "app" / "rotulos.py").read_text(encoding="utf-8")
    achado_html = (RAIZ / "app" / "templates" / "achado.html").read_text(
        encoding="utf-8")
    confere("o subtipo do achado tem tradução em português",
            "SUBTIPO = {" in rotulos_py
            and "Interação prevista por modelo" in rotulos_py)
    confere("a tela do achado traduz o subtipo em vez de exibir o código",
            "rot.rotular(rot.SUBTIPO" in achado_html)

    con.close()
    print("\n" + "=" * 66)
    if falhas:
        print("REGRESSÕES: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("NENHUMA REGRESSÃO — todos os defeitos corrigidos continuam corrigidos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
