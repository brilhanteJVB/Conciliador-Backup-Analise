# -*- coding: utf-8 -*-
"""
FASE 1 - AUDITORIA COMPLETA DO ACERVO
=====================================
Percorre 'C:/Conteudos banco de dados tcc' em modo SOMENTE LEITURA e produz um
inventario tecnico de cada arquivo: formato, tamanho, encoding, delimitador,
esquema, colunas, vazios, duplicidades, identificadores candidatos, idioma e
funcao provavel.

NAO modifica, move ou apaga nada na origem.
Saida: auditoria/saida/inventario_bruto.json
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ORIGEM = Path(r"C:\Conteudos banco de dados tcc")
DESTINO = Path(r"C:\Sistema Conciliador projeto")
SAIDA = DESTINO / "auditoria" / "saida"
SAIDA.mkdir(parents=True, exist_ok=True)

IGNORAR_DIR = {"__pycache__", ".git", ".idea"}

AMOSTRA_LINHAS = 400          # linhas lidas para inferir esquema
csv.field_size_limit(10 * 1024 * 1024)

PALAVRAS_PT = {
    "de", "da", "do", "para", "com", "nao", "medicamento", "principio",
    "ativo", "substancia", "gravidade", "interacao", "dose", "paciente",
    "descricao", "nome", "codigo", "registro", "produto", "situacao",
}
PALAVRAS_EN = {
    "the", "and", "with", "drug", "interaction", "severity", "description",
    "name", "code", "product", "level", "effect", "mechanism", "food",
    "disease", "adverse", "reaction", "dose",
}
ACENTOS = "\u00e1\u00e9\u00ed\u00f3\u00fa\u00e3\u00f5\u00e7\u00ea\u00f4\u00e2\u00c1\u00c9\u00cd\u00d3\u00da\u00c3\u00d5\u00c7"


def detectar_idioma(texto: str) -> str:
    """Heuristica PT/EN sobre um trecho de texto."""
    if not texto:
        return "indeterminado"
    fichas = re.findall(r"[a-zA-Z" + ACENTOS + r"]+", texto.lower())
    if not fichas:
        return "indeterminado"
    amostra = set(fichas[:4000])
    pt = len(amostra & PALAVRAS_PT)
    en = len(amostra & PALAVRAS_EN)
    if len(re.findall("[" + ACENTOS + "]", texto[:20000])) > 20:
        pt += 3
    if pt > en:
        return "pt-BR"
    if en > pt:
        return "en"
    return "indeterminado"


def detectar_encoding(caminho: Path, n=200_000):
    try:
        import chardet
    except ImportError:
        return ("desconhecido", 0.0)
    with open(caminho, "rb") as fh:
        bruto = fh.read(n)
    if bruto.startswith(b"\xef\xbb\xbf"):
        return ("utf-8-sig", 1.0)
    r = chardet.detect(bruto)
    enc = (r.get("encoding") or "desconhecido").lower()
    # chardet le so o inicio: 'ascii' num arquivo grande quase sempre e UTF-8
    # com acento mais adiante. Promover evita falso UnicodeDecodeError.
    if enc == "ascii":
        enc = "utf-8"
    return (enc, float(r.get("confidence") or 0.0))


VALIDA_BYTES = 8 * 1024 * 1024   # quanto decodificar antes de aceitar um encoding


def abrir_texto(caminho: Path, encoding: str):
    """Abre em texto testando encodings contra um trecho grande do arquivo.

    chardet le so o inicio e erra em arquivos da ANVISA (ja devolveu 'big5'
    para um CSV em cp1252). Aqui a ordem e: UTF-8 primeiro -- se decodificar
    8 MB sem erro, e UTF-8 --, depois o palpite do chardet apenas se for um
    codec latino de byte unico, depois cp1252 e latin-1.
    """
    palpite = (encoding or "").lower()
    latinos = {"cp1252", "windows-1252", "iso-8859-1", "iso-8859-2",
               "latin-1", "latin1", "iso-8859-15", "mac_roman"}
    ordem = ["utf-8-sig", "utf-8"]
    if palpite in latinos:
        ordem.append(palpite)
    ordem += ["cp1252", "latin-1"]

    for enc in ordem:
        try:
            fh = open(caminho, "r", encoding=enc, errors="strict", newline="")
            fh.read(VALIDA_BYTES)
            fh.seek(0)
            return fh, enc
        except (UnicodeDecodeError, LookupError):
            try:
                fh.close()
            except Exception:
                pass
            continue
    return open(caminho, "r", encoding="latin-1", errors="replace", newline=""), "latin-1(forcado)"


def detectar_delimitador(amostra: str) -> str:
    """Escolhe o delimitador que produz a tabela mais consistente.

    Contar ocorrencias por linha nao serve: campos entre aspas contendo o
    separador (descricoes de interacao, nomes de produto) quebram a contagem.
    Aqui cada candidato e de fato parseado com csv.reader e vence o que der
    mais colunas mantendo o mesmo numero de colunas na maioria das linhas.
    """
    melhor, melhor_nota = ",", -1e9
    for d in (";", ",", "\t", "|"):
        try:
            linhas = []
            for i, linha in enumerate(csv.reader(io.StringIO(amostra), delimiter=d)):
                if i >= 60:
                    break
                if linha:
                    linhas.append(len(linha))
        except csv.Error:
            continue
        if len(linhas) < 2:
            continue
        ncol = linhas[0]
        if ncol < 2:
            continue
        consistentes = sum(1 for n in linhas[1:-1] if n == ncol)
        base = max(1, len(linhas) - 2)
        nota = (consistentes / base) * 100 + min(ncol, 80)
        if nota > melhor_nota:
            melhor, melhor_nota = d, nota
    return melhor


def localizar_cabecalho(amostra: str, delim: str):
    """Devolve (linhas_a_pular, cabecalho_ausente).

    Tres padroes reais no acervo quebram a suposicao 'linha 1 = cabecalho':
      - CMED: as primeiras linhas sao um banner ('Secretaria Executiva - CMED');
      - GtoPdb/IUPHAR: linha 1 e um comentario '# GtoPdb Version: ...';
      - ANVISA TA_CONSULTA_BULA_DOCUMENTO: nao ha cabecalho, linha 1 ja e dado.
    A largura modal das linhas diz qual e a primeira linha util; se essa linha
    parecer dado (numeros, datas) em vez de rotulos, marcamos cabecalho ausente.
    """
    linhas = []
    for i, linha in enumerate(csv.reader(io.StringIO(amostra), delimiter=delim)):
        if i >= 120:
            break
        linhas.append(linha)
    if not linhas:
        return 0, False
    larguras = [len(l) for l in linhas if l]
    if not larguras:
        return 0, False
    modal = Counter(larguras).most_common(1)[0][0]
    if modal < 2:
        return 0, False
    # O banner da CMED tambem vem preenchido ate 74 colunas com ';' vazios,
    # entao largura modal nao basta: a linha util precisa ter celulas de fato.
    pular = None
    for i, l in enumerate(linhas):
        if len(l) != modal:
            continue
        if l and str(l[0]).lstrip().startswith("#"):
            continue
        preenchidas = sum(1 for c in l if str(c).strip())
        if preenchidas / modal >= 0.6:
            pular = i
            break
    if pular is None:
        return 0, False

    candidato = linhas[pular]
    celulas = [str(c).strip() for c in candidato if str(c).strip()]
    if not celulas:
        return pular, True
    # rotulo tipico: texto sem virar numero e sem cara de data
    def parece_dado(v: str) -> bool:
        if re.fullmatch(r"[\d.,/:\-\s]+", v):
            return True
        return bool(re.match(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}", v))
    proporcao_dado = sum(parece_dado(c) for c in celulas) / len(celulas)
    return pular, proporcao_dado >= 0.5


def contar_linhas(caminho: Path) -> int:
    total = 0
    with open(caminho, "rb") as fh:
        while True:
            bloco = fh.read(4 * 1024 * 1024)
            if not bloco:
                break
            total += bloco.count(b"\n")
    return total


LIMITE_CONTAGEM_EXATA = 300 * 1024 * 1024


def contar_registros(caminho: Path, enc: str, delim: str, pular: int,
                     cabecalho_ausente: bool, tam: int):
    """Conta registros CSV de verdade, nao linhas fisicas.

    Descricao de interacao e texto de bula contem quebra de linha dentro de
    campo entre aspas; contar '\\n' superestima. Acima de 60 MB a contagem
    exata fica cara e devolvemos None, sinalizando o metodo usado.
    """
    if tam > LIMITE_CONTAGEM_EXATA:
        return None, "nao contado (arquivo grande) - ver n_linhas_fisicas"
    try:
        with open(caminho, "r", encoding=enc, errors="replace", newline="") as fh:
            leitor = csv.reader(fh, delimiter=delim)
            for _ in range(pular):
                next(leitor, None)
            if not cabecalho_ausente:
                next(leitor, None)
            n = 0
            for linha in leitor:
                if linha and any(str(c).strip() for c in linha):
                    n += 1
        return n, "registros CSV (exato)"
    except (csv.Error, OSError) as e:
        return None, f"falhou: {type(e).__name__}"


def hash_rapido(caminho: Path, limite=8 * 1024 * 1024) -> str:
    """Hash do inicio do arquivo + tamanho: detecta duplicata exata barato."""
    h = hashlib.sha256()
    h.update(str(caminho.stat().st_size).encode())
    with open(caminho, "rb") as fh:
        h.update(fh.read(limite))
    return h.hexdigest()[:24]


def legivel(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{int(n)} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return str(n)


# ------------------------------------------------------------- analisadores

def analisar_tabular(caminho: Path, tam: int) -> dict:
    enc, conf = detectar_encoding(caminho)
    fh, enc_real = abrir_texto(caminho, enc)
    try:
        amostra_txt = fh.read(256_000)
        delim = detectar_delimitador(amostra_txt)
        pular, cabecalho_ausente = localizar_cabecalho(amostra_txt, delim)
        fh.seek(0)
        leitor = csv.reader(fh, delimiter=delim)
        for _ in range(pular):
            next(leitor, None)
        try:
            primeira = next(leitor)
        except StopIteration:
            return {"erro": "arquivo vazio"}
        linhas = []
        if cabecalho_ausente:
            # sem linha de cabecalho: a primeira linha ja e dado
            cabecalho = ["col_%02d" % (i + 1) for i in range(len(primeira))]
            linhas.append(primeira)
        else:
            cabecalho = primeira
        for i, linha in enumerate(leitor):
            if i >= AMOSTRA_LINHAS:
                break
            linhas.append(linha)
    finally:
        fh.close()

    ncol = len(cabecalho)
    nulos = [0] * ncol
    valores = [Counter() for _ in range(ncol)]
    exemplos = [None] * ncol
    for linha in linhas:
        for j in range(min(ncol, len(linha))):
            v = (linha[j] or "").strip()
            if v == "" or v.upper() in {"NULL", "NA", "N/A", "-", "NONE", "NAN"}:
                nulos[j] += 1
            else:
                valores[j][v] += 1
                if exemplos[j] is None:
                    exemplos[j] = v[:80]

    n = max(1, len(linhas))
    colunas = []
    for j, nome in enumerate(cabecalho):
        distintos = len(valores[j])
        colunas.append({
            "nome": nome.strip()[:120],
            "pct_vazio_amostra": round(100 * nulos[j] / n, 1),
            "distintos_amostra": distintos,
            "exemplo": exemplos[j],
            "possivel_id": bool(distintos >= 0.97 * n and n > 20),
            "dominio_pequeno": [v for v, _ in valores[j].most_common(8)] if 0 < distintos <= 8 else None,
        })

    fisicas = contar_linhas(caminho)
    registros, metodo = contar_registros(caminho, enc_real, delim, pular, cabecalho_ausente, tam)
    dup = len(linhas) - len({tuple(l) for l in linhas})
    return {
        "formato": "CSV/tabular",
        "encoding_detectado": enc,
        "encoding_confianca": round(conf, 2),
        "encoding_usado": enc_real,
        "delimitador": {"\t": "TAB"}.get(delim, delim),
        "n_colunas": ncol,
        "n_linhas_dados": registros,
        "metodo_contagem": metodo,
        "n_linhas_fisicas": fisicas,
        "quebras_de_linha_dentro_de_campo": (
            None if registros is None else max(0, (fisicas - pular - (0 if cabecalho_ausente else 1)) - registros)
        ),
        "linhas_ignoradas_antes_do_cabecalho": pular,
        "cabecalho_ausente": cabecalho_ausente,
        "cabecalho": [c.strip() for c in cabecalho],
        "colunas": colunas,
        "dup_linhas_amostra": dup,
        "idioma": detectar_idioma(" ".join(cabecalho) + " " + amostra_txt[:20000]),
    }


def _resumir(obj, prof=0, max_prof=3):
    if prof > max_prof:
        return "..."
    if isinstance(obj, dict):
        return {k: _resumir(v, prof + 1, max_prof) for k, v in list(obj.items())[:25]}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_resumir(obj[0], prof + 1, max_prof), f"...({len(obj)} itens)"]
    if isinstance(obj, str):
        return obj[:120]
    return obj


def analisar_json(caminho: Path, tam: int) -> dict:
    enc, _ = detectar_encoding(caminho)
    fh, enc_real = abrir_texto(caminho, enc)
    try:
        bruto = fh.read()
    finally:
        fh.close()
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as e:
        linhas = [l for l in bruto.splitlines() if l.strip()]
        try:
            primeira = json.loads(linhas[0])
            return {"formato": "JSON Lines", "n_registros": len(linhas),
                    "chaves": sorted(primeira.keys()) if isinstance(primeira, dict) else None,
                    "encoding_usado": enc_real, "idioma": detectar_idioma(bruto[:30000])}
        except Exception:
            return {"erro": f"JSON invalido: {e}", "encoding_usado": enc_real}

    info = {"encoding_usado": enc_real, "idioma": detectar_idioma(bruto[:30000])}
    if isinstance(dados, list):
        info["formato"] = "JSON lista"
        info["n_registros"] = len(dados)
        if dados and isinstance(dados[0], dict):
            ch = Counter()
            for r in dados[:2000]:
                if isinstance(r, dict):
                    ch.update(r.keys())
            base = min(len(dados), 2000)
            info["chaves"] = [{"chave": k, "presenca_pct": round(100 * v / base, 1)}
                              for k, v in ch.most_common(40)]
        info["amostra"] = _resumir(dados[:1])
    elif isinstance(dados, dict):
        info["formato"] = "JSON objeto"
        info["n_chaves_topo"] = len(dados)
        info["chaves_topo"] = list(dados.keys())[:40]
        info["amostra"] = _resumir(dados)
    else:
        info["formato"] = f"JSON {type(dados).__name__}"
    return info


def analisar_sqlite(caminho: Path, tam: int) -> dict:
    try:
        con = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("SELECT type, name FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name")
        objetos = cur.fetchall()
        tabelas, visoes = [], []
        for tipo, nome in objetos:
            if tipo == "table" and not nome.startswith("sqlite_"):
                try:
                    cur.execute('SELECT COUNT(*) FROM "%s"' % nome)
                    n = cur.fetchone()[0]
                except sqlite3.Error:
                    n = None
                cur.execute('PRAGMA table_info("%s")' % nome)
                cols = [c[1] for c in cur.fetchall()]
                tabelas.append({"tabela": nome, "linhas": n, "n_colunas": len(cols), "colunas": cols})
            elif tipo == "view":
                visoes.append(nome)
        cur.execute("PRAGMA page_count"); pc = cur.fetchone()[0]
        cur.execute("PRAGMA page_size"); ps = cur.fetchone()[0]
        con.close()
        return {"formato": "SQLite", "n_tabelas": len(tabelas), "n_visoes": len(visoes),
                "visoes": visoes, "total_linhas": sum(t["linhas"] or 0 for t in tabelas),
                "tabelas": sorted(tabelas, key=lambda t: -(t["linhas"] or 0)),
                "paginas": pc, "tamanho_pagina": ps}
    except sqlite3.Error as e:
        return {"erro": f"SQLite ilegivel: {e}"}


def analisar_pdf(caminho: Path, tam: int) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"erro": "pypdf ausente", "metodo_sugerido": "pip install pypdf"}
    try:
        leitor = PdfReader(str(caminho))
        n = len(leitor.pages)
        texto = ""
        for p in leitor.pages[:3]:
            try:
                texto += (p.extract_text() or "")
            except Exception:
                pass
        meta = leitor.metadata or {}
        return {"formato": "PDF", "n_paginas": n,
                "tem_camada_texto": len(texto.strip()) > 120,
                "caracteres_3_paginas": len(texto),
                "titulo_metadado": str(meta.get("/Title") or "")[:120],
                "trecho": re.sub(r"\s+", " ", texto)[:400],
                "idioma": detectar_idioma(texto)}
    except Exception as e:
        return {"erro": f"PDF ilegivel: {type(e).__name__}: {e}",
                "metodo_sugerido": "OCR (tesseract) ou pdfplumber"}


def analisar_xlsx(caminho: Path, tam: int) -> dict:
    try:
        import openpyxl
    except ImportError:
        return {"erro": "openpyxl ausente"}
    try:
        wb = openpyxl.load_workbook(str(caminho), read_only=True, data_only=True)
        abas = []
        for nome in wb.sheetnames:
            ws = wb[nome]
            cab = []
            for linha in ws.iter_rows(min_row=1, max_row=1, values_only=True):
                cab = [str(c) if c is not None else "" for c in linha]
            abas.append({"aba": nome, "linhas": ws.max_row, "colunas": ws.max_column,
                         "cabecalho": cab[:40]})
        wb.close()
        return {"formato": "XLSX", "n_abas": len(abas), "abas": abas}
    except Exception as e:
        return {"erro": f"XLSX ilegivel: {type(e).__name__}: {e}"}


def analisar_python(caminho: Path, tam: int) -> dict:
    enc, _ = detectar_encoding(caminho)
    fh, enc_real = abrir_texto(caminho, enc)
    try:
        src = fh.read()
    finally:
        fh.close()
    doc = ""
    m = re.search(r'^\s*(?:#[^\n]*\n)*\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', src, re.S)
    if m:
        doc = re.sub(r"\s+", " ", m.group(1)).strip()[:400]
    return {"formato": "codigo Python",
            "linhas": src.count("\n") + 1,
            "docstring": doc,
            "imports": sorted(set(re.findall(r"^\s*(?:import|from)\s+([\w\.]+)", src, re.M)))[:40],
            "funcoes": re.findall(r"^\s*def\s+(\w+)", src, re.M)[:40],
            "classes": re.findall(r"^\s*class\s+(\w+)", src, re.M)[:20],
            "tabelas_sql_citadas": sorted(set(re.findall(
                r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_][a-z0-9_]*)", src, re.I)))[:40],
            "encoding_usado": enc_real}


def analisar_texto(caminho: Path, tam: int) -> dict:
    enc, _ = detectar_encoding(caminho)
    fh, enc_real = abrir_texto(caminho, enc)
    try:
        conteudo = fh.read(400_000)
    finally:
        fh.close()
    linhas = conteudo.splitlines()
    return {"formato": "texto/markdown",
            "linhas_total": contar_linhas(caminho),
            "titulos_markdown": [l.strip()[:110] for l in linhas if l.startswith("#")][:25],
            "trecho": re.sub(r"\s+", " ", conteudo[:600]),
            "idioma": detectar_idioma(conteudo[:30000]),
            "encoding_usado": enc_real}


def analisar_npz(caminho: Path, tam: int) -> dict:
    try:
        import numpy as np
        d = np.load(str(caminho), allow_pickle=False)
        if hasattr(d, "files"):
            return {"formato": "NumPy .npz",
                    "arrays": [{"nome": k, "forma": list(d[k].shape), "tipo": str(d[k].dtype)}
                               for k in d.files]}
        return {"formato": "NumPy .npy", "forma": list(d.shape), "tipo": str(d.dtype)}
    except Exception as e:
        return {"erro": f"NumPy ilegivel: {e}"}


def analisar_sql(caminho: Path, tam: int) -> dict:
    enc, _ = detectar_encoding(caminho)
    fh, enc_real = abrir_texto(caminho, enc)
    try:
        src = fh.read()
    finally:
        fh.close()
    return {"formato": "DDL/SQL", "linhas": src.count("\n") + 1,
            "tabelas_criadas": re.findall(r"CREATE\s+TABLE\s+(?:IF NOT EXISTS\s+)?[\"']?(\w+)", src, re.I),
            "visoes_criadas": re.findall(r"CREATE\s+VIEW\s+(?:IF NOT EXISTS\s+)?[\"']?(\w+)", src, re.I),
            "n_indices": len(re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX", src, re.I)),
            "n_checks": len(re.findall(r"\bCHECK\s*\(", src, re.I)),
            "n_fks": len(re.findall(r"REFERENCES\s+\w+", src, re.I)),
            "encoding_usado": enc_real}


DESPACHO = {
    ".csv": analisar_tabular, ".tsv": analisar_tabular,
    ".json": analisar_json,
    ".db": analisar_sqlite, ".sqlite": analisar_sqlite, ".sqlite3": analisar_sqlite,
    ".pdf": analisar_pdf,
    ".xlsx": analisar_xlsx, ".xlsm": analisar_xlsx,
    ".py": analisar_python,
    ".md": analisar_texto, ".txt": analisar_texto,
    ".npz": analisar_npz, ".npy": analisar_npz,
    ".sql": analisar_sql,
}


def analisar(caminho: Path, tam: int) -> dict:
    fn = DESPACHO.get(caminho.suffix.lower())
    if fn is None:
        with open(caminho, "rb") as fh:
            cab = fh.read(16)
        if cab.startswith(b"SQLite format 3"):
            return analisar_sqlite(caminho, tam)
        if cab.startswith(b"PK\x03\x04"):
            return analisar_xlsx(caminho, tam)
        if cab.startswith(b"%PDF"):
            return analisar_pdf(caminho, tam)
        for tentativa in (analisar_json, analisar_tabular, analisar_texto):
            try:
                r = tentativa(caminho, tam)
                if "erro" not in r:
                    r["nota"] = "extensao nao padrao: formato inferido pelo conteudo"
                    return r
            except Exception:
                continue
        return {"erro": "formato nao reconhecido", "primeiros_bytes": cab.hex()}
    try:
        return fn(caminho, tam)
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {e}"}


def main() -> int:
    registros = []
    t0 = datetime.now(timezone.utc)
    for raiz, dirs, arqs in os.walk(ORIGEM):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIR]
        for nome in sorted(arqs):
            caminho = Path(raiz) / nome
            try:
                st = caminho.stat()
            except OSError as e:
                registros.append({"caminho_relativo": str(caminho), "erro": str(e)})
                continue
            rel = caminho.relative_to(ORIGEM).as_posix()
            reg = {"caminho_relativo": rel,
                   "pasta": Path(rel).parent.as_posix(),
                   "nome": nome,
                   "extensao": caminho.suffix.lower(),
                   "tamanho_bytes": st.st_size,
                   "tamanho_legivel": legivel(st.st_size),
                   "modificado": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")}
            if st.st_size == 0:
                reg["analise"] = {"erro": "arquivo vazio (0 bytes)"}
            else:
                reg["analise"] = analisar(caminho, st.st_size)
                if st.st_size < 300 * 1024 * 1024:
                    reg["hash"] = hash_rapido(caminho)
            registros.append(reg)
            print("  " + rel, flush=True)

    por_hash = {}
    for r in registros:
        if r.get("hash"):
            por_hash.setdefault(r["hash"], []).append(r["caminho_relativo"])
    duplicatas = {h: v for h, v in por_hash.items() if len(v) > 1}

    saida = {"gerado_em": t0.isoformat(), "origem": str(ORIGEM),
             "n_arquivos": len(registros),
             "bytes_totais": sum(r.get("tamanho_bytes", 0) for r in registros),
             "duplicatas_exatas": duplicatas,
             "arquivos": registros}
    destino = SAIDA / "inventario_bruto.json"
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nOK: %d arquivos -> %s" % (len(registros), destino))
    print("Duplicatas exatas: %d grupos" % len(duplicatas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
