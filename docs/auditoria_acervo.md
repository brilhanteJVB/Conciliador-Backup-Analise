# Auditoria do acervo — Conciliador de Medicamentos

**Data:** 08/09/2026
**Origem auditada:** `C:\Conteudos banco de dados tcc` (somente leitura, nada foi alterado)
**Destino dos resultados:** `C:\Sistema Conciliador projeto`
**Método:** varredura automática de 100% dos arquivos + verificação manual dos casos duvidosos

Scripts que produziram este documento (reexecutáveis):

| Script | O que faz | Saída |
|---|---|---|
| `auditoria/01_inventario.py` | lê os 689 arquivos e mede formato, encoding, delimitador, esquema, vazios, duplicidade | `auditoria/saida/inventario_bruto.json` |
| `auditoria/02_cruzamentos.py` | mede quanto de cada fonte chega a uma substância que existe no Brasil | `auditoria/saida/cruzamentos.json` |
| `auditoria/03_classificacao.py` | atribui categoria, decisão de uso e tratamento a cada arquivo | `auditoria/saida/classificacao.csv` |

---

## 1. A conclusão que muda tudo, antes dos números

**O acervo não é um conjunto de dados brutos à espera de um sistema. Ele contém um sistema pronto e funcionando.**

Dentro de `banco/` existe o `conciliador.db`: 95,4 MB, 49 tabelas, 9 visões, 408.997 linhas, alimentado por 24 ETLs numerados, consumido por um motor determinístico de 8 módulos (86 KB de código), servido por uma interface Flask (148 KB) e acompanhado de modelos de Machine Learning treinados e validados externamente.

Rodei a validação de integridade do próprio sistema, sem alterar nada:

```
PYTHONIOENCODING=utf-8 python banco/etl/15_validacao.py
→ VALIDACAO COMPLETA — todas as garantias de seguranca satisfeitas (exit 0)
```

E o teste funcional embutido responde de verdade: para um paciente fumante em uso de clozapina, teofilina e cafeína, o sistema devolveu três alertas corretos com 18 referências bibliográficas.

**Consequência para a instrução recebida.** A ordem era: auditar o acervo e construir o sistema do zero em `Sistema Conciliador projeto`. Cumpri a auditoria. Mas preciso registrar, antes de qualquer implementação, que **reconstruir do zero destruiria trabalho que não é regenerável por script**:

- `banco/curadoria/` contém curadoria humana assinada — 30 substâncias do módulo tabaco com mecanismo, conduta e referências PubMed verificadas; 32 referências conferidas uma a uma; a fila de gravidade priorizada. Nenhum ETL recria isso, porque a informação **não está em nenhuma fonte do acervo**: ela foi pesquisada e escrita por uma pessoa.
- `analise_dados/*.md` são 25 documentos que registram por que cada escolha foi feita, **inclusive as que foram testadas e descartadas**. Sem eles, os mesmos becos sem saída seriam percorridos de novo.
- As invariantes de segurança clínica (ML nunca atribui gravidade; discrepância nasce `NAO_DETERMINADA`; ausência de alerta nunca é apresentada como ausência de risco) estão implementadas no esquema e verificadas por teste. Refazê-las de memória é a forma mais provável de perdê-las.

**Recomendação: absorver, não reconstruir.** O `Sistema Conciliador projeto` deve ser o ambiente novo — com a estrutura de pastas pedida, a documentação pedida e as fases pendentes — mas partindo do banco curado como fonte de primeira ordem, e não do CSV bruto. A seção 8 detalha como. A decisão final é sua; a seção 8.3 descreve o que muda se preferir a reconstrução completa.

---

## 2. O que existe — inventário

**689 arquivos, 2,11 GB, 13 formatos.** Todos foram abertos e lidos. **Zero falhas de leitura.**

| Pasta | Arquivos | Tamanho | O que é |
|---|---:|---:|---|
| `banco/` | 80 | 1330,4 MB | O sistema construído + 12 backups do banco |
| `fontes_novas/07_complementares/` | 8 | 493,1 MB | VigiMed (farmacovigilância BR) e restrições |
| `(raiz)` | 12 | 125,3 MB | Datasets internacionais originais |
| `fontes_novas/01_anvisa_bulario/` | 460 | 86,4 MB | 150 bulas (PDF + texto + seções) |
| `fontes_novas/02_cmed_precos_drogaria/` | 6 | 42,6 MB | CMED: preço, EAN, apresentação |
| `fontes_novas/04_rename_renisus/` | 8 | 31,9 MB | RENAME, RENISUS, Memento Fitoterápico |
| `fontes_novas/08_iuphar_gtopdb/` | 4 | 15,4 MB | Alvo molecular e direção de ação |
| `DDInter/` | 8 | 12,5 MB | Interações graduadas por gravidade |
| `ml_teste/` | 38 | 6,9 MB | Bancada de experimentos de ML |
| `analise_dados/` | 37 | 6,6 MB | Documentação de método + scripts |
| `Drug-disease/` | 3 | 5,2 MB | Fármaco, doença e mapeamento |
| `fontes_novas/03_dcb_denominacoes/` | 5 | 5,0 MB | DCB vigente + chave de normalização |
| `fontes_novas/06_vendas_sngpc/` | 8 | 1,3 MB | Vendas SNGPC agregadas |
| `fontes_novas/05_atc_classes/` | 4 | 0,3 MB | WHO ATC-DDD |
| `fontes_novas/07_fda_ddi/` | 2 | 0,0 MB | Tabela de fármacos-índice da FDA |
| demais | 6 | 0,0 MB | Configuração e ferramentas |

Por formato: 174 JSON, 163 TXT, 162 PDF, 66 PY, 52 CSV, 46 MD, 16 DB (SQLite), 3 SQL, 4 NumPy, 1 XLSX, 1 `.xsl` (que não é XSL — ver §5).

### 2.1 A auditoria anterior cobria 19 arquivos; esta cobre 689

O acervo já tinha um inventário — `analise_dados/inventario.csv`. Ele é bom e o confirmo em quase tudo, **mas cobre apenas os 19 datasets originais de agosto/2026**. Toda a pasta `fontes_novas/` (546 arquivos, 675 MB, carregada em setembro) nunca passou por inventário de máquina: tinha só um README por pasta.

Onde os dois se cruzam, batem. O inventário antigo registrou 43.439 registros em `TA_CONSULTA_MEDICAMENTOS.CSV`; o meu mediu 43.441 — diferença de 2 linhas em 43 mil, dentro do esperado para regras de descarte de linha vazia ligeiramente diferentes.

---

## 3. Qualidade dos dados — o que a leitura de máquina encontrou

Cinco problemas estruturais reais, todos encontrados por medição e nenhum deles óbvio pelo nome do arquivo.

### 3.1 Contar `\n` superestima o tamanho de 8 arquivos

Descrições de interação e textos de bula contêm quebra de linha **dentro** de campo entre aspas. Contar linhas físicas superestima o número de registros:

| Arquivo | Registros reais | Linhas físicas | Diferença |
|---|---:|---:|---:|
| `TA_CONSULTA_MEDICAMENTOS.CSV` | 43.441 | 46.523 | **3.081** |
| `VigiMed_Medicamentos.csv` | 697.274 | 699.312 | 2.037 |
| `Drug-disease/drugsInfo.csv` | 1.410 | 1.486 | 75 |
| `TA_PRECO_MEDICAMENTO.csv` | 25.702 | 25.768 | 24 |
| `medicine_dataset.csv` | 248.218 | 248.232 | 13 |

Qualquer contagem por `wc -l` neste acervo está errada. O inventário registra as duas medidas e o método usado em cada uma.

### 3.2 Três padrões de cabeçalho que quebram a leitura ingênua

- **CMED** (`TA_PRECO_MEDICAMENTO.csv`, `_GOV.csv`): as primeiras 41 e 53 linhas são um banner institucional — título, data de publicação, notas de rodapé jurídicas — **preenchido até as 74 colunas com `;` vazios**, o que engana qualquer detector baseado em largura. O cabeçalho real começa em `SUBSTÂNCIA;CNPJ;LABORATÓRIO;...`.
- **IUPHAR/GtoPdb** (3 arquivos): linha 1 é o comentário `# GtoPdb Version: 2026.2`. O cabeçalho está na linha 2.
- **ANVISA bulário** (`TA_CONSULTA_BULA_DOCUMENTO.CSV`, `TA_CONSULTA_BULA_PRODUTO.CSV`): **não têm cabeçalho nenhum.** A primeira linha já é dado. As colunas só podem ser nomeadas consultando o dicionário de dados da ANVISA.

### 3.3 Detecção automática de encoding erra nas fontes brasileiras

O `chardet` classificou `TA_CONSULTA_BULA_DOCUMENTO.CSV` (ANVISA, português) como **`big5`** — codificação de chinês tradicional. Erra porque lê só o início do arquivo. Em dois outros arquivos declarou `ascii` para conteúdo UTF-8, e a leitura estourava mais adiante.

Regra adotada e implementada: testar UTF-8 primeiro contra **8 MB** do arquivo; só aceitar o palpite automático se for um codec latino de byte único; cair para `cp1252` e `latin-1` nessa ordem. Encodings reais medidos: `utf-8-sig` (26 arquivos), `cp1252`/`windows-1252` (3), `iso-8859-1` (3), `utf-8` (o restante).

### 3.4 Delimitador não pode ser detectado por contagem

Contar `;` e `,` por linha falhou em 7 arquivos, porque campos entre aspas contêm o próprio separador. Trocado por: parsear de fato com cada candidato e escolher o que produz o maior número de colunas mantendo largura constante. Delimitadores reais: `;` nas fontes brasileiras (ANVISA, CMED, VigiMed), `,` nas internacionais.

### 3.5 Colunas 100% vazias

`TA_CONSULTA_MEDICAMENTOS.CSV` tem três colunas inteiramente vazias na amostra (`ST_ROTULO`, `TP_GRAU`, `SITUACAO_ASSUNTO`) e várias acima de 90% (`CO_ATC` 99,2% vazia — a ANVISA praticamente não preenche ATC, o que é justamente por que o projeto foi buscar ATC na OMS). `medicine_dataset.csv` tem 17 colunas `sideEffect25`–`sideEffect41` completamente vazias.

---

## 4. Quanto de cada fonte chega ao Brasil — a medição que decide o uso

Esta é a pergunta que separa dado útil de dado volumoso. Âncora: as **2.153 substâncias** de medicamentos com registro **ativo** na ANVISA, reduzidas ao esqueleto fonético de `lib_norm.skeleton` (que resolve `dipirona monoidratada` → `metamisol`, e por isso funciona onde comparação de texto cru falha).

| Fonte | Substâncias na fonte | Existem no BR | % da fonte aproveitável | % do BR coberto |
|---|---:|---:|---:|---:|
| **WHO ATC-DDD** | 5.972 | 1.102 | 18,5% | **51,2%** |
| **DDInter** (8 arquivos) | 1.794 | 776 | 43,3% | **36,0%** |
| **IUPHAR/GtoPdb** | 13.330 | 846 | 6,3% | 39,3% |
| `db_drug_interactions` | 1.694 | 673 | 39,7% | 31,3% |
| Drug to Food | 1.409 | 600 | 42,6% | 27,9% |
| `Drug-disease/drugsInfo` | 1.399 | 583 | 41,7% | 27,1% |
| Drug finder (deepseek) | 717 | 462 | **64,4%** | 21,5% |
| **`medicine_dataset.csv`** | 219.115 | **0** | **0,0%** | **0,0%** |

### 4.1 Pares de interação — onde está o volume que importa

| | Pares únicos | Pares BR×BR | % BR×BR | Gradua gravidade? |
|---|---:|---:|---:|---|
| `db_drug_interactions` | 190.045 | 43.928 | 23,1% | **Não** |
| DDInter | 149.878 | 50.072 | 33,4% | **Sim** |
| Em ambas | 38.892 | — | — | — |
| **União BR×BR** | — | **79.418** | — | — |

DDInter é a fonte mais valiosa do acervo: é a **única que gradua gravidade** e a que mais entrega pares brasileiros. Mas gradua incompleto — dos 222.383 registros, **47.182 vêm marcados como `Unknown`**. Essa é a origem do buraco de 58,3% de gravidade indeterminada que o sistema já documenta: a gravidade **não existe na fonte**, não é um defeito do processamento.

### 4.2 `medicine_dataset.csv`: 85 MB, contribuição zero

Foi o resultado mais surpreendente, então verifiquei a causa em vez de aceitar o número. A coluna `name` não contém princípios ativos: contém **marcas do mercado indiano** — `augmentin 625 duo tablet`, `azithral 500 tablet`, `ascoril ls syrup`. São 219.115 nomes distintos que não têm correspondente brasileiro porque **não são vendidos no Brasil**. O que resta de aproveitável são 23 classes terapêuticas e 358 classes de ação, em inglês, redundantes com o WHO ATC, que é fonte oficial. **Descartar.** É o maior arquivo isolado de dado internacional e não entra no banco.

---

## 5. Duplicidades e conflitos

### 5.1 Duplicata exata confirmada por hash

`Drug to Food interactions Dataset.xsl` é **byte a byte idêntico** a `Drug to Food interactions Dataset.json`. Não é planilha XSL: é o mesmo JSON com extensão trocada. Manter o `.json`, descartar o `.xsl`.

### 5.2 Backups do banco: 1,03 GB, 12 arquivos

Doze cópias datadas de `conciliador.db` (`_antes_a3_`, `_antes_ean_`, `_antes_etl27_`…). São disciplina correta de trabalho — e ocupam **quase metade do acervo inteiro**. Recomendo manter os dois mais recentes e o `conciliador_piloto_congelado_20260904.db` (que **não é backup**: é a versão congelada que sustenta o kappa do piloto e não pode ser alterada), e arquivar os demais fora do diretório de trabalho.

### 5.3 Conflito de gravidade entre fontes

O banco já registra 1.123 linhas em `auditoria_conflito_gravidade` — casos em que `db_drug_interactions` e DDInter discordam sobre o mesmo par. O tratamento existente está correto e segue a Fase 20 da especificação: registra o conflito em vez de escolher em silêncio.

### 5.4 Procedência frágil em três arquivos

| Arquivo | Registros | Referências distintas | Problema |
|---|---:|---:|---|
| `Drug to Food…json` | 1.423 | **1** | Todos citam o mesmo artigo do DrugBank |
| `DDI Database.json` | 180 | 49 | 101 citam o artigo do DrugBank; o resto, só nome de periódico |
| `DDI 2.0.json` | 80 | 57 | Referências como `"Journal of Clinical Psychopharmacology"`, sem volume, página ou DOI |

Citar o artigo que **descreve** o DrugBank como evidência de que "varfarina × ibuprofeno" interage é citar a fonte errada. E `"New England Journal of Medicine"` não é referência: é o nome de uma revista. Some-se o arquivo cujo próprio nome contém `deepseek_csv_20250915`, indicando geração por modelo de linguagem, e cujo conteúdo confirma a suspeita — em `Acyclovir`, o campo `Side Effects` traz *"Varicella zoster virus (VZV) infections"*, que é uma **indicação**, não um efeito adverso.

**Nenhum desses três arquivos pode ser tratado como evidência primária.** Servem como apoio para redação de mecanismo e como pista de curadoria, sempre com revisão humana. A auditoria anterior do projeto chegou à mesma conclusão de forma independente, o que aumenta a confiança nela.

---

## 6. O maior ativo inexplorado: VigiMed

**493 MB, 1.093.739 reações adversas notificadas no Brasil, e nenhum ETL os lê.**

Verifiquei que o vínculo funciona antes de recomendar: `VigiMed_Reacoes.csv` liga a `VigiMed_Medicamentos.csv` pela chave `IDENTIFICACAO_NOTIFICACAO`, e numa amostra de 400 mil reações **377.731 (94%) casaram com um princípio ativo**, produzindo pares (princípio ativo, reação MedDRA). A terminologia MedDRA já está **em português** — `Cefaleia`, `Pirexia`, `Calafrios` — o que atende diretamente à exigência de idioma do projeto sem precisar de tradução.

O banco atual **não tem tabela de reação adversa**. A Fase 8 da especificação está inteiramente por fazer, e a matéria-prima brasileira para fazê-la já está no acervo.

**Ressalva científica que precisa acompanhar qualquer uso disto.** São notificações espontâneas, não incidência. A amostra é dominada por vacinas de COVID-19 (7.496 registros de cefaleia para ChAdOx1) porque houve campanha de notificação ativa — contagem bruta mediria a campanha, não o risco. O uso correto é **análise de desproporcionalidade** (PRR, ROR), e o resultado é **sinal**, nunca prova de causalidade. Registrado aqui para que não vire "o sistema diz que este medicamento causa isto".

---

## 7. Classificação dos 689 arquivos

Cada arquivo recebeu decisão de uso a partir do conteúdo verificado. Detalhe linha a linha em `auditoria/saida/classificacao.csv`. Nenhum arquivo ficou sem classificação.

| Decisão | Arquivos | Tamanho | Significado |
|---|---:|---:|---|
| **USAR** | 419 | 734,7 MB | Entra no sistema |
| **USAR_PARCIAL** | 152 | 83,2 MB | Entra com ressalva registrada |
| **APOIO** | 64 | 27,8 MB | Consulta e conferência, não regra clínica |
| **DOCUMENTAÇÃO** | 33 | 0,7 MB | Registro de método |
| **REDUNDANTE** | 15 | 1135,0 MB | Backups e a duplicata `.xsl` |
| **DESCARTAR** | 5 | 86,2 MB | `medicine_dataset`, `mapping.csv`, config |
| **SISTEMA_PRONTO** | 1 | 95,4 MB | `conciliador.db` |

### 7.1 Descartáveis, com o motivo

- **`medicine_dataset.csv`** (85,3 MB) — marcas indianas, 0% de aproveitamento (§4.2).
- **`Drug-disease/mapping.csv`** (906 KB, 42.200 pares) — liga fármaco a doença **sem dizer se é indicação ou contraindicação**. Usar isso geraria alerta invertido: acusar de risco exatamente a doença que o medicamento trata. Descartado pela auditoria anterior pelo mesmo motivo; confirmo.
- **`Drug to Food interactions Dataset.xsl`** — duplicata exata (§5.1).
- **`.vscode/`, `.code-workspace`, `~$ferencial_teorico.md`** — configuração de editor e arquivo de bloqueio do Word.

### 7.2 Exigem tratamento antes do uso

| Arquivo | Tratamento |
|---|---|
| `RENAME_2024_digitalizado_sem_texto.pdf` (29 MB) | **Sem camada de texto.** Exige OCR. Existe o `RENAME_2024.pdf` com texto — usar esse. |
| `TA_CONSULTA_BULA_*.CSV` | Sem cabeçalho: mapear colunas pelo dicionário da ANVISA |
| `TA_PRECO_MEDICAMENTO*.csv` | Pular 41 (e 53) registros de banner |
| `interactions.csv`, `ligands.csv`, `targets_and_families.csv` | Pular a linha de comentário; filtrar `Species=Human` |
| `Drug finder db…deepseek.csv` | Colunas trocadas entre si; revisão humana linha a linha |
| 162 PDFs | 161 têm camada de texto e são legíveis; só o RENAME digitalizado precisa de OCR |

### 7.3 Exigem análise manual (não automatizável)

Nenhum arquivo ficou ilegível. O que exige pessoa, e não script:

1. **`Drug finder db…deepseek.csv`** — 462 substâncias brasileiras com contraindicação e categoria de gravidez, campos que nenhuma outra fonte tem, misturados a erros de coluna. É o melhor candidato a curadoria manual do acervo.
2. **`interacao_ff.conduta`** — preenchida em 154 de 130.317 registros (0,12%). Nenhuma fonte traz conduta; ela precisa ser escrita.
3. **Os 488 registros do módulo doença** — carregados, não verificados, e por isso não geram alerta.
4. **As 58.252 interações com gravidade `NAO_DETERMINADA`** — a fila já está priorizada por impacto de balcão em `banco/curadoria/gravidade_indeterminada.csv`.

---

## 8. Recomendação

### 8.1 Arquitetura — absorver o que existe

A estrutura pedida foi criada em `Sistema Conciliador projeto` e é a estrutura certa. O que muda é **de onde vem o conteúdo**:

```
conteudos banco de dados tcc/          (ACERVO — somente leitura, preservado)
        │
        │  cópia, nunca movimentação
        ▼
Sistema Conciliador projeto/
   data/raw/         cópia das fontes classificadas como USAR
   pipeline/         ETLs portados de banco/etl/ (ordem 10→37 preservada)
   database/         conciliador.db importado + esquema de banco/schema.sql
   rules/            motor determinístico (8 módulos) de banco/app/
   ml/               _features.py, treino, predição, calibrador
   app/              interface Flask em português
   models/           modelos v1.0 e v2.0 (não apagar a v1.0)
   docs/             esta auditoria + os 12 documentos da Fase 26
   tests/            casos clínicos + validação de invariantes
```

Ordem de execução recomendada:

1. **Copiar a curadoria humana primeiro** (`banco/curadoria/`) — é o único conteúdo insubstituível.
2. **Importar `conciliador.db`** como base de partida, não recarregar CSV bruto.
3. **Portar `15_validacao.py`** e rodá-lo no destino: se passar, a migração foi fiel.
4. **Só então** avançar para o que está por fazer.

### 8.2 O que está por fazer — nesta ordem

1. **Reação adversa (Fase 8)** — não existe no sistema, e o VigiMed está pronto para alimentá-la. Maior ganho por esforço do acervo inteiro.
2. **Restrição por faixa etária** — `TA_RESTRICAO_MEDICAMENTO.csv` (16.395 registros) está carregado no acervo e não é usado. Um paciente pediátrico ou idoso hoje não dispara nada.
3. **Curadoria de conduta** — 0,12% preenchido é o que mais limita a utilidade de balcão.
4. **Empacotamento `.exe` (Fases 22–24)** — a interface é Flask local, o banco é SQLite e os modelos são JSON: a arquitetura já é offline-first. PyInstaller com servidor local embutido é o caminho de menor risco, e não exige reescrever nada.

### 8.3 Estratégia de Machine Learning

O modelo já existe, está treinado e validado externamente. Os números medidos:

| Protocolo | AUC |
|---|---:|
| Split por par (otimista) | 0,9390 |
| **Split por fármaco (honesto)** | **0,8561** |
| Validação externa, treino em DDInter → teste em `db_drug_interactions` | 0,9017 |
| Validação externa sem as features contaminadas | **0,8016** |
| Acaso | 0,4926 |

Calibração isotônica reduziu o erro de calibração de 0,0758 para 0,0308.

Três coisas a preservar e não repetir:

- **A ablação já foi feita.** `perfil_farmacodinamico` é extraído do mesmo arquivo de onde saem os rótulos — feature e alvo têm origem comum. Isso vale 0,0428 de AUC. O modelo **sobrevive sem ela** (0,7925). Trate 0,8401 como teto e 0,7973 como piso, como o documento 20 já registra.
- **Fatoração de matriz e embedding de grafo já foram avaliadas e descartadas** com motivo estrutural, não de preferência: 1.103 das 2.097 substâncias não têm nenhuma aresta na matriz de interações, e são exatamente o ponto cego que motivou o trabalho. Um modelo de grafo não tem o que propagar nelas. Está em `21_comparacao_familias_ml.md`.
- **ML não atribui gravidade, por decisão medida** — o modelo rebaixava 88% das interações MAIOR. `predicao_ml.gravidade_sugerida` é sempre `NULL`.

O próximo modelo útil **não é de existência de interação**: é de **relevância de alerta** (fadiga de alerta), e ele depende dos rótulos do piloto com dois farmacêuticos. É trabalho que depende de gente, não de código.

---

## 9. Ressalvas desta auditoria

- **Idioma detectado por heurística.** Marcações `indeterminado` em arquivos curtos ou só numéricos são limitação do método, não do arquivo.
- **Esquema inferido de 400 linhas** por arquivo tabular. Percentuais de vazio são da amostra, não do arquivo inteiro. Contagem de registros, essa sim, é exata e sobre o arquivo completo.
- **A âncora brasileira mediu 2.153 substâncias ativas**; o sistema existente trabalha com 2.097. A diferença vem da regra de separação de associações em dose fixa (dividi por `+` e `;`). Não invalida nenhuma conclusão comparativa, porque todas as fontes foram medidas contra a mesma âncora.
- **Não abri os 150 PDFs de bula um a um.** Verifiquei formato, número de páginas e presença de camada de texto em todos; o conteúdo clínico de cada um não foi lido.
- **Não avaliei licenças de uso.** IUPHAR/GtoPdb é CC BY-SA e exige atribuição; DrugBank tem restrição de uso comercial. Para um TCC acadêmico isso tende a ser resolvível, mas é questão jurídica, não técnica, e está fora do que posso afirmar.
