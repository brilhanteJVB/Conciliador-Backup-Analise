# -*- coding: utf-8 -*-
"""
FASE 10 — V2: INSPECAO INDEPENDENTE DO QUE FOI EMPACOTADO.

A V1 usa o programa como um usuario usaria. Se o programa estiver errado de um
jeito que ele mesmo nao percebe, ela concorda com o erro. Esta verificacao NAO
executa o fluxo da aplicacao: ela olha os arquivos, o banco e o processo por
fora.

SETE CAMINHOS
-------------
  A  a arvore do pacote      arquivo por arquivo, tamanho por tamanho
  B  SQLite direto           o conhecimento comparado tabela a tabela com o dev
  C  cacada de caminho       C:\\ absoluto no codigo e DENTRO do pacote
  D  maquina limpa           executado sem Python no ambiente, PATH podado
  E  isolamento de escrita   o programa nao escreve na propria pasta
  F  as tres listas          as 16 tabelas de atendimento, nos tres arquivos
                             que as definem, tem de ser a MESMA lista
  G  o que nao pode viajar   segredo, dado de paciente, artefato de ML

Uso: python tests/fase10_v2_independente.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIST = RAIZ / "dist" / "SistemaConciliador"
EXE = DIST / "SistemaConciliador.exe"
INTERNO = DIST / "_internal"
DEV = RAIZ / "database" / "conciliador.db"

PASSOS, FALHAS = [], []


def checa(caminho, nome, ok, detalhe=""):
    PASSOS.append((caminho, nome, ok, detalhe))
    if not ok:
        FALHAS.append((caminho, nome, detalhe))
    print("   %s %-52s %s" % ("OK  " if ok else "ERRO", nome[:52],
                              str(detalhe)[:56]))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(4 * 1024 ** 2), b""):
            h.update(b)
    return h.hexdigest()


def sql(banco: Path, consulta: str):
    con = sqlite3.connect("file:%s?mode=ro" % banco.as_posix(), uri=True)
    try:
        return con.execute(consulta).fetchall()
    finally:
        con.close()


# =====================================================================
def caminho_a_arvore():
    print("\nA. A ARVORE DO PACOTE — arquivo por arquivo\n")
    arquivos = [p for p in DIST.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in arquivos)
    checa("A", "o executável existe", EXE.exists(),
          "%.1f MB" % (EXE.stat().st_size / 1024 ** 2) if EXE.exists() else "—")
    checa("A", "a pasta tem conteúdo", len(arquivos) > 20,
          "%d arquivo(s), %.1f MB" % (len(arquivos), total / 1024 ** 2))

    obrigatorios = [
        "_internal/conhecimento/conhecimento.db",
        "_internal/conhecimento/conhecimento.json",
        "_internal/app/templates/base.html",
        "_internal/app/templates/resultados.html",
        "_internal/app/templates/achado.html",
        "_internal/app/templates/relatorio.html",
        "_internal/app/static/estilo.css",
        "_internal/docs/GUIA_INSTALACAO.md",
        "_internal/models/espaco_features.json",
    ]
    for rel in obrigatorios:
        checa("A", "veio no pacote: %s" % rel.replace("_internal/", ""),
              (DIST / rel).exists())

    templates_dev = {p.name for p in (RAIZ / "app" / "templates").glob("*.html")}
    templates_pac = {p.name for p in
                     (INTERNO / "app" / "templates").glob("*.html")}
    checa("A", "todos os templates do projeto foram embarcados",
          templates_dev == templates_pac,
          "faltando: %s" % sorted(templates_dev - templates_pac))

    for nome, pasta in (("pipeline", "pipeline"), ("testes", "tests"),
                        ("auditoria", "auditoria"), ("ml", "ml")):
        checa("A", "a pasta %s NÃO foi embarcada" % nome,
              not (INTERNO / pasta).exists())
    checa("A", "o acervo não foi embarcado",
          not any("Conteudos banco de dados" in str(p) for p in arquivos))


def caminho_b_sqlite():
    print("\nB. SQLITE DIRETO — o conhecimento comparado com o de dev\n")
    semente = INTERNO / "conhecimento" / "conhecimento.db"
    if not semente.exists() or not DEV.exists():
        checa("B", "há o que comparar", False, "banco ausente")
        return
    manifesto = json.loads(
        (INTERNO / "conhecimento" / "conhecimento.json").read_text("utf-8"))
    checa("B", "o sha256 do pacote confere com o manifesto",
          sha256(semente) == manifesto["sha256"])

    ATEND = {"paciente", "atendimento", "atendimento_medicamento",
             "atendimento_item", "posologia", "horario_administracao",
             "rotina_paciente", "paciente_alergia", "paciente_condicao",
             "paciente_habito", "conciliacao", "conciliacao_par", "achado",
             "achado_evidencia", "nao_avaliado", "anotacao_profissional"}
    t_dev = {n for (n,) in sql(DEV, "SELECT name FROM sqlite_master "
                                    "WHERE type='table' AND name NOT LIKE "
                                    "'sqlite_%'")}
    t_pac = {n for (n,) in sql(semente, "SELECT name FROM sqlite_master "
                                        "WHERE type='table' AND name NOT LIKE "
                                        "'sqlite_%'")}
    checa("B", "o esquema distribuído tem as mesmas tabelas do de dev",
          t_dev == t_pac, "diferença: %s" % sorted(t_dev ^ t_pac))
    v_dev = {n for (n,) in sql(DEV, "SELECT name FROM sqlite_master "
                                    "WHERE type='view'")}
    v_pac = {n for (n,) in sql(semente, "SELECT name FROM sqlite_master "
                                        "WHERE type='view'")}
    checa("B", "e as mesmas views", v_dev == v_pac,
          "diferença: %s" % sorted(v_dev ^ v_pac))

    # O TESTE FORTE: hash do CONTEUDO de cada tabela de conhecimento.
    # Contagem igual nao prova conteudo igual.
    divergentes, conferidas = [], 0
    for t in sorted(t_dev & t_pac):
        # `propriedade` guarda a IDENTIDADE, e duas das suas linhas sao carimbo
        # de hora — mudam a cada carga sem que um dado mude. Sao conferidas
        # logo abaixo, pelo que importa: versao, impressao digital e esquema.
        if t in ATEND or t == "propriedade":
            continue
        conferidas += 1
        h = {}
        for rotulo, banco in (("dev", DEV), ("pac", semente)):
            d = hashlib.sha256()
            for linha in sql(banco, "SELECT * FROM %s ORDER BY rowid" % t):
                d.update(repr(linha).encode("utf-8"))
            h[rotulo] = d.hexdigest()[:16]
        if h["dev"] != h["pac"]:
            divergentes.append((t, h["dev"], h["pac"]))
    checa("B", "as %d tabelas de conhecimento têm conteúdo IDÊNTICO"
          % conferidas, not divergentes,
          "divergem: %s" % [d[0] for d in divergentes][:3])

    # DELETE, nao WAL. Um banco WAL precisa de `-wal` e `-shm` ao lado: numa
    # pasta somente leitura, abri-lo pode falhar, e a instrucao de backup do
    # guia ("copie um arquivo") deixaria de ser verdadeira. A V2 flagrou o
    # `-shm` sendo recriado dentro da pasta do programa.
    checa("B", "o banco distribuído está em modo DELETE, não WAL",
          sql(semente, "PRAGMA journal_mode")[0][0].lower() == "delete",
          sql(semente, "PRAGMA journal_mode")[0][0])
    vizinhos = [x.name for x in semente.parent.iterdir()
                if x.name.startswith("conhecimento.db-")]
    checa("B", "nenhum arquivo vizinho de WAL viajou no pacote",
          not vizinhos, vizinhos)

    vazias = [t for t in sorted(ATEND & t_pac)
              if sql(semente, "SELECT COUNT(*) FROM %s" % t)[0][0]]
    checa("B", "as 16 tabelas de atendimento estão vazias no pacote",
          not vazias, vazias)
    checa("B", "o pacote não leva nenhum dado de paciente",
          sql(semente, "SELECT COUNT(*) FROM paciente")[0][0] == 0)
    checa("B", "nenhum modelo ativo no pacote",
          sql(semente, "SELECT COUNT(*) FROM modelo WHERE ativo=1")[0][0] == 0)
    checa("B", "o pacote declara sua versão de conhecimento",
          bool(sql(semente, "SELECT valor FROM propriedade WHERE "
                            "chave='conhecimento.versao'")))
    for chave in ("conhecimento.digital", "conhecimento.versao",
                  "esquema.versao"):
        a = sql(semente, "SELECT valor FROM propriedade WHERE chave='%s'"
                % chave)
        b = sql(DEV, "SELECT valor FROM propriedade WHERE chave='%s'" % chave)
        checa("B", "%s é igual à do desenvolvimento" % chave, a == b and a,
              "pacote %s · dev %s" % (a[0][0] if a else "—",
                                      b[0][0] if b else "—"))


def caminho_c_caminhos():
    print("\nC. CACADA DE CAMINHO ABSOLUTO — no código e dentro do pacote\n")
    absoluto = re.compile(r"""["']([A-Za-z]:[\\/]{1,2}[^"']{4,})["']""")
    suspeitos = []
    for pasta in ("app", "rules"):
        for f in sorted((RAIZ / pasta).glob("*.py")):
            for n, linha in enumerate(
                    f.read_text(encoding="utf-8").splitlines(), 1):
                if linha.lstrip().startswith("#"):
                    continue
                for m in absoluto.findall(linha):
                    suspeitos.append("%s:%d %s"
                                     % (f.relative_to(RAIZ).as_posix(), n,
                                        m[:40]))
    checa("C", "nenhum caminho absoluto no código do produto", not suspeitos,
          suspeitos[:2])

    # Dentro do pacote: o codigo compilado viaja no .pyz. Um caminho da maquina
    # de build gravado la dentro so aparece olhando o arquivo.
    pyz = INTERNO / "base_library.zip"
    achados_pyz = []
    if pyz.exists():
        with zipfile.ZipFile(pyz) as z:
            nomes = z.namelist()
        achados_pyz = [n for n in nomes
                       if "Sistema Conciliador" in n or "AppData" in n]
    checa("C", "o arquivo de biblioteca não carrega caminho da máquina",
          not achados_pyz, achados_pyz[:2])

    bruto = EXE.read_bytes()
    marca = b"C:\\Sistema Conciliador projeto"
    checa("C", "o executável não tem o caminho do projeto embutido",
          marca not in bruto,
          "encontrado %d vez(es)" % bruto.count(marca))

    for f in sorted((RAIZ / "app").glob("*.py")):
        texto = f.read_text(encoding="utf-8")
        if "caminhos" in f.name or "__" in f.name:
            continue
        # Comentario nao e codigo. A primeira versao desta conferencia
        # acusou o proprio comentario que explica a regra — falso positivo
        # classico de varredura por texto.
        codigo = [l for l in texto.splitlines()
                  if not l.lstrip().startswith("#")]
        usa_raiz = re.search(r'RAIZ\s*/\s*"(database|conhecimento|backups)"',
                             "\n".join(codigo))
        checa("C", "%s não monta caminho de dado por conta própria" % f.name,
              not usa_raiz, usa_raiz.group(0) if usa_raiz else "")


def caminho_d_maquina_limpa():
    print("\nD. MAQUINA LIMPA — sem Python no ambiente\n")
    tmp = Path(tempfile.mkdtemp(prefix="f10v2_"))
    try:
        sistema = os.environ.get("SystemRoot", r"C:\Windows")
        # Ambiente minimo: nada de PYTHONPATH, PYTHONHOME, nem o Python do
        # desenvolvedor no PATH. Se o `.exe` depender do ambiente de
        # desenvolvimento, e aqui que ele quebra.
        ambiente = {
            "SystemRoot": sistema,
            "windir": sistema,
            "PATH": "%s\\system32;%s" % (sistema, sistema),
            "TEMP": str(tmp), "TMP": str(tmp),
            "CONCILIADOR_DADOS": str(tmp / "dados"),
            "PYTHONIOENCODING": "utf-8",
        }
        for proibida in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            checa("D", "o ambiente de teste não define %s" % proibida,
                  proibida not in ambiente)
        r = subprocess.run([str(EXE), "--diagnostico"], cwd=str(DIST),
                           env=ambiente, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        checa("D", "o executável roda sem Python no ambiente",
              r.returncode == 0, "código %d · %s"
              % (r.returncode, (r.stdout or r.stderr or "")[-60:]))
        checa("D", "e instalou o conhecimento do zero",
              (tmp / "dados" / "database" / "conciliador.db").exists())
        checa("D", "o banco criado é válido e íntegro",
              (tmp / "dados" / "database" / "conciliador.db").exists()
              and sql(tmp / "dados" / "database" / "conciliador.db",
                      "PRAGMA integrity_check")[0][0] == "ok")
        checa("D", "não sobrou processo escrevendo na pasta do programa",
              not (DIST / "database").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def caminho_e_isolamento():
    print("\nE. ISOLAMENTO DE ESCRITA — o programa não suja a própria pasta\n")
    antes = {p.relative_to(DIST).as_posix(): p.stat().st_mtime_ns
             for p in DIST.rglob("*") if p.is_file()}
    tmp = Path(tempfile.mkdtemp(prefix="f10e_"))
    try:
        ambiente = dict(os.environ, CONCILIADOR_DADOS=str(tmp / "dados"),
                        PYTHONIOENCODING="utf-8")
        subprocess.run([str(EXE), "--diagnostico"], cwd=str(DIST),
                       env=ambiente, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
        depois = {p.relative_to(DIST).as_posix(): p.stat().st_mtime_ns
                  for p in DIST.rglob("*") if p.is_file()}
        novos = sorted(set(depois) - set(antes))
        alterados = sorted(k for k in set(antes) & set(depois)
                           if antes[k] != depois[k])
        checa("E", "nenhum arquivo novo na pasta do programa", not novos,
              novos[:3])
        checa("E", "nenhum arquivo alterado na pasta do programa",
              not alterados, alterados[:3])
        checa("E", "tudo que ele criou ficou na pasta de dados",
              (tmp / "dados" / "database" / "conciliador.db").exists())
        escritos = sorted(p.relative_to(tmp / "dados").as_posix()
                          for p in (tmp / "dados").rglob("*") if p.is_file())
        checa("E", "e o que ele criou é só o esperado",
              all(e.startswith(("database/", "data/", "config/", "backups/"))
                  for e in escritos), escritos[:4])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def caminho_f_listas():
    print("\nF. AS TRES LISTAS — a fronteira tem de ser a mesma em todo lugar\n")
    def extrair(arquivo: Path, marcador: str) -> set:
        texto = arquivo.read_text(encoding="utf-8")
        i = texto.find(marcador)
        if i < 0:
            return set()
        trecho = texto[i:texto.find(")", i)]
        return set(re.findall(r'"([a-z_]+)"', trecho))

    a = extrair(RAIZ / "app" / "atualizacao.py", "ATENDIMENTO_EM_ORDEM = (")
    b = extrair(RAIZ / "scripts" / "preparar_conhecimento.py",
                "ATENDIMENTO = (")
    c = extrair(RAIZ / "tests" / "fase9_convergencia.py", "FORA_DA_CARGA = {")
    if not c:
        texto = (RAIZ / "tests" / "fase9_convergencia.py").read_text("utf-8")
        i = texto.find("FORA_DA_CARGA = {")
        c = set(re.findall(r'"([a-z_]+)"', texto[i:texto.find("}", i)]))
    c = c - {"modelo", "predicao"}       # ML não é atendimento

    checa("F", "atualizacao.py e preparar_conhecimento.py concordam", a == b,
          "só em um: %s" % sorted(a ^ b))
    checa("F", "e concordam com a fronteira usada na Fase 9", a == c,
          "só em um: %s" % sorted(a ^ c))
    checa("F", "são exatamente 16 tabelas de atendimento", len(a) == 16,
          "%d" % len(a))

    # A conferencia definitiva: a lista bate com o que o BANCO mostra.
    if DEV.exists():
        todas = {n for (n,) in sql(DEV, "SELECT name FROM sqlite_master "
                                        "WHERE type='table' AND name NOT LIKE "
                                        "'sqlite_%'")}
        checa("F", "toda tabela da lista existe no banco", a <= todas,
              sorted(a - todas))
        # Nenhuma tabela FORA da lista pode referenciar paciente/atendimento.
        con = sqlite3.connect("file:%s?mode=ro" % DEV.as_posix(), uri=True)
        try:
            esquecidas = []
            for t in sorted(todas - a):
                for fk in con.execute("PRAGMA foreign_key_list(%s)" % t):
                    if fk[2] in ("paciente", "atendimento", "conciliacao"):
                        esquecidas.append((t, fk[2]))
        finally:
            con.close()
        checa("F", "nenhuma tabela ficou de fora da lista por engano",
              not esquecidas, esquecidas[:3])


def caminho_g_nao_viaja():
    print("\nG. O QUE NAO PODE VIAJAR NO PACOTE\n")
    arquivos = [p for p in DIST.rglob("*") if p.is_file()]
    nomes = [p.name.lower() for p in arquivos]
    checa("G", "nenhuma chave de sessão foi embarcada",
          "sessao.chave" not in nomes)
    checa("G", "nenhum banco de desenvolvimento foi embarcado",
          "conciliador.db" not in nomes,
          [p.name for p in arquivos if p.name == "conciliador.db"][:1])
    checa("G", "nenhum backup histórico foi embarcado",
          not any(n.startswith("conciliador_backup") for n in nomes))
    checa("G", "nenhum artefato .pkl de modelo", not any(n.endswith(".pkl")
                                                          for n in nomes))
    checa("G", "nenhum log de desenvolvimento", "aplicacao.log" not in nomes)
    checa("G", "nenhum .git", not any(".git" in p.parts for p in arquivos))

    # Varredura de segredo no pacote inteiro, texto e binario pequeno.
    padroes = [re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
               re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
               re.compile(rb"AKIA[0-9A-Z]{16}")]
    encontrados = []
    for p in arquivos:
        if p.stat().st_size > 20 * 1024 ** 2:
            continue
        dados = p.read_bytes()
        for pad in padroes:
            if pad.search(dados):
                encontrados.append(p.name)
                break
    checa("G", "nenhum segredo no pacote", not encontrados, encontrados[:3])

    # O programa e OFFLINE. Nenhuma chamada de rede de saida no codigo do
    # produto — o unico socket e local, para escolher uma porta livre, e o
    # unico endereco aberto no navegador e 127.0.0.1.
    rede = re.compile(r"(urllib|requests|http\.client|urlopen|smtplib|"
                      r"ftplib|xmlrpc|telnetlib)")
    usos = []
    for pasta in ("app", "rules"):
        for f in sorted((RAIZ / pasta).glob("*.py")):
            for n, linha in enumerate(
                    f.read_text(encoding="utf-8").splitlines(), 1):
                if linha.lstrip().startswith("#"):
                    continue
                if rede.search(linha):
                    usos.append("%s:%d" % (f.name, n))
    checa("G", "o produto não faz nenhuma chamada de rede de saída",
          not usos, usos[:3])
    externos = re.findall(
        r'(?:href|src)="(https?://[^"]+)"',
        "\n".join(p.read_text(encoding="utf-8", errors="replace")
                  for p in (INTERNO / "app" / "templates").glob("*.html")))
    checa("G", "nenhum template busca recurso na internet", not externos,
          externos[:2])
    principal = (RAIZ / "app" / "principal.py").read_text(encoding="utf-8")
    aberturas = re.findall(r'webbrowser\.open\("([^"]+)', principal)
    checa("G", "o navegador só é aberto em 127.0.0.1",
          all(a.startswith("http://127.0.0.1") for a in aberturas),
          aberturas)

    guia = INTERNO / "docs" / "GUIA_INSTALACAO.md"
    if guia.exists():
        texto = guia.read_text(encoding="utf-8")
        checa("G", "o guia declara a limitação clínica",
              "não a substitui" in texto and "revisado por farmacêutico"
              in texto)
        checa("G", "o guia diz onde ficam os dados do usuário",
              "AppData" in texto and "backup" in texto.lower())


# =====================================================================
def main() -> int:
    print("=" * 78)
    print("FASE 10 — V2: INSPECAO INDEPENDENTE DO QUE FOI EMPACOTADO")
    print("=" * 78)
    if not EXE.exists():
        # Ver a nota em `tests/fase10_empacotamento.py`: sem o `.exe` nao ha
        # o que inspecionar, e pular alto e melhor do que quebrar a bateria.
        print("")
        print("=" * 70)
        print("PULADO — o executável não foi construído.")
        print("Rode antes `python scripts/build_exe.py`.")
        print("=" * 70)
        return 0
    print("pacote: %s\n" % DIST)

    caminho_a_arvore()
    caminho_b_sqlite()
    caminho_c_caminhos()
    caminho_d_maquina_limpa()
    caminho_e_isolamento()
    caminho_f_listas()
    caminho_g_nao_viaja()

    print("\n" + "=" * 78)
    print("%d verificação(ões) · %d ok · %d falha(s)"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS)))
    for c, nome, det in FALHAS:
        print("  FALHA [%s] %s — %s" % (c, nome, det))
    if not FALHAS:
        print("\nV2 OK — sete caminhos independentes, nenhum defeito de "
              "empacotamento encontrado.")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
