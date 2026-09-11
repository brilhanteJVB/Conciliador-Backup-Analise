# -*- coding: utf-8 -*-
"""
INTERFACE — aplicação local do Conciliador de Medicamentos.

    INTERFACE (este arquivo + templates)
        v
    SERVICOS  (app/servicos.py, app/busca.py, app/relatorio.py)
        v
    MOTORES   (rules/motor_horarios.py, rules/motor_conciliacao.py)
        v
    BANCO

**Nao ha uma linha de SQL clinico neste arquivo.** Toda consulta ao
conhecimento farmacologico passa por `busca.py` ou pelos motores; toda
escrita passa por `servicos.py`. A tela coleta, mostra e navega — nao avalia.

O botao "Analisar atendimento" chama `servicos.analisar`, que chama
`conciliar_atendimento`. Nenhuma regra e recalculada aqui, em JavaScript nem
em template.

Uso:
    python app/web.py            # http://127.0.0.1:5000
    PORT=8080 python app/web.py
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline"):
    sys.path.insert(0, str(RAIZ / _p))

from flask import (Flask, abort, flash, get_flashed_messages, jsonify, redirect,  # noqa: E402
                   render_template, request, url_for)
from werkzeug.exceptions import HTTPException  # noqa: E402

import busca                       # noqa: E402
import relatorio as rel            # noqa: E402
import rotulos as rot              # noqa: E402
import servicos as sv              # noqa: E402
from servicos import ErroDeUso     # noqa: E402

app = Flask(__name__, template_folder=str(RAIZ / "app" / "templates"),
            static_folder=str(RAIZ / "app" / "static"))
app.secret_key = os.environ.get("CONCILIADOR_SECRET", "conciliador-local-fase6")
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

ARQUIVO_LOG = RAIZ / "data" / "aplicacao.log"
ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(ARQUIVO_LOG), level=logging.INFO, encoding="utf-8",
    format="%(asctime)s  %(levelname)-7s  %(message)s")
log = logging.getLogger("conciliador")


# =====================================================================
# INFRAESTRUTURA
# =====================================================================
def com_banco(fn):
    """Abre e fecha a conexao, e traduz erro tecnico em mensagem legivel."""
    from functools import wraps

    @wraps(fn)
    def envelope(*args, **kwargs):
        try:
            con = sv.conectar()
        except FileNotFoundError as exc:
            log.error("banco indisponível: %s", exc)
            return render_template("erro.html", titulo="Banco indisponível",
                                   mensagem=str(exc)), 503
        try:
            return fn(con, *args, **kwargs)
        except HTTPException:
            # 404, 405 e afins sao respostas HTTP legitimas do proprio Flask.
            # Engoli-las no `except Exception` abaixo transformava um endereco
            # inexistente em erro interno 500 — encontrado pelo caso 14.5.
            raise
        except ErroDeUso as exc:
            # Erro do formulario: a mensagem foi escrita para ser lida, e
            # pertence ao atendimento em que o erro foi cometido.
            avisar(str(exc), "erro", kwargs.get("codigo"))
            destino = request.referrer or url_for("inicio")
            return redirect(destino)
        except Exception:                                   # noqa: BLE001
            # Erro tecnico: detalhe vai para o log, nunca para a tela.
            log.error("falha em %s\n%s", request.path, traceback.format_exc())
            return render_template(
                "erro.html", titulo="Erro interno",
                mensagem="Alguma coisa falhou ao processar esta página. O "
                         "detalhe técnico foi registrado em data/aplicacao.log. "
                         "Os dados do atendimento não foram perdidos."), 500
        finally:
            con.close()
    return envelope


def avisar(texto: str, categoria: str = "ok", codigo: str = None) -> None:
    """Mensagem de estado, PRESA ao atendimento que a gerou.

    A fila do Flask e da SESSAO, nao do atendimento: a mensagem espera ate
    que alguma pagina renderize. Com dois atendimentos abertos, a confirmacao
    de um sai na tela do outro — e "Posologia de Gliclazida 30 mg salva" na
    tela de quem toma varfarina e exatamente o tipo de confusao que este
    sistema existe para evitar. Achado pela Fase 9, eixo 1.

    O codigo do atendimento vai na CATEGORIA, depois de '@'. `base.html`
    mostra o que e da tela e DEVOLVE o resto para a fila — mensagem de outro
    atendimento nao e perdida, so nao aparece aqui.
    """
    flash(texto, "%s@%s" % (categoria, codigo) if codigo else categoria)


def mensagens_da_tela(codigo: str = None) -> list:
    """Le a fila uma vez, separa o que e desta tela e devolve o resto.

    Uma mensagem so e escondida quando a tela atual pertence a OUTRO
    atendimento. Numa tela sem atendimento — inicio, pagina de erro — tudo
    aparece: o risco e confundir o paciente A com um aviso do paciente B, e
    ali nao ha paciente nenhum. A primeira versao desta funcao escondia
    tambem no inicio, e com isso engolia justamente a mensagem "Atendimento
    X nao encontrado", que redireciona para la.
    """
    minhas, alheias = [], []
    for categoria, texto in get_flashed_messages(with_categories=True):
        dono = categoria.split("@")[1] if "@" in categoria else None
        de_outro = dono is not None and codigo is not None and dono != codigo
        (alheias if de_outro else minhas).append((categoria, texto))
    for categoria, texto in alheias:
        flash(texto, categoria)          # devolvidas: nao se perdem
    return [(c.split("@")[0], t) for c, t in minhas]


PASSOS = [
    ("paciente", "1. Paciente"),
    ("anamnese", "2. Anamnese"),
    ("medicamentos", "3. Medicamentos"),
    ("rotina", "4. Rotina"),
    ("itens", "5. Alimentos e plantas"),
    ("conciliacao", "6. Conciliação"),
    ("resultados", "7. Resultados"),
]


def contexto(con, codigo: str, etapa: str) -> dict:
    """Tudo que o cabecalho e a barra lateral precisam, em toda tela."""
    at = sv.exigir_atendimento(con, codigo)
    meds = sv.listar_medicamentos(con, codigo)
    return {
        "at": at, "codigo": codigo, "etapa": etapa, "passos": PASSOS,
        "rot": rot,
        "n_medicamentos": len(meds),
        "n_condicoes": len(sv.listar_condicoes(con, codigo)),
        "n_alergias": len(sv.listar_alergias(con, codigo)),
        "n_itens": len(sv.listar_itens(con, codigo)),
        "tem_rotina": bool(sv.listar_rotina(con, codigo)),
        "pendencias": sv.pendencias(con, codigo),
        "pode_analisar": sv.pode_analisar(con, codigo),
        "ultima": sv.ultima_conciliacao(con, codigo),
    }


@app.errorhandler(404)
def nao_encontrado(_e):
    return render_template("erro.html", titulo="Página não encontrada",
                           mensagem="O endereço pedido não existe nesta "
                                    "aplicação."), 404


@app.context_processor
def injetar():
    return {"rot": rot, "mensagens_da_tela": mensagens_da_tela}


# =====================================================================
# INICIO
# =====================================================================
@app.route("/")
@com_banco
def inicio(con):
    return render_template("inicio.html",
                           atendimentos=sv.listar_atendimentos(con))


@app.route("/novo", methods=["POST"])
@com_banco
def novo(con):
    codigo = sv.criar_atendimento(
        con, request.form.get("nome"), request.form.get("farmaceutico"),
        request.form.get("crf"))
    log.info("atendimento criado: %s", codigo)
    avisar("Atendimento %s iniciado." % codigo, "ok", codigo)
    return redirect(url_for("paciente", codigo=codigo))


# =====================================================================
# ETAPA 1 — PACIENTE
# =====================================================================
@app.route("/a/<codigo>/paciente", methods=["GET", "POST"])
@com_banco
def paciente(con, codigo):
    if request.method == "POST":
        f = request.form
        sv.salvar_paciente(
            con, codigo, nome=f.get("nome"),
            data_nascimento=f.get("data_nascimento"), sexo=f.get("sexo"),
            peso_kg=f.get("peso_kg"), altura_cm=f.get("altura_cm"),
            contato=f.get("contato"), observacao=f.get("observacao"),
            farmaceutico=f.get("farmaceutico"), crf=f.get("crf"))
        avisar("Dados do paciente salvos.", "ok", codigo)
        return redirect(url_for("anamnese", codigo=codigo))
    return render_template("paciente.html", **contexto(con, codigo, "paciente"))


# =====================================================================
# ETAPA 2 — ANAMNESE
# =====================================================================
@app.route("/a/<codigo>/anamnese")
@com_banco
def anamnese(con, codigo):
    ctx = contexto(con, codigo, "anamnese")
    ctx.update(
        condicoes=sv.listar_condicoes(con, codigo),
        alergias=sv.listar_alergias(con, codigo),
        habitos=sv.listar_habitos(con, codigo),
        grupos_condicao=busca.condicoes_por_grupo(con),
        lista_habitos=sv.HABITOS, situacoes=sv.SITUACOES_HABITO,
        gravidades=sv.GRAVIDADES_ALERGIA)
    return render_template("anamnese.html", **ctx)


@app.route("/a/<codigo>/condicao", methods=["POST"])
@com_banco
def add_condicao(con, codigo):
    sv.adicionar_condicao(con, codigo, request.form.get("doenca_id"),
                          request.form.get("descricao_livre"),
                          request.form.get("desde"))
    avisar("Condição registrada.", "ok", codigo)
    return redirect(url_for("anamnese", codigo=codigo))


@app.route("/a/<codigo>/condicao/<int:cid>/remover", methods=["POST"])
@com_banco
def del_condicao(con, codigo, cid):
    sv.remover_condicao(con, codigo, cid)
    avisar("Condição removida.", "ok", codigo)
    return redirect(url_for("anamnese", codigo=codigo))


@app.route("/a/<codigo>/alergia", methods=["POST"])
@com_banco
def add_alergia(con, codigo):
    escolha = (request.form.get("substancia_id") or "").strip()
    sv.adicionar_alergia(con, codigo, substancia_id=escolha or None,
                         descricao_livre=request.form.get("descricao_livre"),
                         reacao=request.form.get("reacao"),
                         gravidade=request.form.get("gravidade")
                         or "NAO_INFORMADA")
    avisar("Alergia registrada.", "ok", codigo)
    return redirect(url_for("anamnese", codigo=codigo))


@app.route("/a/<codigo>/alergia/<int:aid>/remover", methods=["POST"])
@com_banco
def del_alergia(con, codigo, aid):
    sv.remover_alergia(con, codigo, aid)
    avisar("Alergia removida.", "ok", codigo)
    return redirect(url_for("anamnese", codigo=codigo))


@app.route("/a/<codigo>/habitos", methods=["POST"])
@com_banco
def salvar_habitos(con, codigo):
    for habito, _rotulo in sv.HABITOS:
        situacao = request.form.get("situacao_" + habito)
        if not situacao:
            continue
        sv.salvar_habito(con, codigo, habito, situacao,
                         request.form.get("quantidade_" + habito),
                         request.form.get("frequencia_" + habito))
    avisar("Hábitos registrados.", "ok", codigo)
    return redirect(url_for("anamnese", codigo=codigo))


# =====================================================================
# ETAPA 3 — MEDICAMENTOS
# =====================================================================
@app.route("/a/<codigo>/medicamentos")
@com_banco
def medicamentos(con, codigo):
    ctx = contexto(con, codigo, "medicamentos")
    termo = (request.args.get("q") or "").strip()
    ctx.update(medicamentos=sv.listar_medicamentos(con, codigo),
               resultados=busca.buscar_medicamento(con, termo) if termo else [],
               termo=termo, listas=sv.LISTAS, origens=sv.ORIGENS)
    return render_template("medicamentos.html", **ctx)


@app.route("/a/<codigo>/medicamento", methods=["POST"])
@com_banco
def add_medicamento(con, codigo):
    f = request.form
    grupo = sv.adicionar_medicamento(
        con, codigo, nome_relatado=f.get("nome_relatado"),
        escolha=f.get("escolha"), lista=f.get("lista") or "RELATADA",
        origem=f.get("origem") or "PRESCRITO")
    avisar("Medicamento adicionado. Informe a posologia.", "ok", codigo)
    return redirect(url_for("posologia", codigo=codigo, grupo_id=grupo))


@app.route("/a/<codigo>/medicamento/<int:grupo_id>/remover", methods=["POST"])
@com_banco
def del_medicamento(con, codigo, grupo_id):
    tinha_analise = sv.ultima_conciliacao(con, codigo) is not None
    sv.remover_medicamento(con, codigo, grupo_id)
    avisar("Medicamento removido." + (" A análise gravada ficou desatualizada: "
          "a tela já mostra o resultado recalculado, e vale gravar de novo "
          "com 'Analisar atendimento'." if tinha_analise else ""), "ok", codigo)
    return redirect(url_for("medicamentos", codigo=codigo))


@app.route("/a/<codigo>/medicamento/<int:grupo_id>/lista", methods=["POST"])
@com_banco
def mover_medicamento(con, codigo, grupo_id):
    sv.mover_medicamento(con, codigo, grupo_id, request.form.get("lista"))
    avisar("Item movido de lista.", "ok", codigo)
    return redirect(url_for("medicamentos", codigo=codigo))


# =====================================================================
# ETAPA 3b — POSOLOGIA
# =====================================================================
@app.route("/a/<codigo>/posologia/<int:grupo_id>", methods=["GET", "POST"])
@com_banco
def posologia(con, codigo, grupo_id):
    grupo = sv.obter_grupo(con, codigo, grupo_id)
    if request.method == "POST":
        f = request.form
        horas = [h for h in f.getlist("horario") if (h or "").strip()]
        sv.salvar_posologia(
            con, codigo, grupo_id, dose_valor=f.get("dose_valor"),
            dose_unidade=f.get("dose_unidade"),
            vezes_por_dia=f.get("vezes_por_dia"),
            intervalo_horas=f.get("intervalo_horas"),
            via_administracao=f.get("via_administracao"),
            duracao_dias=f.get("duracao_dias"),
            data_inicio=f.get("data_inicio"),
            data_fim_prevista=f.get("data_fim_prevista"),
            uso_continuo=bool(f.get("uso_continuo")),
            se_necessario=bool(f.get("se_necessario")),
            condicao_uso=f.get("condicao_uso"),
            texto_original=f.get("texto_original"), horarios=horas)
        avisar("Posologia de %s salva." % grupo.nome_relatado, "ok", codigo)
        return redirect(url_for("medicamentos", codigo=codigo))
    ctx = contexto(con, codigo, "medicamentos")
    detalhe = (busca.detalhar_apresentacao(con, grupo.apresentacao_id)
               if grupo.apresentacao_id else None)
    ctx.update(grupo=grupo, detalhe=detalhe)
    return render_template("posologia.html", **ctx)


# =====================================================================
# ETAPA 4 — ROTINA
# =====================================================================
@app.route("/a/<codigo>/rotina", methods=["GET", "POST"])
@com_banco
def rotina(con, codigo):
    if request.method == "POST":
        sv.salvar_rotina(con, codigo,
                         {e: request.form.get(e) for e, _r in sv.EVENTOS_ROTINA})
        avisar("Rotina registrada.", "ok", codigo)
        return redirect(url_for("itens", codigo=codigo))
    ctx = contexto(con, codigo, "rotina")
    ctx.update(eventos=sv.EVENTOS_ROTINA, valores=sv.listar_rotina(con, codigo))
    return render_template("rotina.html", **ctx)


# =====================================================================
# ETAPA 5 — ALIMENTOS, PLANTAS E SUPLEMENTOS
# =====================================================================
@app.route("/a/<codigo>/itens")
@com_banco
def itens(con, codigo):
    ctx = contexto(con, codigo, "itens")
    registrados = sv.listar_itens(con, codigo)
    ja = {i["item_id"] for i in registrados if i["item_id"]}
    ctx.update(
        registrados=registrados, ja=ja,
        catalogo={g: busca.buscar_item(con, grupo=g)
                  for g in ("ALIMENTO", "PLANTA", "SUPLEMENTO")},
        frequencias=sv.FREQUENCIAS_ITEM)
    return render_template("itens.html", **ctx)


@app.route("/a/<codigo>/item", methods=["POST"])
@com_banco
def add_item(con, codigo):
    sv.adicionar_item(con, codigo, request.form.get("item_id"),
                      request.form.get("nome_relatado"),
                      request.form.get("frequencia") or "NAO_INFORMADA",
                      request.form.get("horario_habitual"))
    avisar("Item registrado.", "ok", codigo)
    return redirect(url_for("itens", codigo=codigo))


@app.route("/a/<codigo>/item/<int:rid>/remover", methods=["POST"])
@com_banco
def del_item(con, codigo, rid):
    sv.remover_item(con, codigo, rid)
    avisar("Item removido.", "ok", codigo)
    return redirect(url_for("itens", codigo=codigo))


# =====================================================================
# ETAPA 6 — CONCILIACAO
# =====================================================================
@app.route("/a/<codigo>/conciliacao")
@com_banco
def conciliacao(con, codigo):
    ctx = contexto(con, codigo, "conciliacao")
    res = sv.resultado_atual(con, codigo)
    anotacoes = sv.listar_anotacoes(con, codigo)
    pares = [{"par": p, "chave": sv.chave_divergencia(p),
              "anotacao": anotacoes.get(("DIVERGENCIA",
                                         sv.chave_divergencia(p)))}
             for p in res.pares]
    ctx.update(
        pares=pares, res=res,
        prescritos=sv.listar_medicamentos(con, codigo, "PRESCRITA"),
        relatados=[g for g in sv.listar_medicamentos(con, codigo)
                   if g.lista in ("RELATADA", "EM_USO")],
        anteriores=[g for g in sv.listar_medicamentos(con, codigo)
                    if g.lista in ("ANTERIOR", "HISTORICO")],
        listas=sv.LISTAS)
    return render_template("conciliacao.html", **ctx)


@app.route("/a/<codigo>/divergencia/registrar", methods=["POST"])
@com_banco
def registrar_divergencia(con, codigo):
    f = request.form
    sv.registrar_anotacao(
        con, codigo, "DIVERGENCIA", f.get("chave"),
        situacao=f.get("situacao") or "REVISADO",
        intencionalidade=f.get("intencionalidade") or None,
        observacao=f.get("observacao"), profissional=f.get("profissional"),
        crf=f.get("crf"))
    avisar("Avaliação da divergência registrada.", "ok", codigo)
    return redirect(url_for("conciliacao", codigo=codigo))


# =====================================================================
# ANALISE E RESULTADOS
# =====================================================================
@app.route("/a/<codigo>/analisar", methods=["POST"])
@com_banco
def analisar(con, codigo):
    res = sv.analisar(con, codigo, persistir=True)
    log.info("análise de %s: %d achados", codigo, res.resumo["achados"])
    avisar("Análise concluída: %d achado(s)." % res.resumo["achados"],
           "ok", codigo)
    return redirect(url_for("resultados", codigo=codigo))


@app.route("/a/<codigo>/resultados")
@com_banco
def resultados(con, codigo):
    ctx = contexto(con, codigo, "resultados")
    res = sv.resultado_atual(con, codigo)
    anotacoes = sv.listar_anotacoes(con, codigo)

    filtros = {
        "prioridade": request.args.get("prioridade") or "",
        "tipo": request.args.get("tipo") or "",
        "item": (request.args.get("item") or "").strip().lower(),
        "fonte": request.args.get("fonte") or "",
        "status": request.args.get("status") or "",
        "revisao": request.args.get("revisao") or "",
    }

    def passa(a):
        if filtros["prioridade"] and a.prioridade != filtros["prioridade"]:
            return False
        if filtros["tipo"] and a.tipo != filtros["tipo"]:
            return False
        if filtros["status"] and a.status_informacao != filtros["status"]:
            return False
        if filtros["fonte"] and filtros["fonte"] not in (a.fonte or ""):
            return False
        if filtros["revisao"] == "PENDENTE" and \
                ("ACHADO", a.grupo_chave) in anotacoes:
            return False
        if filtros["revisao"] == "REVISADO" and \
                ("ACHADO", a.grupo_chave) not in anotacoes:
            return False
        if filtros["item"]:
            alvo = " ".join(filter(None, [a.item_a, a.item_b])).lower()
            if filtros["item"] not in alvo:
                return False
        return True

    visiveis = [a for a in res.achados if passa(a)]
    # DOCUMENTADO e PREVISTO vao em listas separadas e nunca se encontram na
    # mesma seccao da tela. A previsao nao concorre por prioridade com o que
    # tem documento atras: ela tem bloco proprio, no fim, com aviso.
    documentados = [a for a in visiveis if a.natureza != "PREVISTO"]
    previstos = [a for a in visiveis if a.natureza == "PREVISTO"]
    por_prioridade = {p: [a for a in documentados if a.prioridade == p]
                      for p in rot.ORDEM_PRIORIDADE}
    ctx.update(
        res=res, visiveis=visiveis, por_prioridade=por_prioridade,
        previstos=previstos, documentados=documentados,
        filtros=filtros, anotacoes=anotacoes,
        tipos=sorted({a.tipo for a in res.achados}),
        fontes=sorted({a.fonte for a in res.achados if a.fonte}),
        estados=sorted({a.status_informacao for a in res.achados}),
        nao_avaliado=_agrupar_nao_avaliado(res))
    return render_template("resultados.html", **ctx)


def _agrupar_nao_avaliado(res) -> dict:
    saida = {}
    for n in res.nao_avaliado:
        saida.setdefault(n.motivo, []).append(n)
    return saida


@app.route("/a/<codigo>/achado")
@com_banco
def achado(con, codigo):
    chave = request.args.get("chave") or ""
    ctx = contexto(con, codigo, "resultados")
    res = sv.resultado_atual(con, codigo)
    alvo = next((a for a in res.achados if a.grupo_chave == chave), None)
    if alvo is None:
        alvo = next((a for a in res.achados_agrupados
                     if a.grupo_chave == chave), None)
    if alvo is None:
        abort(404)
    agrupados = [a for a in res.achados_agrupados if a.agrupado_em == chave]
    anotacoes = sv.listar_anotacoes(con, codigo)
    ctx.update(achado=alvo, agrupados=agrupados,
               anotacao=anotacoes.get(("ACHADO", chave)),
               previsao=(sv.detalhe_previsao(con, alvo.origem_afirmacao)
                         if alvo.natureza == "PREVISTO" else None),
               cadeia=alvo.por_que_apareceu().split("\n"))
    return render_template("achado.html", **ctx)


@app.route("/a/<codigo>/achado/revisar", methods=["POST"])
@com_banco
def revisar_achado(con, codigo):
    f = request.form
    sv.registrar_anotacao(
        con, codigo, "ACHADO", f.get("chave"),
        situacao=f.get("situacao") or "REVISADO",
        observacao=f.get("observacao"), profissional=f.get("profissional"),
        crf=f.get("crf"))
    avisar("Revisão registrada.", "ok", codigo)
    return redirect(url_for("achado", codigo=codigo, chave=f.get("chave")))


# =====================================================================
# RELATORIO
# =====================================================================
@app.route("/a/<codigo>/relatorio")
@com_banco
def relatorio(con, codigo):
    ctx = contexto(con, codigo, "resultados")
    ctx.update(dados=rel.montar_relatorio(con, codigo))
    return render_template("relatorio.html", **ctx)


@app.route("/a/<codigo>/relatorio.txt")
@com_banco
def relatorio_texto(con, codigo):
    texto = rel.relatorio_em_texto(rel.montar_relatorio(con, codigo))
    return app.response_class(texto, mimetype="text/plain; charset=utf-8")


@app.route("/a/<codigo>/concluir", methods=["POST"])
@com_banco
def concluir(con, codigo):
    sv.concluir_atendimento(con, codigo)
    avisar("Atendimento %s concluído." % codigo, "ok", codigo)
    return redirect(url_for("relatorio", codigo=codigo))


@app.route("/a/<codigo>/reabrir", methods=["POST"])
@com_banco
def reabrir(con, codigo):
    sv.reabrir_atendimento(con, codigo)
    avisar("Atendimento reaberto.", "ok", codigo)
    return redirect(url_for("paciente", codigo=codigo))


# =====================================================================
# BUSCA (autocompletar)
# =====================================================================
@app.route("/api/busca/medicamento")
@com_banco
def api_medicamento(con):
    termo = request.args.get("q") or ""
    return jsonify([{"chave": r.chave, "rotulo": r.rotulo,
                     "detalhe": r.detalhe, "confianca": r.confianca,
                     "reconhecimento": r.reconhecimento}
                    for r in busca.buscar_medicamento(con, termo, 12)])


@app.route("/api/busca/substancia")
@com_banco
def api_substancia(con):
    termo = request.args.get("q") or ""
    return jsonify([{"id": r.substancia_id, "rotulo": r.rotulo,
                     "detalhe": r.detalhe}
                    for r in busca.buscar_substancia(con, termo, 12)
                    if r.substancia_id])


@app.route("/api/busca/condicao")
@com_banco
def api_condicao(con):
    termo = request.args.get("q") or ""
    return jsonify([{"id": o.id, "rotulo": o.nome, "detalhe": o.grupo or ""}
                    for o in busca.buscar_condicao(con, termo, 20)])


@app.route("/api/busca/item")
@com_banco
def api_item(con):
    return jsonify([{"id": o.id, "rotulo": o.nome,
                     "detalhe": rot.rotular(rot.TIPO_ITEM, o.tipo)}
                    for o in busca.buscar_item(con, request.args.get("q") or "",
                                               request.args.get("grupo"), 20)])


def main() -> int:
    porta = int(os.environ.get("PORT", "5000"))
    print("Conciliador de Medicamentos — aplicação do farmacêutico")
    print("  banco:   %s" % sv.BANCO)
    print("  log:     %s" % ARQUIVO_LOG)
    print("  abra em: http://127.0.0.1:%d" % porta)
    print("  (Ctrl+C encerra)")
    app.run(host="127.0.0.1", port=porta, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
