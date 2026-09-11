# Mapa do acervo — entidades, chaves e relacionamentos

**Data:** 08/09/2026
**Base:** medições de `auditoria/saida/cruzamentos.json` e `inventario_bruto.json`

Este documento responde: **quais dados podem se ligar a quais, por qual chave, e com que taxa de sucesso real.** Todo número aqui foi medido, não estimado.

---

## 1. O problema central: nada se liga por nome cru

O acervo tem fontes em dois idiomas e três convenções de nomenclatura:

| Convenção | Onde aparece | Exemplo |
|---|---|---|
| DCB (português, com sal) | ANVISA, CMED, DCB | `dipirona monoidratada` |
| INN (inglês, com sal) | DDInter, DrugBank | `Metamizole sodium` |
| Marca comercial | CMED, `medicine_dataset` | `Novalgina`, `augmentin 625 duo tablet` |

`dipirona monoidratada` e `Metamizole sodium` são a mesma molécula. Comparação de texto não os une, e nem `lower()` nem remoção de acento resolvem.

**A ponte é `analise_dados/scripts/lib_norm.py`**, um normalizador determinístico (não é modelo de ML) que aplica transliteração fonética PT↔EN e remove uma tabela de 120 sais, ésteres e hidratos, reduzindo os dois idiomas a um mesmo esqueleto:

```
dipirona monoidratada  ─┐
                        ├─→  metamisol   (esqueleto canônico)
Metamizole sodium      ─┘
```

Toda a medição da seção 4 da auditoria depende dessa função. **É a peça mais crítica e menos visível do acervo.**

---

## 2. Cadeia de entidades — o que o acervo permite montar

Cada seta abaixo existe de verdade no acervo, com a fonte que a sustenta e a cobertura medida.

```
PRODUTO COMERCIAL                    CMED (25.702) · ANVISA (43.441)
    │  EAN / registro ANVISA         26.762 EANs carregados
    ▼
APRESENTAÇÃO                         CMED: concentração, forma, via
    │  CO_SUBSTANCIA / DS_SUBSTANCIA
    ▼
SUBSTÂNCIA (princípio ativo)         2.153 ativas na ANVISA  ← ÂNCORA
    │  lib_norm.skeleton()              ponte PT ↔ EN
    ├──────────────► CLASSE ATC        WHO ATC-DDD · cobre 51,2%
    ├──────────────► CAS / DCB nº      DCB nº 81,9% · CAS 72,1%
    ├──────────────► ALVO MOLECULAR    IUPHAR/GtoPdb · cobre 39,3%
    │                    │  Type / Action (agonista, antagonista, inibidor)
    │                    ▼
    │                DIREÇÃO DE AÇÃO   permite deduzir antagonismo por receptor
    ├──────────────► PAPEL CYP         FDA (31 índice) + regex de bula
    │                    │  substrato / inibidor / indutor + potência
    │                    ▼
    │                MECANISMO PK      inibição de CYP3A4 → ↑ exposição
    ├──────────────► PERFIL PD         db_drug_interactions (efeito nomeado)
    └──────────────► TARJA / CANAL     ANVISA CO_TARJA (mapa corrigido)

SUBSTÂNCIA × SUBSTÂNCIA               79.418 pares BR×BR (união medida)
    │  gravidade                       DDInter (única fonte que gradua)
    ▼
INTERAÇÃO ──► MECANISMO ──► EFEITO ESPERADO ──► GRAVIDADE ──► CONDUTA
                                                                 ▲
                                                    0,12% preenchido — lacuna
```

---

## 3. As oito relações que o sistema precisa, e o que existe para cada uma

| # | Relação | Fonte disponível | Volume BR | Situação |
|---|---|---|---:|---|
| 1 | **Fármaco × Fármaco** | DDInter + `db_drug_interactions` | 79.418 pares | Implementado |
| 2 | **Fármaco × Álcool** | Curadoria própria | 288 registros | Implementado (curado) |
| 3 | **Fármaco × Tabaco** | Curadoria própria + PubMed | 30 substâncias | Implementado (curado, assinado) |
| 4 | **Fármaco × Alimento/fito** | Drug to Food + RENISUS + Memento | 570 registros | Implementado |
| 5 | **Fármaco × Doença** | `Drug-disease` + bulas | 488 registros | **Carregado, não verificado → não alerta** |
| 6 | **Fármaco × Gestação/lactação** | Drug finder + bulas | 488 registros | Implementado |
| 7 | **Duplicidade terapêutica** | ATC (mesmo 5º nível) | 6.996 classes | Implementado |
| 8 | **Fármaco × Alergia** | Ficha do paciente + ATC | — | Implementado |
| — | **Fármaco × Reação adversa** | **VigiMed (1.093.739)** | 94% vinculáveis | **NÃO EXISTE no sistema** |
| — | **Fármaco × Faixa etária** | `TA_RESTRICAO_MEDICAMENTO` (16.395) | carregado no acervo | **NÃO USADO** |
| — | **Fármaco × Exame laboratorial** | — | — | Sem fonte no acervo |

Os módulos 2, 3 e 4 são o diferencial do trabalho: o concorrente nacional é hospitalar e não tem nenhum deles.

---

## 4. Chaves de junção — quais funcionam e quais não

| Chave | Liga | Taxa medida | Observação |
|---|---|---:|---|
| `skeleton(nome)` | qualquer fonte ↔ âncora BR | 6% a 64% | Depende da fonte; ver §4 da auditoria |
| **EAN** | caixa física ↔ apresentação | determinístico | 26.762 carregados; melhor chave do sistema |
| Registro ANVISA | produto ↔ bula ↔ preço | alta | 9 dígitos, presente em ANVISA/CMED/bulário |
| `CO_SUBSTANCIA` | produto ↔ substância | 69,5% | 30,5% dos registros ANVISA não têm |
| Código ATC | substância ↔ classe | 51,2% | Melhor cobertura de classe do acervo |
| CAS | substância ↔ química | 72,1% | Medido nas 2.361 linhas de `chave_substancia_br.csv` |
| `IDENTIFICACAO_NOTIFICACAO` | reação ↔ medicamento (VigiMed) | **94%** | Verificado em amostra de 400 mil |
| `DrugID` (DrugBank) | `drugsInfo` ↔ `mapping` | funciona, mas **semântica ambígua** | Descartado: não distingue indicação de contraindicação |
| Nome comercial | `medicine_dataset` ↔ BR | **0%** | Marcas indianas |

---

## 5. Conflitos entre fontes — política

A Fase 20 da especificação exige que conflito nunca seja resolvido em silêncio. O que o acervo já faz, e deve ser mantido:

| Conflito | Volume | Tratamento |
|---|---:|---|
| Gravidade divergente entre DDInter e `db_drug_interactions` | 1.123 pares | Registrado em `auditoria_conflito_gravidade`, não resolvido automaticamente |
| Mesma substância com grafias diferentes na ANVISA | 276 strings | Colapsadas por `skeleton()`, com rastro |
| A–B e B–A na mesma fonte | 74 mil | Deduplicado por par ordenado |
| Nome em inglês que casa com 2 substâncias BR | 71 nomes | **Ambíguo não mapeia** — `ibuprofen` → "ibuprofeno" *e* "levolisinato de ibuprofeno" |
| `.xsl` vs `.json` de alimentos | idênticos | Fica o `.json` |

---

## 6. Onde a cadeia se interrompe

Três interrupções, em ordem de impacto:

1. **Gravidade.** 58.252 das 99.955 interações liberadas (58,3%) estão `NAO_DETERMINADA`, porque `db_drug_interactions` não gradua e o DDInter marca 47.182 pares como `Unknown`. **A gravidade não existe na fonte** — não há processamento que a recupere. Só curadoria.
2. **Conduta.** 154 de 130.317 registros (0,12%). Nenhuma fonte do acervo traz conduta de balcão; é texto que precisa ser escrito por farmacêutico.
3. **Cobertura de substância.** 989 das 2.097 substâncias (47,2%) não têm nenhum dado de interação. Não é falha do motor: é ausência na fonte. Por isso o sistema distingue `SEM_INTERACAO_CONHECIDA` de `SUBSTANCIA_NAO_COBERTA` — e essa distinção é uma invariante de segurança, não um detalhe de interface.
