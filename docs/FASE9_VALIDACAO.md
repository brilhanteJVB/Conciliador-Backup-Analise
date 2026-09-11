# Fase 9 — Validação do sistema inteiro

**Data:** 10/09/2026 · Decisões **D-049** e **D-050**
**Resultado:** o sistema está **APTO PARA EMPACOTAMENTO**, com as ressalvas do §9.

---

## O que esta fase é, e o que ela não é

As fases 1 a 8 validaram um módulo de cada vez. Cada uma tinha duas
verificações, e todas passaram. Esta fase faz a pergunta que nenhuma delas
fazia: **o produto inteiro funciona quando tudo roda junto?**

A diferença não é retórica. Os quatro defeitos reais desta fase são todos de
costura — nenhum deles é um erro dentro de um módulo, e nenhum deles teria
aparecido rodando os testes das fases anteriores mais uma vez.

### LEGENDA DE TERMOS

**E2E (ponta a ponta)** — o teste que percorre o sistema todo, da primeira tela
ao relatório, sem atalho por dentro. **V1 / V2** — as duas verificações
obrigatórias: V1 executa o sistema pelo caminho normal, V2 refaz a mesma
conferência por outro caminho. **Regressão** — teste que existe para impedir que
um defeito já corrigido volte. **Idempotente** — reexecutar não muda nada.
**Convergir** — chegar ao resultado final já na primeira passada, em vez de na
segunda. **Impressão digital (dos dados)** — resumo curto que identifica de qual
banco um resultado saiu. **Fail-closed** — quando falta configuração, o sistema
não emite nada em vez de emitir errado. **Calibração isotônica** — ajuste que faz
a probabilidade do modelo corresponder à frequência observada. **Saturar** — a
calibração devolver exatamente 1,0 (ou 0,0) por a faixa inteira da validação ter
o mesmo desfecho. **Órfão** — linha que sobrou apontando para outra que já não
existe. **`NOT EXISTS`** — cláusula SQL que exige a ausência de uma linha
correspondente; é o que sustenta a quarta trava da previsão.

---

## 1. O que foi construído

| Arquivo | O que faz | Conferências |
|---|---|---:|
| `tests/fase9_cenarios.py` | dez cenários clínicos, cada um do início ao relatório | **90** |
| `tests/fase9_v1_sistema.py` | V1 — onze eixos de auditoria funcional | **166** |
| `tests/fase9_v2_independente.py` | V2 — oito caminhos independentes | **64** |
| `tests/fase9_convergencia.py` | pipeline do zero → 2ª → 3ª passada, e reprodução | **44** |
| `auditoria/05_integridade_acervo.py` | 689 arquivos do acervo, recalculados | **6** |
| `docs/EMPACOTAMENTO.md` | inventário do que a Fase 10 vai precisar | — |

Os três primeiros entram em `pipeline/executar_tudo.py`. Os dois últimos ficam
de fora e são deliberados: o de convergência roda os ETLs (poria a bateria
dentro de si mesma) e o do acervo lê 2,2 GB.

### A bateria completa, depois da Fase 9

| Script | Conferências |
|---|---:|
| `pipeline/90_validacao.py` | 49 |
| `tests/teste_normalizacao.py` | 33 |
| `tests/teste_schema.py` | 54 |
| `tests/verificacao_20_substancias.py` | 11 |
| `tests/verificacao_30_produtos.py` | 19 |
| `tests/verificacao_50_regras.py` | 18 |
| `tests/teste_motor_horarios.py` | 29 |
| `tests/verificacao_motor_horarios.py` | 21 |
| `pipeline/traducao_interacao.py` | 11 |
| `rules/_prioridade.py` | 24 |
| `tests/teste_motor_conciliacao.py` | 35 |
| `tests/verificacao_motor_conciliacao.py` | 18 |
| `app/busca.py` | 14 |
| `tests/teste_aplicacao.py` | 44 |
| `tests/verificacao_aplicacao.py` | 35 |
| `tests/teste_ponta_a_ponta.py` | 14 |
| `tests/teste_regressao.py` | **61** (era 49) |
| `tests/teste_ml.py` | 61 |
| `tests/teste_integracao_ml.py` | 59 |
| `tests/verificacao_integracao_ml.py` | 42 |
| `tests/fase9_cenarios.py` | **90** |
| `tests/fase9_v1_sistema.py` | **166** |
| `tests/fase9_v2_independente.py` | **64** |
| **TOTAL — exit 0, 0 falhas** | **972** |

Fora da bateria, executados nesta fase: `fase9_convergencia.py` **44**,
`05_integridade_acervo.py` **6**, `teste_idempotencia.py` **12**, e
`ml/executar_tudo.py --so-verificacao` (V1 e V2 da camada de ML mais a
regressão de ML), todos com exit 0.

`teste_regressao.py` ganhou **12 travas novas**, uma por defeito desta fase.

---

## 2. Os dez cenários

Farmacologia real do banco, paciente sintético. Os identificadores das
substâncias estão fixados no teste, com o motivo escrito ao lado — um cenário
que depende da ordem do resultado de uma busca não prova nada quando a ordem
muda.

| # | Situação | Fixtura real | Esperado — e obtido |
|---|---|---|---|
| 1 | sem problemas | bromexina + dimeticona + macrogol, os três com **grau zero** no grafo de interações e classes ATC distintas | 0 achados, 0 crítico/alto, ausência **declarada** |
| 2 | interação documentada | varfarina × ibuprofeno | `REGRA`, gravidade MAIOR, prioridade ALTO, **2 evidências de 2 fontes** |
| 3 | previsão do modelo | haloperidol × levomepromazina, sem documento no acervo | 1 achado `MODELO`, INFORMATIVO, **sem nenhuma evidência anexada** |
| 4 | documentada **e** prevista | varfarina × ibuprofeno com previsão forjada de **0,999** | a previsão **não aparece**; a regra documental prevalece; sem alerta duplicado |
| 5 | alergia | dipirona declarada, dipirona em uso | CRÍTICO, com a reação relatada no contexto |
| 6 | contraindicação | glibenclamida + insuficiência renal (bula ANVISA) | `CONTRAINDICADO`, contextualizado, com fonte e trecho |
| 7 | duplicidade | gliclazida + glimepirida (ambas A10BB) | `MESMA_CLASSE_ATC4`, no 4º nível, **não** apresentada como interação |
| 8 | conflito de horário | levotiroxina + carbonato de cálcio no mesmo horário (separação de 4 h) | 2 conflitos na agenda, com justificativa e sem intervalo inventado |
| 9 | informação insuficiente | item não reconhecido, dose ausente, horário ausente | tudo **declarado**; nenhuma conclusão de ausência de risco |
| 10 | divergência | losartana 50 mg prescrita × 100 mg relatada | `DOSE_DIFERENTE` + `SO_NO_RELATO`; intencionalidade **não determinada** |

Todos rodam numa **cópia** do banco. Os cenários 3 e 4 precisam homologar um
modelo, e homologar em produção seria o teste ligando aquilo que a Fase 7
decidiu manter desligado. Ao final, o teste confere que o banco de produção
continua com **0 modelos ativos e 0 atendimentos**.

---

## 3. V1 — auditoria funcional, onze eixos

| Eixo | O que procura | Achado |
|---|---|---|
| 1 | isolamento entre dois pacientes | **defeito real** (§5.1) |
| 2 | persistência — outro **processo** lê o que foi gravado | ok |
| 3 | recálculo — remover, acrescentar, mudar dose, horário, alergia, condição | ok |
| 4 | ML no sistema — treze condições de liberação | ok |
| 5 | integridade do modelo — artefato, versão, semente, espaço, calibrador | ok |
| 6 | dados desatualizados — modelo novo, troca, aposentadoria | ok |
| 7 | resiliência — treze situações que podem dar errado | ok |
| 8 | segurança lógica — órfãos, chaves, ids cruzados | ok |
| 9 | a interface — quatro estados, quatro aparências | ok |
| 10 | relatório — cinco perfis de paciente | ok |
| 11 | desempenho — seis medidas com orçamento declarado | ok |

**Eixo 2 usa um processo separado de propósito.** No mesmo processo, uma
conexão aberta ou um módulo em cache poderiam responder de memória, e o teste
passaria sem que nada tivesse sido gravado.

**Eixo 4 cobre as condições que faltavam.** Além das quatro travas já testadas
na Fase 8: probabilidade **exatamente no limiar** (libera, porque a comparação é
`>=`), **um bilionésimo abaixo** (não libera), o banco recusando ativar modelo
não homologado, e o banco recusando probabilidade 1,5 e −0,1.

**Eixo 5 é a conferência que expôs o D-048.** A impressão digital dos dados é
**recalculada agora** e comparada com a que cada modelo gravou no treino:
`9e9c85ee3ffea5e0` nos dois lados. Também confere que a versão do scikit-learn
instalada é a do artefato (1.9.0) e que, em produção, `limiar_alerta` é NULL e
os dois modelos estão `EXPERIMENTAL`, inativos.

### Desempenho (eixo 11)

| Medida | Orçamento | Medido |
|---|---:|---:|
| análise — 2 medicamentos | 2,0 s | **0,016 s** |
| análise — 6 medicamentos | 3,0 s | **0,021 s** |
| análise — 20 medicamentos | 8,0 s | **0,045 s** |
| tela de resultados com 110 achados | 5,0 s | **0,037 s** |
| busca de medicamento | 1,0 s | **0,000 s** |
| geração do relatório | 5,0 s | **0,032 s** |

Duas ordens de grandeza de folga. **Nada foi otimizado** — não havia o que
otimizar, e otimizar sem gargalo é como o item 21 pediu para não fazer.

---

## 4. V2 — oito caminhos independentes

A V1 executa o sistema pelo caminho normal. Se o caminho normal estiver errado,
ela concorda com o erro. A V2 usa ferramentas diferentes:

| | Caminho | O que refaz |
|---|---|---|
| A | **SQL cru** | a conciliação inteira em SQL, sem tocar no motor: pares documentados, pior gravidade, duplicidade por classe |
| B | **HTML como texto** | a página contada por expressão regular, sem as estruturas do motor |
| C | **recontagem** | 44 tabelas, 15 views, 2.094 substâncias, 1.159 com ATC — contra o que a documentação afirma |
| D | **segunda implementação** | as quatro travas da view reescritas em Python e comparadas linha a linha |
| E | **calibração por fora** | `np.interp` reimplementado sem numpy, aplicado às **600** previsões gravadas |
| F | **leitura do código** | o que cada camada importa, e o que não importa |
| G | **SQL direto** | dois atendimentos montados sem passar pela interface |
| H | **caçada** | previsão apresentada como fato, em HTML, em texto e no banco |

Três resultados que merecem o número:

- **D:** a reimplementação e a view devolveram exatamente o mesmo conjunto —
  168 previsões liberadas de 600, com o limiar de teste em 0,90, diferença
  vazia. E o `NOT EXISTS` da quarta trava só é válido porque `interacao_substancia`
  e `predicao` guardam o par na mesma ordem canônica: **0 linhas fora de ordem
  em cada uma**. Se uma delas aceitasse `(b, a)`, a previsão de um par
  documentado escaparia pela porta da frente.
- **E:** maior diferença entre a calibração reimplementada e a gravada:
  **1,110 × 10⁻¹⁶** — o épsilon do ponto flutuante de dupla precisão.
- **C:** a gravidade ausente continua ausente e declarada — **74.061 de 112.520
  linhas (65,8%)** sem graduação na fonte, exatamente como a Fase 5 registrou.
  Nada foi preenchido para a validação parecer melhor.

---

## 5. Os quatro defeitos reais

### 5.1 A mensagem de um paciente aparecia na tela de outro — **defeito real** (D-049)

A fila de mensagens do Flask é da **sessão do navegador**, não do atendimento.
Com dois atendimentos abertos, a tela de uma paciente que toma varfarina e
ibuprofeno mostrava, no alto:

> Posologia de **Gliclazida 30 mg** salva.

Nenhum dado clínico vazou — achado, resumo, relatório e banco continuaram
corretos, e a V1 confirma isso em oito conferências separadas. O que vazou foi
uma frase sobre outro paciente, num sistema cuja finalidade é não confundir
paciente. Corrigido: `web.avisar()` prende a mensagem ao atendimento;
`base.html` mostra o que é da tela e devolve o resto para a fila.

**Este defeito também expôs um segundo, no meu próprio teste.** A primeira
versão da conferência do eixo 3 procurava `"Ibuprofeno 600 mg"` no HTML inteiro
depois de remover o medicamento — e casava com a mensagem de estado, não com um
achado. Duas falhas, uma causa.

### 5.2 "100% de probabilidade" — **defeito real** (D-050)

A tela do achado previsto dizia:

> o modelo estima **100%** de probabilidade de que o par esteja documentado

três parágrafos abaixo de *"Não há evidência documental para este par"*.

O número estava certo: a calibração isotônica satura, e a faixa mais alta da
validação recebe 1,0 quando todos os pares daquela faixa estavam documentados.
Uma frequência observada num conjunto finito — **não** uma certeza. Escrito como
"100%", ao lado de "nenhuma fonte afirma nada", vira a contradição mais forte que
este sistema poderia produzir. Corrigido: `percentual_previsao()` é o único
formatador, acima de 0,995 sai "acima de 99%", e o valor exato com quatro casas
continua no painel de rastreabilidade, agora com a explicação da saturação.

**Nenhum teste tinha pegado, e a razão importa.** Todos conferiam *estrutura* —
que o campo existe, que o bloco está separado, que a evidência é nenhuma.
Nenhum lia a frase. Este foi encontrado abrindo a tela e lendo.

### 5.3 Código interno chegando cru à tela — **defeito real, menor** (D-050)

O chip do achado mostrava `interacao prevista`: o subtipo do banco, sem acento,
em minúsculas, contra a regra do projeto de que todo vocabulário do banco é
traduzido em `rotulos.py`. Corrigido com `rotulos.SUBTIPO` (26 entradas), com
recuo para o comportamento antigo em valor desconhecido.

### 5.4 Cinco pacientes órfãos no banco de produção — **defeito de teste, com efeito real**

`tests/verificacao_aplicacao.py` apagava um atendimento de propósito no eixo 5,
para conferir o cascata. Depois, `limpar()` procurava o paciente **a partir do
atendimento** — que já não existia. Cada execução deixava uma linha
`"Integridade B"` no banco de produção; havia **cinco** acumuladas.

Não é dado clínico e não afetava resultado nenhum. Mas é resíduo de teste em
produção, e o teste que o encontrou é o mesmo que agora o impede: o eixo final
da V1 confere que produção termina com 0 modelos ativos, 0 atendimentos e
**0 pacientes órfãos**.

### Uma asserção fraca herdada da Fase 8

`teste_integracao_ml.py` conferia a ausência de evidência assim:

```python
ok("o bloco mostra 'Evidência documental: nenhuma'",
   "Evid" in html and "nenhuma" in html)
```

`"Evid"` e `"nenhuma"` soltos casam com quase qualquer página do sistema. A
asserção passava sem provar nada. Trocada pela conferência estrutural, **dentro**
do bloco previsto: `>Evidência documental</div>` seguido de `>nenhuma</div>`.

---

## 6. Os treze falsos positivos

Foram meus, e a classificação importa tanto quanto a dos defeitos reais. Nenhum
deles motivou mudança no produto.

| | O que acusou | O que era |
|---|---|---|
| 1 | cenário 3 sem previsão | homologuei o modelo **sem** previsões gravadas |
| 2 | conflito sem descrição | usei nomes de campo que o `Conflito` não tem |
| 3 | relatório do cenário 10 "citando" o cenário 1 | `"Cenário 1"` é substring de `"Cenário 10"` |
| 4 | painel sem aviso de SHAP | o template escreve `Não é SHAP`, com maiúscula |
| 5 | processo novo falhando | a chave do dicionário é `nome`, não `paciente_nome` |
| 6 | manifesto sem amarra de versão | o aviso diz `scikit-learn`, não `sklearn` |
| 7 | atendimento inexistente devolvendo 302 | a convenção do sistema é redirecionar com mensagem, não 404 |
| 8 | achado citando substância de fora | eram achados de **histórico**, de uma conciliação anterior — e devem mesmo continuar lá |
| 9 | duplicidade divergindo do SQL | o achado de classe não preenche `substancia_a_id`, de propósito: a classe pode ter mais de duas substâncias |
| 10 | coluna `documento` inexistente | é `documento_origem` |
| 11 | inserção direta recusada | faltou `reconhecimento`, que é `NOT NULL` |
| 12 | ausência de evidência não encontrada | rótulo e valor são dois `<div>` irmãos |
| 13 | probabilidade sem percentual | o teste não acompanhou a correção 5.2 |

O nº 8 é o mais instrutivo. A conciliação gravada é **histórico**: cada análise
grava uma linha nova, e as antigas ficam. Um achado antigo pode citar um
medicamento removido depois — é o registro correto do que se avaliou naquele
momento. A tela não lê essas linhas: `resultado_atual` recalcula. A conferência
certa é sobre o resultado **vivo**, e é assim que ela está agora.

### E uma regressão que eu mesmo introduzi

A primeira versão do filtro de mensagens (5.1) escondia mensagem de outro
atendimento **em qualquer tela**. Como a mensagem *"Atendimento X não
encontrado"* redireciona para a tela inicial, que não pertence a atendimento
nenhum, ela era engolida. A V1 pegou no mesmo ciclo. A regra final esconde
apenas quando a tela atual pertence a **outro** atendimento.

---

## 7. Convergência e reprodutibilidade

`tests/fase9_convergencia.py` guarda uma cópia do banco, reconstrói do zero,
roda mais duas vezes, compara tudo, e devolve a cópia guardada — porque
`--recriar` apaga `modelo` e `predicao`, e há dois modelos e 600 previsões que
levaram vinte minutos para existir.

Colunas de hora de entrada (`carga.data_importacao`, `substancia.criado_em`,
`auditoria_conflito.registrado_em`) ficam de fora, uma a uma e declaradas —
nunca por "ignorar o que não bate".

**Resultado: 44 de 44.** A 1ª passada já é o ponto fixo.

| | 1ª (do zero) | 2ª | 3ª |
|---|---:|---:|---:|
| substâncias | 2.094 | 2.094 | 2.094 |
| **com ATC** | **1.159** | **1.159** | **1.159** |
| sinônimos INN | 983 | 983 | 983 |
| interações f×f | 112.520 | 112.520 | 112.520 |
| pares distintos | 94.770 | 94.770 | 94.770 |
| regras de administração | 723 | 723 | 723 |
| regras de separação | 59 | 59 | 59 |
| evidências | 153.647 | 153.647 | 153.647 |
| lotes de carga | 12 | 12 | 12 |
| **impressão digital** | `9e9c85ee3ffea5e0` | idem | idem |

E a reprodução: reconstruir do zero devolveu **o banco anterior, tabela por
tabela, com 0 diferenças** — e a mesma impressão digital com que os dois
modelos foram treinados. É isto que torna o resultado da Fase 7 reprodutível: o
mesmo corpus produz o mesmo banco, e o modelo continua válido sobre ele.

O defeito de convergência que a Fase 8 encontrou (1.153 numa passada, 1.159 em
duas) está corrigido e agora tem trava permanente.

---

## 8. Acervo original — recalculado, não herdado

`auditoria/05_integridade_acervo.py` percorre `C:\Conteudos banco de dados tcc`
em modo somente leitura e refaz a conta.

| | |
|---|---|
| arquivos | **689** — o mesmo número do inventário de 09/09 |
| bytes | **2.268.000.886** — idêntico |
| tamanho divergente | **0** |
| hash divergente | **0** |
| arquivo novo ou desaparecido | **0** |

**ACERVO INTACTO — 689 arquivos, 0 modificados.**

Uma ressalva declarada: o inventário de 09/09 gravou `hash_rapido`, que é
sha256 do tamanho mais os **primeiros 8 MB**. É cego para alteração depois do
oitavo megabyte. Esta execução recalcula com a mesma fórmula (para que a
comparação seja legítima) **e** grava um manifesto novo, `acervo_sha256.json`,
com sha256 do conteúdo **inteiro** dos 689 arquivos. A partir da próxima
execução existe uma linha de base que enxerga o arquivo todo. Esta primeira
grava a linha de base; ela **não** prova que nada mudou depois do 8º MB, e o
script diz isso na saída em vez de contar como prova.

---

## 9. Critério de aprovação — item a item

O item 25 exige treze demonstrações. Nenhuma delas é "todos os testes passaram".

| | Exigido | Estado |
|---|---|---|
| 1 | fluxo completo funcionando | ✅ 10 cenários, do início ao relatório |
| 2 | isolamento de pacientes | ✅ após correção D-049 |
| 3 | persistência | ✅ conferida por outro processo |
| 4 | recálculo | ✅ remoção, acréscimo, dose, horário, alergia, condição |
| 5 | pipeline convergente | ✅ ponto fixo na 1ª passada |
| 6 | ML corretamente protegido | ✅ treze condições; reimplementação bate exatamente |
| 7 | previsões diferenciadas | ✅ quatro estados, quatro aparências |
| 8 | achados rastreáveis | ✅ 0 previsões sem ponteiro para modelo e versão |
| 9 | relatório correto | ✅ cinco perfis, sem mistura entre pacientes |
| 10 | acervo intacto | ✅ 689 arquivos, 0 modificados |
| 11 | regressão sem quebra | ✅ bateria completa, 0 falhas |
| 12 | falhas tratadas | ✅ treze situações, nenhum erro 500 |
| 13 | documentação atualizada | ✅ este documento, STATUS, ARQUITETURA, DECISIONS, CLAUDE |

### RESULTADO: **APTO PARA EMPACOTAMENTO**

O que sustenta a aprovação, objetivamente:

- os quatro defeitos reais foram **corrigidos e travados por regressão**;
- o pipeline converge na primeira passada e **reproduz o banco byte a byte**;
- o acervo está intacto, recalculado;
- a camada de ML está **desligada e estruturalmente incapaz** de emitir
  qualquer coisa sem ato humano registrado, e isso foi verificado por duas
  implementações independentes;
- o desempenho tem duas ordens de grandeza de folga;
- o produto empacotável depende de **uma** biblioteca externa (Flask) e não
  tem **um único caminho absoluto**.

### O que o "apto" NÃO significa

1. **Não é validação clínica.** Nenhum farmacêutico avaliou nenhum achado deste
   sistema. Zero linhas em `anotacao_profissional`. A Fase 9 mediu que o
   software faz o que promete — não que o que ele promete seja clinicamente
   suficiente.
2. **Apto para empacotar não é apto para distribuir.** A Fase 10 tem duas
   pendências de engenharia que não são cosméticas, ambas em
   `docs/EMPACOTAMENTO.md`: o banco precisa ser gravável (não pode viver em
   `Program Files`), e **conhecimento e atendimento estão no mesmo arquivo** —
   atualizar o primeiro sobrescreveria o segundo. Nenhuma das duas impede o
   empacotamento; as duas impedem a segunda versão.
3. **As lacunas de dados continuam as mesmas.** 65,8% das interações sem
   gravidade graduada, fármaco × doença cobrindo 4,9% das substâncias, zero
   regras revisadas por farmacêutico. A Fase 9 não as reduziu e não as
   escondeu.

---

## 10. Como repetir esta validação

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"

# bateria completa (inclui os três testes da Fase 9)
PYTHONIOENCODING=utf-8 "$PY" pipeline/executar_tudo.py

# os três, isolados
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_cenarios.py
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_v1_sistema.py
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_v2_independente.py

# fora da bateria, deliberados
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_convergencia.py       # ~1 min
PYTHONIOENCODING=utf-8 "$PY" auditoria/05_integridade_acervo.py # ~3 min
```

`fase9_convergencia.py` reconstrói o banco e o devolve ao final. Se for
interrompido no meio, a cópia guardada fica no diretório temporário que ele
imprime na primeira linha.
