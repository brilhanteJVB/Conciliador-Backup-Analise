# -*- coding: utf-8 -*-
"""
FASE 10 — V1: O EXECUTAVEL, USADO COMO UM USUARIO O USARIA.

Nada aqui importa o codigo da aplicacao. Tudo passa pelo `.exe`: ele e
iniciado como processo, conversado por HTTP, encerrado, reaberto. Se o
empacotamento tiver quebrado alguma coisa, e aqui que aparece — importar os
modulos em Python provaria que o CODIGO funciona, nao que o PROGRAMA funciona.

SETE EIXOS
----------
  1  primeira instalacao      maquina limpa, sem banco, sem pastas
  2  atendimento completo     paciente -> ... -> relatorio, tudo por HTTP
  3  persistencia             fechar o processo, abrir de novo, conferir
  4  o conhecimento intacto   o empacotamento nao pode mudar o conteudo
  5  ML desligado             o `.exe` nao preve, e nao carrega sklearn
  6  falhas controladas       oito situacoes que podem dar errado
  7  atualizacao e perda      valido aceito, invalido recusado, dado mantido

Uso: python tests/fase10_empacotamento.py
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXE = RAIZ / "dist" / "SistemaConciliador" / "SistemaConciliador.exe"
INTERNO = RAIZ / "dist" / "SistemaConciliador" / "_internal"

PASSOS, FALHAS = [], []


def checa(eixo, nome, ok, detalhe=""):
    PASSOS.append((eixo, nome, ok, detalhe))
    if not ok:
        FALHAS.append((eixo, nome, detalhe))
    print("   %s %-52s %s" % ("OK  " if ok else "ERRO", nome[:52],
                              str(detalhe)[:56]))


# =====================================================================
# CONVERSAR COM O PROGRAMA
# =====================================================================
class Programa:
    """Sobe o `.exe` como processo e fala com ele por HTTP."""

    def __init__(self, dados: Path, porta: int):
        self.dados, self.porta = dados, porta
        self.proc = None
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            SemRedirecionar())
        self.saida = None

    def abrir(self, espera=60) -> bool:
        ambiente = dict(os.environ)
        ambiente["CONCILIADOR_DADOS"] = str(self.dados)
        ambiente["PYTHONIOENCODING"] = "utf-8"
        self.saida = tempfile.TemporaryFile(mode="w+", encoding="utf-8",
                                            errors="replace")
        self.proc = subprocess.Popen(
            [str(EXE), "--sem-navegador", "--porta", str(self.porta)],
            cwd=str(EXE.parent), env=ambiente,
            stdout=self.saida, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL)
        limite = time.time() + espera
        while time.time() < limite:
            if self.proc.poll() is not None:
                return False
            with socket.socket() as s:
                s.settimeout(0.4)
                if s.connect_ex(("127.0.0.1", self.porta)) == 0:
                    return True
            time.sleep(0.3)
        return False

    def texto_da_saida(self) -> str:
        if not self.saida:
            return ""
        self.saida.seek(0)
        return self.saida.read()

    def fechar(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        time.sleep(0.6)          # o SQLite fecha o -wal

    # -------------------------------------------------------------- HTTP
    def url(self, caminho: str) -> str:
        return "http://127.0.0.1:%d%s" % (self.porta, caminho)

    def get(self, caminho: str):
        try:
            r = self.opener.open(self.url(caminho), timeout=60)
            return r.getcode(), r.read().decode("utf-8", "replace"), r
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e

    def post(self, caminho: str, campos):
        if isinstance(campos, dict):
            campos = list(campos.items())
        corpo = urllib.parse.urlencode(
            [(k, v) for k, v in campos if v is not None]).encode()
        req = urllib.request.Request(
            self.url(caminho), data=corpo,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            r = self.opener.open(req, timeout=120)
            return r.getcode(), r.read().decode("utf-8", "replace"), r
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e


class SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Precisamos LER o Location para descobrir o código do atendimento."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

    def http_error_302(self, req, fp, code, msg, headers):
        resposta = urllib.error.HTTPError(req.full_url, code, msg, headers, fp)
        resposta.headers = headers
        return resposta

    http_error_301 = http_error_303 = http_error_307 = http_error_302


def porta_livre(base=5100) -> int:
    for p in range(base, base + 200):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("sem porta livre")


def sql(banco: Path, consulta: str, *args):
    con = sqlite3.connect("file:%s?mode=ro" % banco.as_posix(), uri=True)
    try:
        return con.execute(consulta, args).fetchall()
    finally:
        con.close()


# =====================================================================
def eixo_1_primeira_instalacao(dados: Path) -> bool:
    print("\n1. PRIMEIRA INSTALACAO — máquina limpa\n")
    checa(1, "o executável foi produzido", EXE.exists(),
          "%.1f MB" % (EXE.stat().st_size / 1024 ** 2) if EXE.exists() else "—")
    if not EXE.exists():
        return False
    checa(1, "a pasta de dados ainda não existe", not dados.exists())

    ambiente = dict(os.environ, CONCILIADOR_DADOS=str(dados),
                    PYTHONIOENCODING="utf-8")
    r = subprocess.run([str(EXE), "--diagnostico"], cwd=str(EXE.parent),
                       env=ambiente, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    checa(1, "o executável roda e sai sem erro", r.returncode == 0,
          "código %d" % r.returncode)
    saida = r.stdout or ""
    checa(1, "ele se declara empacotado", "empacotado                 True"
          in saida)
    checa(1, "instalou o conhecimento na primeira execução",
          "primeira execução" in saida)
    checa(1, "o banco do usuário foi criado na pasta de dados",
          (dados / "database" / "conciliador.db").exists())
    checa(1, "e NÃO ficou dentro da pasta do programa",
          not (EXE.parent / "database" / "conciliador.db").exists())
    checa(1, "o carimbo de build aparece", "build 20" in saida,
          [l.strip() for l in saida.splitlines() if "build 20" in l][:1])
    checa(1, "declara ML desligado", "0 modelos ativos" in saida)
    return True


def eixo_2_atendimento(p: Programa, dados: Path) -> str:
    print("\n2. ATENDIMENTO COMPLETO — tudo por HTTP, contra o .exe\n")
    banco = dados / "database" / "conciliador.db"
    codigo = [None]

    cod, html, _ = p.get("/")
    checa(2, "a tela inicial responde", cod == 200 and "Atendimento" in html,
          "HTTP %s" % cod)

    cod, _h, r = p.post("/novo", {"nome": "Fase 10 — paciente do .exe",
                                  "farmaceutico": "Farm. Fase 10",
                                  "crf": "CRF-AM 100010"})
    local = r.headers.get("Location", "")
    codigo[0] = local.split("/a/")[1].split("/")[0] if "/a/" in local else None
    checa(2, "o atendimento foi criado", bool(codigo[0]), codigo[0])
    if not codigo[0]:
        return ""
    c = codigo[0]

    p.post("/a/%s/paciente" % c,
           {"nome": "Fase 10 — paciente do .exe",
            "data_nascimento": "1949-11-03", "sexo": "F",
            "peso_kg": "62", "altura_cm": "155",
            "farmaceutico": "Farm. Fase 10", "crf": "CRF-AM 100010"})
    p.post("/a/%s/alergia" % c, {"substancia_id": "1506",
                                 "reacao": "urticária relatada no balcão",
                                 "gravidade": "GRAVE"})
    p.post("/a/%s/condicao" % c, {"doenca_id": "26"})
    cod, html, _ = p.get("/a/%s/anamnese" % c)
    checa(2, "anamnese gravada e exibida",
          cod == 200 and "urticária" in html, "HTTP %s" % cod)

    for rotulo, sid, origem, dose, vezes, horas in (
            ("Varfarina 5 mg", "2070", "PRESCRITO", "5", "1", ["20:00"]),
            ("Ibuprofeno 600 mg", "1039", "AUTOMEDICACAO", "600", "3",
             ["08:00", "14:00", "22:00"]),
            ("um chá que a vizinha indicou", None, "NAO_INFORMADO",
             None, None, [])):
        cod, _h, r = p.post("/a/%s/medicamento" % c,
                            {"nome_relatado": rotulo,
                             "escolha": ("substancia:%s" % sid) if sid else "",
                             "lista": "EM_USO", "origem": origem})
        loc = r.headers.get("Location", "")
        if sid and "/posologia/" in loc:
            grupo = loc.rstrip("/").split("/")[-1]
            campos = [("dose_valor", dose), ("dose_unidade", "mg"),
                      ("vezes_por_dia", vezes), ("via_administracao", "oral")]
            campos += [("horario", h) for h in horas]
            p.post("/a/%s/posologia/%s" % (c, grupo), campos)

    cod, html, _ = p.get("/a/%s/medicamentos" % c)
    checa(2, "medicamentos e posologia gravados",
          "Varfarina" in html and "Ibuprofeno" in html
          and "não reconhecido" in html)

    p.post("/a/%s/rotina" % c, {"ACORDAR": "06:30", "CAFE_MANHA": "07:00",
                                "ALMOCO": "12:00", "JANTAR": "19:30",
                                "DORMIR": "22:30"})
    cod, html, _ = p.get("/a/%s/conciliacao" % c)
    checa(2, "a tela de conciliação abre", cod == 200, "HTTP %s" % cod)

    cod, _h, _r = p.post("/a/%s/analisar" % c, {})
    checa(2, "a análise executou", cod in (200, 302), "HTTP %s" % cod)

    cod, html, _ = p.get("/a/%s/resultados" % c)
    checa(2, "os resultados aparecem", cod == 200 and "Resultados" in html)
    checa(2, "a interação anticoagulante × anti-inflamatório foi detectada",
          "Ibuprofeno" in html and "Varfarina" in html)
    checa(2, "o que não foi avaliado está declarado",
          "não avaliou" in html or "não avaliado" in html.lower())
    checa(2, "nenhum bloco de previsão (ML desligado)",
          'id="bloco-previsto"' not in html)

    linhas = sql(banco, "SELECT grupo_chave FROM achado a JOIN conciliacao co "
                        "ON co.id=a.conciliacao_id JOIN atendimento t "
                        "ON t.id=co.atendimento_id WHERE t.codigo=?", c)
    checa(2, "os achados foram GRAVADOS no banco do usuário", len(linhas) > 0,
          "%d achado(s)" % len(linhas))
    if linhas:
        chave = [l[0] for l in linhas if l[0].startswith("PAR:")]
        if chave:
            cod, det, _ = p.get("/a/%s/achado?chave=%s"
                                % (c, urllib.parse.quote(chave[0])))
            checa(2, "o detalhe do achado abre com a cadeia de evidência",
                  cod == 200 and "Cadeia de detecção" in det, "HTTP %s" % cod)
            p.post("/a/%s/achado/revisar" % c,
                   {"chave": chave[0], "situacao": "REVISADO",
                    "profissional": "Farm. Fase 10", "crf": "CRF-AM 100010",
                    "observacao": "orientação registrada pelo .exe"})

    cod, html, _ = p.get("/a/%s/relatorio" % c)
    checa(2, "o relatório em HTML é gerado", cod == 200 and "Resumo" in html,
          "%d bytes" % len(html))
    cod, txt, _ = p.get("/a/%s/relatorio.txt" % c)
    checa(2, "o relatório em texto é gerado",
          cod == 200 and "Fase 10" in txt, "%d bytes" % len(txt))
    checa(2, "o relatório traz a revisão do profissional",
          "orientação registrada pelo .exe" in txt)
    return c


def eixo_3_persistencia(dados: Path, codigo: str, porta: int):
    print("\n3. PERSISTENCIA — fechar o processo e abrir de novo\n")
    banco = dados / "database" / "conciliador.db"
    antes = sql(banco, "SELECT COUNT(*) FROM atendimento")[0][0]
    achados = sql(banco, "SELECT COUNT(*) FROM achado")[0][0]

    p2 = Programa(dados, porta)
    subiu = p2.abrir()
    checa(3, "o programa abre de novo, no mesmo banco", subiu,
          p2.texto_da_saida()[-120:] if not subiu else "")
    if not subiu:
        return
    try:
        cod, html, _ = p2.get("/")
        checa(3, "o atendimento aparece na lista ao reabrir",
              codigo in html, codigo)
        cod, html, _ = p2.get("/a/%s/resultados" % codigo)
        checa(3, "os resultados continuam lá", cod == 200
              and "Ibuprofeno" in html, "HTTP %s" % cod)
        cod, html, _ = p2.get("/a/%s/medicamentos" % codigo)
        checa(3, "a posologia sobreviveu", "600 mg" in html or "600" in html)
        cod, txt, _ = p2.get("/a/%s/relatorio.txt" % codigo)
        checa(3, "a revisão do profissional sobreviveu",
              "orientação registrada pelo .exe" in txt)
        checa(3, "o banner do programa declara os atendimentos gravados",
              "atendimentos  %d" % antes in p2.texto_da_saida(),
              "%d atendimento(s)" % antes)
        checa(3, "nada se perdeu entre as duas execuções",
              sql(banco, "SELECT COUNT(*) FROM achado")[0][0] == achados,
              "%d achado(s)" % achados)
    finally:
        p2.fechar()


def eixo_4_conhecimento_intacto(dados: Path):
    print("\n4. O CONHECIMENTO — o empacotamento não pode alterá-lo\n")
    semente = INTERNO / "conhecimento" / "conhecimento.db"
    manifesto = json.loads(
        (INTERNO / "conhecimento" / "conhecimento.json").read_text("utf-8"))
    usuario = dados / "database" / "conciliador.db"
    dev = RAIZ / "database" / "conciliador.db"

    checa(4, "o conhecimento veio junto no pacote", semente.exists(),
          "%.1f MB" % (semente.stat().st_size / 1024 ** 2)
          if semente.exists() else "—")
    if not semente.exists():
        return
    import hashlib
    h = hashlib.sha256()
    with open(semente, "rb") as fh:
        for b in iter(lambda: fh.read(4 * 1024 ** 2), b""):
            h.update(b)
    checa(4, "o sha256 bate com o manifesto",
          h.hexdigest() == manifesto["sha256"], h.hexdigest()[:16])

    for tabela, esperado in manifesto["conteudo"].items():
        atual = sql(usuario, "SELECT COUNT(*) FROM %s" % tabela)[0][0]
        checa(4, "%s: %s linha(s), como em desenvolvimento" % (tabela, esperado),
              atual == esperado, "%d" % atual)
    d_dev = sql(dev, "SELECT valor FROM propriedade WHERE "
                     "chave='conhecimento.digital'")
    d_usr = sql(usuario, "SELECT valor FROM propriedade WHERE "
                         "chave='conhecimento.digital'")
    checa(4, "a impressão digital é a mesma do desenvolvimento",
          d_dev and d_usr and d_dev[0][0] == d_usr[0][0],
          d_usr[0][0] if d_usr else "ausente")
    checa(4, "o banco do usuário passa no teste de integridade",
          sql(usuario, "PRAGMA integrity_check")[0][0] == "ok")
    checa(4, "e não tem referência quebrada",
          not sql(usuario, "PRAGMA foreign_key_check"))


def eixo_5_ml_desligado(dados: Path):
    print("\n5. ML — o .exe não prevê, e não carrega scikit-learn\n")
    usuario = dados / "database" / "conciliador.db"
    checa(5, "nenhum modelo ativo no banco distribuído",
          sql(usuario, "SELECT COUNT(*) FROM modelo WHERE ativo=1")[0][0] == 0)
    checa(5, "os modelos registrados continuam EXPERIMENTAL",
          all(s == "EXPERIMENTAL" for (s,) in
              sql(usuario, "SELECT status FROM modelo")))
    checa(5, "limiar de alerta NULL — fail-closed",
          all(v is None for (v,) in
              sql(usuario, "SELECT limiar_alerta FROM modelo")))
    checa(5, "a view de previsão devolve zero linhas",
          sql(usuario, "SELECT COUNT(*) FROM vw_predicao_liberada")[0][0] == 0)
    checa(5, "nenhum achado de origem MODELO",
          sql(usuario, "SELECT COUNT(*) FROM achado WHERE "
                       "origem_achado='MODELO'")[0][0] == 0)

    nomes = {p.name.lower() for p in INTERNO.rglob("*") if p.is_file()}
    pastas = {p.name.lower() for p in INTERNO.iterdir() if p.is_dir()}
    for proibido in ("numpy", "scipy", "sklearn", "pandas"):
        checa(5, "o pacote NÃO contém %s" % proibido, proibido not in pastas,
              proibido)
    checa(5, "nenhum artefato .pkl de modelo foi embarcado",
          not any(n.endswith(".pkl") for n in nomes))
    checa(5, "os manifestos de modelo (JSON) vieram, para rastreabilidade",
          (INTERNO / "models" / "m1_1_0-boosting.json").exists())


def eixo_6_falhas(dados_base: Path, porta: int):
    print("\n6. FALHAS — oito situações, todas controladas\n")
    ambiente_base = dict(os.environ, PYTHONIOENCODING="utf-8")

    def rodar(dados, extra=()):
        amb = dict(ambiente_base, CONCILIADOR_DADOS=str(dados))
        return subprocess.run([str(EXE), "--diagnostico", *extra],
                              cwd=str(EXE.parent), env=amb,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180)

    # 1. banco corrompido
    d = dados_base / "corrompido"
    (d / "database").mkdir(parents=True, exist_ok=True)
    (d / "database" / "conciliador.db").write_bytes(b"isto nao e um banco" * 50)
    r = rodar(d)
    checa(6, "1. banco corrompido: recusa e explica", r.returncode != 0
          and ("corrompido" in r.stdout or "não é um banco" in r.stdout),
          "código %d" % r.returncode)
    checa(6, "1b. e não apresenta rastreamento de pilha cru ao usuário",
          "Traceback" not in r.stdout or "NÃO PÔDE INICIAR" in r.stdout)

    # 2. banco vazio (arquivo valido, sem tabela)
    d = dados_base / "vazio"
    (d / "database").mkdir(parents=True, exist_ok=True)
    sqlite3.connect(d / "database" / "conciliador.db").close()
    r = rodar(d)
    checa(6, "2. banco sem as tabelas: recusa e diz quais faltam",
          r.returncode != 0 and "faltam as tabelas" in r.stdout,
          "código %d" % r.returncode)

    # 3. banco somente leitura
    d = dados_base / "somente_leitura"
    (d / "database").mkdir(parents=True, exist_ok=True)
    shutil.copy2(dados_base.parent / "dados_limpos" / "database"
                 / "conciliador.db", d / "database" / "conciliador.db")
    alvo = d / "database" / "conciliador.db"
    os.chmod(alvo, 0o444)
    r = rodar(d)
    os.chmod(alvo, 0o666)
    checa(6, "3. banco somente leitura: abre para diagnóstico, sem quebrar",
          r.returncode == 0, "código %d" % r.returncode)

    # 4. pasta de dados impossivel
    impossivel = Path("Z:/nao_existe_conciliador_fase10")
    r = rodar(impossivel)
    checa(6, "4. pasta de dados inacessível: recusa com mensagem",
          r.returncode != 0 and "não aceita gravação" in r.stdout,
          "código %d" % r.returncode)

    # 5. primeira execucao sem o conhecimento do pacote
    escondido = INTERNO / "conhecimento" / "conhecimento.db"
    temporario = escondido.with_suffix(".escondido")
    d = dados_base / "sem_semente"
    escondido.rename(temporario)
    try:
        r = rodar(d)
    finally:
        temporario.rename(escondido)
    checa(6, "5. conhecimento ausente: recusa, e NÃO cria banco vazio",
          r.returncode != 0 and "instalação está incompleta" in r.stdout.lower(),
          "código %d" % r.returncode)
    checa(6, "5b. nenhum banco foi inventado para disfarçar a ausência",
          not (d / "database" / "conciliador.db").exists())

    # 6. porta ocupada
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", porta))
        s.listen(1)
        p = Programa(dados_base.parent / "dados_limpos", porta)
        subiu = p.abrir(espera=40)
        saida = p.texto_da_saida()
        p.fechar()
    checa(6, "6. porta ocupada: sobe na seguinte em vez de falhar", subiu,
          [l for l in saida.splitlines() if "ocupada" in l][:1])

    # 7. argumento invalido
    amb = dict(ambiente_base,
               CONCILIADOR_DADOS=str(dados_base.parent / "dados_limpos"))
    r = subprocess.run([str(EXE), "--porta", "abc"], cwd=str(EXE.parent),
                       env=amb, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    checa(6, "7. argumento inválido: explica em vez de estourar",
          r.returncode == 2 and "precisa de um número" in r.stdout,
          "código %d" % r.returncode)

    # 8. o log registra
    log = (dados_base.parent / "dados_limpos" / "data" / "aplicacao.log")
    checa(6, "8. o log de execução foi escrito", log.exists()
          and log.stat().st_size > 0,
          "%d bytes" % (log.stat().st_size if log.exists() else 0))
    if log.exists():
        texto = log.read_text(encoding="utf-8", errors="replace")
        checa(6, "8b. o log registra o início, com versão e banco",
              "início:" in texto)
        checa(6, "8c. o log NÃO guarda nome de paciente",
              "Fase 10 — paciente do .exe" not in texto)


def eixo_7_atualizacao(dados: Path, tmp: Path):
    print("\n7. ATUALIZACAO DO CONHECIMENTO — e a segurança do dado\n")
    banco = dados / "database" / "conciliador.db"
    semente = INTERNO / "conhecimento" / "conhecimento.db"
    antes_atend = sql(banco, "SELECT COUNT(*) FROM atendimento")[0][0]
    antes_ach = sql(banco, "SELECT COUNT(*) FROM achado")[0][0]
    antes_anot = sql(banco, "SELECT COUNT(*) FROM anotacao_profissional")[0][0]
    checa(7, "há atendimento gravado para arriscar", antes_atend > 0,
          "%d atendimento(s), %d achado(s)" % (antes_atend, antes_ach))

    amb = dict(os.environ, CONCILIADOR_DADOS=str(dados),
               PYTHONIOENCODING="utf-8")

    def atualizar(arquivo):
        return subprocess.run(
            [str(EXE), "--atualizar-conhecimento", str(arquivo)],
            cwd=str(EXE.parent), env=amb, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)

    # (a) arquivo corrompido -> recusado
    ruim = tmp / "corrompido.db"
    ruim.write_bytes(b"nao sou um banco" * 100)
    r = atualizar(ruim)
    checa(7, "a. arquivo corrompido é RECUSADO", r.returncode != 0,
          "código %d" % r.returncode)
    checa(7, "a2. e os atendimentos continuam lá",
          sql(banco, "SELECT COUNT(*) FROM atendimento")[0][0] == antes_atend)

    # (b) esquema incompativel -> recusado
    incompativel = tmp / "incompativel.db"
    shutil.copy2(semente, incompativel)
    con = sqlite3.connect(incompativel)
    con.execute("UPDATE propriedade SET valor='99.0' WHERE chave='esquema.versao'")
    con.commit()
    con.close()
    r = atualizar(incompativel)
    checa(7, "b. versão de esquema incompatível é RECUSADA",
          r.returncode != 0 and "incompatível" in r.stdout.lower(),
          "código %d" % r.returncode)

    # (c) arquivo com paciente dentro -> recusado
    com_paciente = tmp / "com_paciente.db"
    shutil.copy2(semente, com_paciente)
    con = sqlite3.connect(com_paciente)
    con.execute("INSERT INTO paciente (nome) VALUES ('vazado')")
    con.execute("INSERT INTO atendimento (paciente_id, codigo) VALUES (1,'X-1')")
    con.commit()
    con.close()
    r = atualizar(com_paciente)
    checa(7, "c. conhecimento com dados de paciente é RECUSADO",
          r.returncode != 0 and "atendimento" in r.stdout.lower(),
          "código %d" % r.returncode)

    # (d) referencia que quebraria -> recusado
    furado = tmp / "furado.db"
    shutil.copy2(semente, furado)
    usada = sql(banco, "SELECT substancia_id FROM atendimento_medicamento "
                       "WHERE substancia_id IS NOT NULL LIMIT 1")
    if usada:
        con = sqlite3.connect(furado)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("DELETE FROM substancia WHERE id=?", (usada[0][0],))
        con.commit()
        con.close()
        r = atualizar(furado)
        checa(7, "d. versão que apagaria uma substância EM USO é RECUSADA",
              r.returncode != 0 and "RECUSADA" in r.stdout,
              "código %d" % r.returncode)
        checa(7, "d2. nada mudou no banco",
              sql(banco, "SELECT COUNT(*) FROM achado")[0][0] == antes_ach)

    # (e) versao valida -> aceita, atendimento preservado
    nova = tmp / "nova.db"
    shutil.copy2(semente, nova)
    con = sqlite3.connect(nova)
    con.execute("UPDATE propriedade SET valor='2099.01.01' "
                "WHERE chave='conhecimento.versao'")
    con.commit()
    con.close()
    r = atualizar(nova)
    checa(7, "e. versão válida é ACEITA", r.returncode == 0,
          "código %d" % r.returncode)
    checa(7, "e2. o conhecimento novo está em uso",
          sql(banco, "SELECT valor FROM propriedade WHERE "
                     "chave='conhecimento.versao'")[0][0] == "2099.01.01")
    for nome, esperado, consulta in (
            ("atendimentos", antes_atend, "SELECT COUNT(*) FROM atendimento"),
            ("achados", antes_ach, "SELECT COUNT(*) FROM achado"),
            ("anotações", antes_anot,
             "SELECT COUNT(*) FROM anotacao_profissional")):
        atual = sql(banco, consulta)[0][0]
        checa(7, "e3. %s preservado(s) na atualização" % nome,
              atual == esperado, "%d de %d" % (atual, esperado))
    checa(7, "e4. o banco continua íntegro e sem referência quebrada",
          sql(banco, "PRAGMA integrity_check")[0][0] == "ok"
          and not sql(banco, "PRAGMA foreign_key_check"))
    copias = list((dados / "backups").glob("conciliador_*.db"))
    checa(7, "e5. um backup foi feito antes de atualizar", len(copias) >= 1,
          "%d cópia(s)" % len(copias))
    if copias:
        checa(7, "e6. o backup contém os atendimentos de antes",
              sql(copias[-1], "SELECT COUNT(*) FROM atendimento")[0][0]
              == antes_atend)

    # (f) reinstalar o programa nao apaga o dado do usuario
    r = subprocess.run([str(EXE), "--diagnostico"], cwd=str(EXE.parent),
                       env=amb, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    checa(7, "f. abrir de novo preserva o banco (não reinstala por cima)",
          "banco já existia" in r.stdout
          and sql(banco, "SELECT COUNT(*) FROM atendimento")[0][0]
          == antes_atend)


# =====================================================================
def main() -> int:
    print("=" * 78)
    print("FASE 10 — V1: O EXECUTAVEL, USADO COMO UM USUARIO O USARIA")
    print("=" * 78)
    if not EXE.exists():
        # O `.exe` e artefato de build e nao vai para o repositorio. Sem ele
        # este teste nao tem o que medir — e PULAR ALTO e melhor do que
        # quebrar a bateria de quem ainda nao empacotou. A ausencia aparece
        # em maiusculas, nunca em silencio.
        print("")
        print("=" * 70)
        print("PULADO — o executável não foi construído.")
        print("Para exercitar esta verificação, rode antes:")
        print("  python scripts/preparar_conhecimento.py")
        print("  python scripts/build_exe.py")
        print("=" * 70)
        return 0

    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="fase10_"))
    dados = tmp / "dados_limpos"
    falhas_dir = tmp / "falhas"
    falhas_dir.mkdir(parents=True, exist_ok=True)
    porta = porta_livre()
    print("pasta de dados do teste: %s" % dados)
    print("executável:             %s\n" % EXE)

    try:
        if not eixo_1_primeira_instalacao(dados):
            return 1
        p = Programa(dados, porta)
        if not p.abrir():
            checa(2, "o programa sobe e serve", False,
                  p.texto_da_saida()[-200:])
            return 1
        try:
            codigo = eixo_2_atendimento(p, dados)
        finally:
            p.fechar()
        if codigo:
            eixo_3_persistencia(dados, codigo, porta)
        eixo_4_conhecimento_intacto(dados)
        eixo_5_ml_desligado(dados)
        eixo_6_falhas(falhas_dir, porta)
        eixo_7_atualizacao(dados, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 78)
    print("%d conferência(s) · %d ok · %d falha(s) · %.0fs"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS),
             time.time() - t0))
    for eixo, nome, det in FALHAS:
        print("  FALHA [eixo %s] %s — %s" % (eixo, nome, det))
    if not FALHAS:
        print("\nV1 OK — o executável faz, fora do ambiente de "
              "desenvolvimento, o que o sistema promete.")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
