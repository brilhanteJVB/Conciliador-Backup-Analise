# Status por fase

Atualizado a cada fase. Estados: `NÃO INICIADA` · `EM ANDAMENTO` · `CONCLUÍDA` · `BLOQUEADA` · `AGUARDANDO PERMISSÃO`

Uma fase só é marcada `CONCLUÍDA` quando as duas verificações passam:
**V1 funciona?** e **V2 outra evidência independente mostra o mesmo?**

## Onde estamos — 10/09/2026

| Fase | | Estado |
|---|---|---|
| 1 | Auditoria, modelo de dados, esquema | CONCLUÍDA |
| 2 | Pipeline de carga e normalização | CONCLUÍDA |
| 3 | Regras de administração e separação | CONCLUÍDA |
| 4 | Motor de horários | CONCLUÍDA |
| 5 | Motor de conciliação + interações | CONCLUÍDA |
| 6 | Aplicação do farmacêutico | CONCLUÍDA |
| 7 | Machine Learning | CONCLUÍDA — a conclusão é uma **recusa** |
| 8 | Testes integrados + integração do modelo | CONCLUÍDA |
| 9 | **Validação do sistema inteiro** | **CONCLUÍDA — APTO PARA EMPACOTAMENTO** |
| 10 | Empacotamento `.exe` | **PRÓXIMA** |

Bateria completa: **972 conferências**, 24 arquivos de teste, exit 0. Banco com
44 tabelas, 15 views, 73 MB. Camada de ML: 2 modelos registrados, **0 ativos**.
Acervo: 689 arquivos, **0 modificados**.

**Apto para empacotamento não é validação clínica** — nenhum farmacêutico
avaliou nenhum achado deste sistema — **e não é "pronto para distribuir"**: ver
as duas pendências de engenharia em [EMPACOTAMENTO.md](EMPACOTAMENTO.md).

---

## FASE 1 — Auditoria e modelagem

**STATUS:** CONCLUÍDA (08–09/09/2026)

**IMPLEMENTADO:** auditoria de 689 arquivos; medição de lacunas; modelo de dados; `database/schema.sql`.

**TESTE 1:** `tests/teste_schema.py` — esquema criado, invariantes rejeitam o que devem rejeitar.
**TESTE 2:** medições sobre o acervo bruto (`auditoria/saida/*.json`) confirmam as premissas do modelo.

**RESULTADO:** 689 arquivos lidos, zero falhas. Documentos em `docs/`.

**PRÓXIMA:** Fase 2.

---

## FASE 2 — Pipeline de carga e normalização

**STATUS:** CONCLUÍDA (09/09/2026)

### Implementado

| Arquivo | O que faz |
|---|---|
| `database/schema.sql` | 40 tabelas, 6 views |
| `pipeline/normalizacao.py` | esqueleto fonético PT↔EN (cópia do acervo, procedência no cabeçalho) |
| `pipeline/_substancia_texto.py` | divisão do campo de substâncias da ANVISA |
| `pipeline/traducao_atc.py` | tradução de classes ATC por molde, tudo-ou-nada |
| `pipeline/_comum.py` | leitura do acervo, carga, evidência |
| `pipeline/10_fontes.py` | 19 fontes catalogadas |
| `pipeline/20_substancias.py` | ANVISA + DCB → substâncias |
| `pipeline/30_produtos.py` | CMED → produtos, apresentações, EAN, tarja |
| `pipeline/40_atc.py` | WHO ATC → classes e vínculo |
| `pipeline/90_validacao.py` | validação estrutural, sai 1 se violar garantia |
| `pipeline/executar_tudo.py` | roda tudo na ordem + verificação independente |

### Carregado

| Tabela | Linhas |
|---|---:|
| substância | 2.094 |
| sinônimo | 1.207 |
| identificador externo | 5.110 |
| resolução ambígua (para curadoria) | 32 |
| produto | 8.935 |
| apresentação | 25.702 |
| código de barras | 26.889 |
| apresentação × substância | 33.129 |
| classe ATC | 6.996 |
| evidência | 39.641 |
| fonte · carga | 19 · 4 |

Tempo total do pipeline: **9 segundos**.

### Cobertura — o que o sistema sabe e o que não sabe

| | |
|---|---:|
| substâncias com número DCB | 83,9% |
| substâncias ligadas a alguma apresentação | 81,6% |
| substâncias com CAS | 71,9% |
| substâncias com canal de dispensação (tarja) | 69,2% |
| substâncias com código ATC | 55,1% ¹ |
| classes ATC com nome em português | 24,5% (níveis 1 e 2: **100%**) |

¹ Corrigido para **55,3% (1.159)** em 10/09/2026: `40_atc.py` rodava antes
de os sinônimos INN existirem e perdia 6 vínculos. Ver **D-048** e o passo
`pipeline/68_vincular_atc_pendente.py`.

### VERIFICAÇÃO 1 — funcional

`pipeline/90_validacao.py`: integridade referencial, `integrity_check`, 6 invariantes clínicas, 4 de rastreabilidade, 6 de qualidade. **Todas OK, exit 0.**

`tests/teste_schema.py`: 40 tabelas, 6 views, 8 invariantes originais + 9 problemas da revisão. **Todas passam.**

### VERIFICAÇÃO 2 — independente

Não repete o pipeline; procura o erro por outro caminho.

| Mecanismo | Resultado |
|---|---|
| Recontagem da CMED com código próprio | apresentações 25.702 = 25.702 GGREM · produtos 8.935 = 8.935 · EAN 26.889 = 26.889 |
| Comparação com o banco do sistema anterior (outro código, mesma fonte) | substâncias: 2.094 vs 2.097, **99,1% dos esqueletos coincidem**; EAN: 99,8% dos do anterior presentes |
| Casos conhecidos de balcão | 15/15 substâncias presentes |
| **Tarja de fármacos conhecidos** | dipirona=MIP · clonazepam=preta · **tramadol=vermelha com retenção** · amoxicilina=vermelha c/ retenção · paracetamol=MIP |
| Leitura por código de barras | EAN → produto + apresentação corretos |
| Normalizador | 33 casos fixados, incluindo simetria PT/EN e não colisão entre moléculas distintas |

A tarja é a verificação mais significativa: o sistema anterior mapeou o código numérico da ANVISA ao contrário e chegou a afirmar que **tramadol era venda livre**. Lendo o rótulo por extenso da CMED, os cinco casos batem.

### PROBLEMAS ENCONTRADOS E CORRIGIDOS

Todos achados pela verificação independente, nenhum pelos testes que já passavam.

| # | Problema | Correção |
|---|---|---|
| 1 | `UNIQUE(par, origem)` faria a 2ª fonte do mesmo par ser rejeitada em silêncio — conflito de gravidade ficaria indetectável | unicidade por `(par, fonte_id)`; view `vw_conflito_gravidade` |
| 2 | Sem registro de lote: não se sabia quando/de qual arquivo a linha entrou | tabela `carga` + `carga_id` na evidência |
| 3 | `CHECK` de hora aceitava `29:59` | `[0-1][0-9]` ou `2[0-3]` |
| 4 | Sem tabela de identificadores externos (dedup nível 1 e 2 sem base) | `substancia_identificador` |
| 5 | Ambiguidade não tinha onde ser marcada | `status_resolucao` + `resolucao_ambigua` (32 registradas) |
| 6 | EAN usado como identidade — mas **não é único** (183 repetem) | `codigo_ggrem` como chave natural; `apresentacao_ean` em tabela própria |
| 7 | `classe_atc` referenciada antes de existir | reordenada |
| 8 | 5 colunas de junção sem índice | índices criados |
| 9 | Regras de administração com a mesma falha do nº 1 | `fonte_id` obrigatório |
| 10 | **CAS recebia `[Ref. 8]`** — marcador de rodapé da DCB gravado como identificador químico | validação de formato; 252 viraram NULL |
| 11 | Um produto por apresentação (25.701/25.702): registro da CMED inclui sufixo de apresentação | chave = 9 primeiros dígitos → 8.935 produtos |
| 12 | **86 apresentações com 2 concentrações** (`25 MG/0,5ML + 5 MG/0,5ML`) recebiam só a primeira | detecção de 2ª concentração → NULL |
| 13 | `sulfato de morfina pentaidratado` não casava com morfina | hidratos superiores na tabela de sais |
| 14 | `maleato ácido de timolol` → esqueleto `akid timolol` | `ácido` após sal removido também sai |
| 15 | Fragmentos `subunitária)` no vínculo CMED | divisão com consciência de parênteses |

Dois "problemas" eram **falso positivo do teste**, não do dado, e o teste foi corrigido:
- nomes botânicos legitimamente têm parênteses (`Ananas comosus (L.) Merr.`);
- `+ SERINGA` não é segunda concentração.

### LIMITAÇÕES DECLARADAS

- **75,5% das classes ATC continuam em inglês** (níveis 3–5). Ficam marcadas como não traduzidas; a regra tudo-ou-nada impede meia tradução. Níveis 1 e 2 — os que aparecem no relatório — estão 100%.
- **118 strings de substância da CMED sem correspondência** (0,7% das apresentações): vacinas, biológicos e um erro de grafia da própria fonte (`orlipastat`).
- **32 substâncias marcadas `AMBIGUA`**, aguardando curadoria. Não foram fundidas.
- **Diferença de 3 substâncias** para o sistema anterior (2.094 vs 2.097): fragmentos de nome de vacina em ambos os lados, não substâncias reais.

**PRÓXIMA FASE:** 3 — regras de administração (jejum, com alimento, separação de cátions), a partir do DrugBank food-interactions e das bulas ANVISA.

---

## FASE 3 — Regras de administração

**STATUS:** CONCLUÍDA (09/09/2026)

### LEGENDA DE TERMOS

**Regra de administração** — orientação de *como* tomar o medicamento (em jejum, com alimento, com água), distinta de *quanto* e *quando*, que é a posologia.

**Regra de separação** — orientação de manter dois itens afastados no tempo. Não é "não pode tomar os dois": é "não pode tomar os dois **juntos**".

**Quelação** — reação em que um mineral (cálcio, ferro, magnésio, zinco, alumínio) se liga ao medicamento no intestino formando um composto que não é absorvido. O medicamento não faz efeito não porque interage no corpo, mas porque nem entra.

**Cátion multivalente** — íon de carga 2+ ou 3+ (Ca²⁺, Fe²⁺, Mg²⁺, Al³⁺). São os que fazem quelação; por isso antiácido, suplemento de cálcio e leite aparecem juntos nas mesmas orientações.

**CYP3A4** — enzima do fígado e do intestino que metaboliza grande parte dos medicamentos. Quando algo a **inibe** (toranja), o medicamento é destruído mais devagar e sua concentração sobe. Quando algo a **induz** (erva-de-são-joão), acontece o contrário e o medicamento perde efeito.

**MIP** — Medicamento Isento de Prescrição (venda livre, sem tarja).

**DrugBank** — base farmacológica internacional. O campo `food-interactions` dela não traz só alimentos: traz a orientação de administração em texto corrido, em inglês.

### Implementado

| Arquivo | O que faz |
|---|---|
| `pipeline/_diretivas.py` | classifica a frase em inglês em tipo de regra; autoteste com 12 casos |
| `pipeline/50_regras_administracao.py` | DrugBank → regras, separações, itens e hábitos |
| `pipeline/55_regras_bula.py` | bulas ANVISA (2ª fonte, em português) |
| `pipeline/58_conflitos_administracao.py` | contradição entre fontes → `auditoria_conflito` |
| `tests/verificacao_50_regras.py` | verificação independente em 4 eixos |

### Carregado

| | |
|---|---:|
| regras de administração | **725** |
| — do DrugBank | 673 |
| — de bulas ANVISA | 52 |
| substâncias brasileiras com regra | **621** (29,7%) |
| regras de separação | **59** |
| — **com intervalo declarado pela fonte** | **49** |

> **Números corrigidos em 09/09/2026 (D-045).** Eram **71** e **61**, inflados
> por **12 cópias exatas**: `regra_separacao` era a única tabela de afirmação
> sem chave de unicidade, e cinco entradas do DrugBank (acetato, sulfato,
> gluconato, cloreto e brometo de zinco) caem na mesma substância brasileira,
> cada uma gravando as mesmas regras — `brometo de zinco` tinha 15 linhas para
> 3 regras. Nenhuma regra real foi perdida; as 4 verificações clínicas do eixo
> 2 continuam batendo (fenitoína 2 h · etambutol 4 h · sucralfato 1 h ·
> digoxina 2 h).
| — **sem intervalo** (declarado como desconhecido) | **10** |
| interações com item (alimento, planta, mineral) | 289 |
| interações com hábito (álcool, cafeína) | 196 |
| itens não medicamentosos, em português | 14 |
| conflitos registrados, nenhum resolvido | 4 |

Por tipo: indiferente ao alimento 332 · com alimento 164 · **jejum 61** · com água abundante 51 · horário fixo 49 · não partir/triturar 35 · antes da refeição 17 · após 15 · sublingual 1.

### O texto em português não é traduzido frase a frase

Cada tipo de regra tem uma orientação fixa, escrita e revisada uma vez em português. O inglês original fica guardado como `trecho` da evidência. Tradução automática de texto clínico é onde erro de tradução vira erro de conduta.

### VERIFICAÇÃO 1 — funcional

`pipeline/90_validacao.py` continua saindo 0. Autotestes de `_diretivas.py` (12 casos) e `traducao_atc.py` passam.

### VERIFICAÇÃO 2 — independente

| Eixo | Resultado |
|---|---|
| Recontagem do JSON com código próprio | todas as contagens do banco ≤ as do arquivo (só entram fármacos com produto ativo no Brasil) |
| **Casos clínicos conhecidos** | levotiroxina=jejum · captopril=jejum · carvedilol=com alimento · alendronato=antes da refeição + água |
| Separações plausíveis | fenitoína 2 h · etambutol 4 h · sucralfato 1 h · digoxina 2 h |
| Coerência | nenhuma fonte manda jejum e com-alimento ao mesmo tempo; toda regra tem evidência **com o trecho de origem** |
| Intervalo desconhecido | as 10 declaram a ausência; **nenhuma sugere número de horas** |

### PROBLEMAS ENCONTRADOS E CORRIGIDOS

| # | Problema | Como apareceu | Correção |
|---|---|---|---|
| 1 | Regra extraída por expressão regular chegaria à tela como se fosse revisada | revisão do próprio esquema | views ganharam `confianca_extracao`; o motor rebaixa o achado a POSSÍVEL |
| 2 | `diosmina` ficou com *antes da refeição* + *com alimento* + *indiferente* ao mesmo tempo | verificação de sobreposição entre fontes | extrator de bula passou a exigir exclusividade; contradição vai para auditoria e **nenhuma das regras é gravada** |
| 3 | **captopril sem regra nenhuma** | caso clínico conhecido | a fonte diz *"Take separate from meals... one hour prior to meals"*, não *"empty stomach"*. Padrões acrescentados e números por extenso convertidos |
| 4 | **alendronato sem regra** | caso clínico conhecido | `alendronic acid` (inglês, forma ácida) × `alendronato de sódio` (Brasil, sal). Criada a chave candidata `-ic acid` → `-ate` |
| 5 | *"Avoid multivalent ions... may interfere with the absorption"* não gerava separação | leitura do texto de alendronato | padrão acrescentado; +13 regras de separação |
| 6 | `hash_arquivo` quebrava quando a fonte é um diretório | execução do pipeline | passa a resumir a lista de arquivos |

Um "problema" era **falso positivo do teste**: eu exigia `JEJUM` para alendronato, mas a fonte escreve *"30-60 minutes before breakfast"*. Exigir do código algo que a fonte não diz seria forçar invenção — o teste passou a aceitar as duas formas.

### LIMITAÇÕES DECLARADAS

- **29,7% das substâncias têm regra de administração.** O resto não tem porque a fonte não cobre, não porque o código falhou.
- **Todas as 725 regras estão `PENDENTE` de revisão farmacêutica.** Foram extraídas por expressão regular e a view as marca `EXTRAIDA_AUTOMATICAMENTE`. Nenhuma se apresenta como revisada.
- **As duas fontes quase não se sobrepõem** (2 substâncias): as 150 bulas foram baixadas justamente para fármacos ausentes das bases internacionais. São complementares, não redundantes — e por isso a concordância entre fontes ainda não pôde ser usada como verificação.
- **Separação medicamento × medicamento continua sem intervalo.** Os 61 intervalos são de medicamento × item (antiácido, cálcio, leite). Confirma o que a Fase 1 mediu.

**PRÓXIMA FASE:** 4 — motor de horários.

---

## FASE 4 — Motor de horários e administração

**STATUS:** CONCLUÍDA (09/09/2026)

### LEGENDA DE TERMOS

**PRN** — *pro re nata*, "se necessário". Medicamento sem horário fixo, tomado quando a condição aparece (dor, febre). Tem posologia, mas não tem agenda.

**ATC** — Classificação Anatômica Terapêutica Química da OMS. Agrupa medicamentos por órgão-alvo, finalidade e química. `A02A` é o grupo dos antiácidos.

**Aritmética modular (a "volta do dia")** — 23:30 e 00:30 distam 60 minutos, não 1380. Subtração simples erra isso e o motor perderia conflitos entre a última tomada da noite e a primeira da manhã.

**Invariante** — afirmação que precisa valer sempre, independentemente do caso testado. Ex.: "todo horário citado num conflito existe na agenda".

**Teste de propriedade** — em vez de conferir um caso específico, gera muitos casos e verifica que uma regra geral nunca é violada.

### O que foi construído

| Arquivo | O que é |
|---|---|
| `rules/motor_horarios.py` | o motor: 1 função pública, `montar_agenda(con, atendimento_id)` |
| `tests/casos_clinicos.py` | fixtures de paciente sintético sobre farmacologia real |
| `tests/teste_motor_horarios.py` | 16 casos clínicos com resultado esperado |
| `tests/verificacao_motor_horarios.py` | verificação independente em 4 eixos |
| `tests/teste_regressao.py` | 28 travas contra defeitos já corrigidos |
| `database/schema.sql` | `rotina_paciente` substitui `rotina_refeicao`; view `vw_refeicao` |

**Tabela nova:** `rotina_paciente` — acordar, dormir, cinco refeições, trabalho, escola, deslocamento. Sem ela o motor não consegue dizer se "jejum às 06:30" é viável para quem acorda às 08:00.

### Contrato para a Fase 6 (a aplicação)

```
montar_agenda(con, atendimento_id) -> Agenda
    .eventos       list[EventoAdministracao]   ordenados por horário
    .conflitos     list[Conflito]
    .nao_avaliado  list[NaoAvaliado]
    .rotina        dict  evento -> 'HH:MM'
```

**Uma função pública, três listas.** A interface não reimplementa regra nenhuma: lê essas listas e desenha. Cada `EventoAdministracao` carrega os 22 campos que a tela precisa — medicamento, princípio ativo, dose, unidade, horário, via, datas, frequência, intervalo, relação com alimento, orientação em português, separações aplicáveis, fonte, confiança da extração e status da informação.

### Conflitos que o motor detecta

| Tipo | Classificação |
|---|---|
| `JEJUM_PROXIMO_DE_REFEICAO` | confirmado se a fonte deu o intervalo; possível se não |
| `ALIMENTO_EXIGIDO_SEM_REFEICAO_PROXIMA` | possível |
| `SEPARACAO_NAO_RESPEITADA` | confirmado |
| `SEPARACAO_COM_INTERVALO_DESCONHECIDO` | **regra desconhecida** |
| `INTERVALO_ENTRE_DOSES_MENOR_QUE_O_DECLARADO` | confirmado |
| `FREQUENCIA_INCOMPATIVEL_COM_HORARIOS` | confirmado ou informação insuficiente |
| `DUPLICIDADE_DA_MESMA_SUBSTANCIA` | confirmado |
| `HORARIO_FORA_DA_ROTINA` | possível |
| `REGRAS_DE_ALIMENTACAO_CONFLITANTES` | regra desconhecida |

O motor **nunca reescreve horário do paciente**. Quando não há horário e há frequência, propõe — marcado `SUGERIDO_PELO_SISTEMA`.

### Auditoria de qualidade

| | |
|---|---:|
| regras de administração usadas | 723 |
| — indiferente ao alimento · com alimento · jejum | 331 · 163 · 61 |
| — água · horário fixo · não partir · antes · após · sublingual | 51 · 49 · 35 · 17 · 15 · 1 |
| substâncias cobertas | 620 de 2.094 (**29,6%**) |
| regras de separação | 59 (41 item, 18 classe ATC) |
| — **com intervalo declarado** | 61 |
| — **intervalo desconhecido** | 10 |
| regras **extraídas automaticamente** | **723 (100%)** |
| regras **revisadas por farmacêutico** | **0** |
| conflitos em auditoria, nenhum resolvido | 4 |
| casos clínicos testados | 16 |
| verificações estruturais e independentes | 6 arquivos de teste |
| travas de regressão | 26 |
| defeitos encontrados nesta fase | 3 |
| falsos positivos de teste encontrados | 2 |

### VERIFICAÇÃO 1 — funcional

16 casos clínicos, todos passando: jejum longe e perto da refeição · com alimento longe e no almoço · separação com intervalo respeitado e violado · separação com intervalo desconhecido · antiácido por classe ATC · frequência incompatível · intervalo entre doses menor que o declarado · sem posologia · PRN · horário fora da rotina · não reconhecido · polimedicado · duplicidade · sem rotina informada.

### VERIFICAÇÃO 2 — independente

| Eixo | O que fez | Resultado |
|---|---|---|
| Implementação alternativa | reescreveu o cálculo de distância por varredura minuto a minuto, sem compartilhar código com o motor, e comparou em **21.115 pares** de horários | zero divergências |
| Invariantes | todo horário citado existe na agenda; toda classificação está no vocabulário; **nenhum intervalo aparece sem estar no banco** | todas OK |
| Consulta SQL independente | para cada conflito de separação, foi ao banco por SQL próprio conferir intervalo e fonte | conferem |
| Propriedade | 60 agendas aleatórias com substância sem regra, dentro da janela acordada | zero conflitos; e fora da janela o motor sempre acusa |

### DEFEITOS ENCONTRADOS E CORRIGIDOS

| # | Defeito | Como apareceu | Correção |
|---|---|---|---|
| 1 | **Separação só funcionava para substância × substância** — e o banco não tem nenhuma dessas. Item e classe ATC iam para "não avaliado" | consulta ao banco antes de escrever os casos | motor passou a resolver os três alvos: substância, classe ATC (outro medicamento do grupo) e item (suplemento que o paciente declarou) |
| 2 | `hash_arquivo` quebrava quando a fonte é um diretório | execução | passa a resumir a lista de arquivos |
| 3 | **`Fenofibrate` e `Fenofibric acid` caem na mesma substância brasileira** pela chave candidata que criei na Fase 3, e a mesma fonte passava a afirmar *com alimento* e *indiferente* para fenofibrato | teste de regressão | contradição intra-fonte é removida e registrada em auditoria (D-023) |

Dois **falsos positivos de teste**, corrigidos no teste e não no código:
- o fixture escolheu uma regra de classe ATC e a testou como item — o motor estava certo;
- o teste de propriedade sorteava horários a partir das 06:00, quando o paciente acorda 06:30: `HORARIO_FORA_DA_ROTINA` era acerto, não ruído.

### LIMITAÇÕES DECLARADAS

- **Cobertura de 29,6%.** O motor monta agenda para qualquer medicamento, mas só verifica relação com alimento nos 620 com regra.
- **Nenhuma das 723 regras foi revisada por farmacêutico.** Todas aparecem como `EXTRAIDA_AUTOMATICAMENTE`.
- **Zero regras de separação medicamento × medicamento diretas.** As 18 por classe ATC cobrem antiácidos; o resto do universo fármaco-fármaco continua sem intervalo publicado em nenhuma fonte do acervo.
- **`JANELA_REFEICAO_MIN = 30`** é o único número temporal não vindo de fonte. **Não é intervalo terapêutico:** é a janela de leitura para decidir se um horário está perto ou longe de uma refeição quando a fonte não declarou nada. Está declarada como constante nomeada no topo do motor, e quando ela é usada o conflito sai como `POSSIVEL`, nunca `CONFIRMADO`.
- **A agenda não é persistida.** É recalculada por leitura, como deve ser: se o dado do paciente muda, a agenda muda junto.

**PRÓXIMA FASE:** 5 — motor de conciliação. O motor de horários já entrega dois dos doze módulos (regra de administração e conflito de horário); a Fase 5 acrescenta os outros dez e unifica a saída em `achado` com prioridade.

---

## FASE 5 — Motor de conciliação

**STATUS:** CONCLUÍDA (09/09/2026)

### LEGENDA DE TERMOS

**Achado** — a unidade de saída do sistema. Um problema ou informação clinicamente relevante que o motor detectou, com tudo o que sustenta: fonte, trecho, mecanismo, contexto do paciente e o motivo da prioridade. É a camada entre os motores e a tela.

**Conciliação medicamentosa** — comparar o que foi **prescrito** com o que o paciente **realmente usa**, e resolver as diferenças. Não é o mesmo que "checar interações": é o ato de descobrir que a receita diz uma coisa e a vida diz outra.

**Divergência** — uma diferença entre as duas listas. **Não é sinônimo de erro**: pode ser ajuste posterior, decisão de outro prescritor ou esquecimento no relato.

**Intencionalidade** — se uma divergência foi deliberada ou não. É julgamento clínico, assinado. O sistema nunca o faz.

**PK / farmacocinética** — o que o corpo faz com o medicamento (absorver, metabolizar, excretar). **PD / farmacodinâmica** — o que o medicamento faz no corpo.

**CYP** — família de enzimas do fígado e do intestino que metaboliza a maior parte dos medicamentos. Quem a **inibe** faz o outro fármaco subir de concentração; quem a **induz** faz cair.

**Substrato-índice / inibidor-índice** — fármacos que a FDA escolheu como referência para medir força de interação enzimática. São poucos e bem estudados, exatamente por isso servem de régua.

**ATC 4º nível** — o subgrupo químico-terapêutico da classificação da OMS (5 caracteres, ex.: `A02BC`, inibidores da bomba de prótons). O 5º nível identifica a **substância**; o 4º agrupa substâncias de mesma finalidade.

**Deduplicação** — juntar num só alerta o mesmo problema descoberto por caminhos diferentes, **sem** descartar as evidências de nenhum deles.

**Teste de propriedade** — em vez de conferir um caso, gera muitos e verifica que uma regra geral nunca é violada. Ex.: "acrescentar um medicamento nunca pode fazer um achado desaparecer".

**Monotonicidade** — a propriedade acima. Foi ela que encontrou o defeito mais sutil desta fase.

**USAN × DCB** — o nome adotado nos EUA e a Denominação Comum Brasileira. Divergem em alguns fármacos (`rifampin` × `rifampicina`), e o casamento fonético não resolve sozinho.

---

### 1. O que foi construído

| Arquivo | O que é |
|---|---|
| `pipeline/60_interacoes_substancia.py` | DDInter + `db_drug_interactions` → `interacao_substancia` |
| `pipeline/62_papel_farmacocinetico.py` | tabela de fármacos-índice da FDA → `papel_farmacocinetico` |
| `pipeline/64_contraindicacoes_bula.py` | seção CONTRAINDICAÇÕES das bulas → `doenca` + `interacao_doenca` |
| `pipeline/65_habitos_bula.py` | tabagismo a partir das bulas → `interacao_habito` |
| `pipeline/traducao_interacao.py` | tradução por molde, tudo-ou-nada (cópia do acervo, com procedência) |
| **`rules/motor_conciliacao.py`** | **o motor: uma função pública, `conciliar_atendimento`** |
| `rules/_prioridade.py` | tabela de prioridade com justificativa por peso + autoteste |
| `tests/casos_conciliacao.py` | fixtures que **procuram no banco** o insumo real de cada caso |
| `tests/teste_motor_conciliacao.py` | V1 — 28 casos clínicos + 7 casos difíceis |
| `tests/verificacao_motor_conciliacao.py` | V2 — 5 eixos independentes, 18 verificações |
| `tests/qualidade_fase5.py` | coorte de 20 pacientes sintéticos e o quadro de qualidade |
| `database/schema.sql` | `achado` reescrito · `achado_evidencia` · `conciliacao_par` · `lista` |

**Banco:** 43 tabelas (eram 41), 14 views (eram 8), 76 MB. Pipeline completo com as duas verificações: **30 segundos**.

### 2. O que entrou no banco

| Tabela | Linhas | Observação |
|---|---:|---|
| `interacao_substancia` | **112.520** | 94.770 pares distintos; **17.750** afirmados por duas fontes |
| — do DDInter | 58.323 | gradua gravidade, **não publica descrição** |
| — do `db_drug_interactions` | 54.197 | descreve o efeito, **não gradua** |
| `interacao_doenca` | **182** | 94 contraindicações · 88 precauções · 102 substâncias |
| `doenca` | 28 | condições realmente encontradas nas bulas |
| `papel_farmacocinetico` | **28** | 22 substâncias, 8 sistemas CYP, nenhum transportador |
| `interacao_habito` | 199 | álcool 169 · cafeína 27 · **tabagismo 3 (novo)** |
| `substancia_sinonimo` tipo INN | 983 | nomes em inglês que casaram 1:1 |
| `evidencia` | 153.653 | uma por (afirmação, fonte) |

**Gravidade:** MODERADA 28.027 · MAIOR 8.106 · MENOR 2.326 · **NAO_DETERMINADA 74.061 (65,8%)**.
**Tipo:** farmacocinética 27.874 · farmacodinâmica 24.387 · não determinado 60.259.
**Tradução:** 54.183 de 54.197 descrições (**99,97%**) viraram português por molde; as 14 restantes ficaram em inglês, intactas, de propósito.
**Cobertura do módulo 1:** 957 de 2.094 substâncias (**45,7%**).

### 3. O motor

```
conciliar_atendimento(con, atendimento_id, persistir=False) -> ResultadoConciliacao
    .resumo              dict com as contagens estruturadas
    .achados             representantes, ordenados por prioridade
    .achados_agrupados   os absorvidos — preservados, nunca apagados
    .divergencias        .conciliados      .nao_conciliados
    .conflitos           .nao_avaliado     .limitacoes    .indicadores
    .agenda              a estrutura inteira da Fase 4
```

Uma função pública. **A Fase 6 lê estas listas e desenha; não reimplementa regra nenhuma.**

Doze módulos, todos alimentados por dados reais: fármaco × fármaco · fármaco × doença · alergia · alimento · planta · suplemento · hábito · CYP · duplicidade · conflito de horário · regra de administração · posologia — mais divergência de conciliação e informação insuficiente.

**O motor da Fase 4 é consumido, não reimplementado.** `montar_agenda` continua dona de toda regra temporal; a Fase 5 traduz os conflitos dela em achados. Uma exceção declarada: a duplicidade da Fase 4 **não** é importada, porque aquele motor não conhece listas de conciliação e marca duplicidade quando o mesmo fármaco está na prescrição **e** no relato — que é justamente um item **conciliado**. O módulo 8 refaz a verificação com consciência de lista.

#### 3.1 Os seis eixos do achado, e por que nenhum pode ser fundido

| Eixo | Responde |
|---|---|
| `gravidade_fonte` | o que a **fonte** diz sobre o dano possível |
| `confianca_sistema` | o quanto o **sistema** confia no que está afirmando |
| `prioridade` | em que ordem **mostrar** — combina os dois com o contexto |
| `natureza` | epistemologia da afirmação: documentada, possível, prevista, conflitante |
| `classificacao` | detecção **neste paciente**: confirmada, ou possível porque falta dado |
| `status_informacao` | procedência e revisão: documentado, extraído, revisado, não determinado, previsto |

Um achado pode ser potencialmente grave **e** pouco confiável. A especificação exige que isso apareça de forma independente, e aparece: são colunas separadas, com `CHECK` de esquema impedindo que previsão se disfarce de fato.

#### 3.2 Prioridade

Tabela explícita em `rules/_prioridade.py`, 33 linhas, **cada uma com o motivo escrito ao lado** — e esse texto vai para o achado, de modo que o farmacêutico lê o porquê, não só o rótulo. Três modificadores, e só três:

1. **anafilaxia declarada** força CRÍTICO (dado do paciente, não de fonte externa);
2. **informação insuficiente** limita a INFORMATIVO — a especificação proíbe transformar ausência de dado em alerta grave;
3. **confiança baixa** rebaixa um degrau, exceto na alergia, que não depende de fonte externa nenhuma.

**A idade ficou de fora de propósito.** Sem Beers ou STOPP/START carregados, o sistema não tem base para dizer que um fármaco é inadequado no idoso. A idade entra no contexto do achado, é exibida, e **não mexe na prioridade** — e o motor declara essa limitação quando o paciente tem 65 anos ou mais (D-027).

#### 3.3 Agrupamento sem perda

Achados com a mesma `grupo_chave` viram um só na lista principal. O representante **recebe as evidências dos demais** (papel `CORROBORA`, ou `DIVERGE` quando a gravidade declarada diverge). Os absorvidos continuam existindo, com `status='AGRUPADO'`, e voltam em `achados_agrupados`. Reduzir alerta nunca apaga registro — verificado por invariante: **zero evidências perdidas**.

#### 3.4 Conflito entre fontes

Quando duas fontes graduam o mesmo par de forma diferente, o motor **não escolhe**: marca `natureza='CONFLITANTE'`, `conflito_tipo='GRAVIDADE'`, põe as duas evidências como `DIVERGE`, escreve a discordância na explicação e **ordena pela mais grave** — a única escolha cujo risco não é assimétrico.

### 4. VERIFICAÇÃO 1 — funcional

**35 casos, 35 passando, 0 pulados.** Cobre a bateria da especificação e os sete casos difíceis:

interação · alergia exata · alergia por classe ATC · contraindicação · duplicidade de substância · duplicidade terapêutica · dose divergente · frequência e horário divergentes · conflito de horário · conflito com refeição · separação por classe ATC · informação insuficiente · duas fontes · alimento/planta declarado · item não declarado · hábito · CYP · PRN · sem cobertura · não reconhecido · gravidade ausente · polimedicado · **controle negativo** · persistência · explicação · sem prescrição · conciliado ≠ duplicidade · suspenso em uso.

Casos difíceis: **A** três problemas no mesmo fármaco preservados e ordenados · **B** fontes discordantes, nenhuma escolhida em silêncio · **C** extração automática continua identificada · **D** falta de dado não gera alerta · **E** dedup sem perda de evidência · **F** e **G** as duas direções da divergência de conciliação.

### 5. VERIFICAÇÃO 2 — independente

**18 verificações, 18 passando.** Cinco eixos, nenhum compartilhando lógica com o motor:

| Eixo | O que fez | Resultado |
|---|---|---|
| **Invariantes** | 28 afirmações que precisam valer sempre, sobre 4 cenários estruturalmente diferentes | 0 violações |
| **SQL independente** | para cada achado gravado, volta ao banco por consulta escrita à parte e confere que a afirmação existe com a gravidade declarada | 0 divergências |
| **Recontagem** | 12 rodadas: os pares esperados são calculados por SQL próprio, sem passar pelo motor | 18 pares, 0 divergências |
| **Propriedade** | determinismo · **monotonicidade** · nenhum módulo dispara sem causa · CRÍTICO só com alergia · todo medicamento deixa registro | 0 quebras |
| **Conferência manual** | 5 pares e 6 contraindicações conferidos item a item; 200 descrições traduzidas | 0 erros |

### 6. DEFEITOS ENCONTRADOS E CORRIGIDOS

| # | Defeito | Como apareceu | Correção |
|---|---|---|---|
| 1 | **Duplicidade terapêutica escrita no 5º nível ATC — regra estruturalmente morta.** O 5º nível *é* a substância: zero grupos com duas substâncias diferentes | consulta ao banco antes de escrever o teste | passou ao 4º nível: 248 grupos, e são os clinicamente certos (D-028) |
| 2 | **`db_drug_interactions` marcado como `REGEX` por causa de um campo acessório**, rebaixando a confiança de 54 mil interações | caso 18 da verificação funcional | `CARGA_DIRETA`: o par e a descrição são colunas lidas sem interpretação; só `tipo` é derivado, e a procedência fraca da fonte já está declarada em `fonte.confiabilidade` |
| 3 | **Chave de agrupamento presa à linha do atendimento** — o mesmo "como tomar" aparecia duas vezes para marca e genérico, e o agrupamento dependia da ordem de cadastro | **teste de propriedade (monotonicidade)** | chave por substância; invariante e trava de regressão impedem o retorno (D-032) |
| 4 | **`rifampin` (USAN) não casava com `rifampicina` (DCB)** e o maior indutor enzimático da tabela da FDA ficava de fora | conferência das 8 linhas não aproveitadas | equivalência de nomenclatura declarada no carregador; +5 linhas |
| 5 | Consulta com `NOT EXISTS (... WHERE i.substancia_a_id = id)` resolvia `id` na tabela **interna** e devolvia vazio | coorte de qualidade | ajudante que qualifica todas as colunas |

Três **falsos positivos de teste**, corrigidos no teste e não no código — o motor estava certo nos três:

- casos 07 e 13 exigiam prioridade MODERADO, mas **todas** as regras de separação e de hábito são extração automática não revisada, então a confiança é BAIXA e a exibição desce um degrau. Exigir o contrário seria pedir que o sistema ignorasse a própria limitação;
- o fixture de "par sem gravidade" filtrava a **linha** em vez do **par**, e devolvia pares em que uma fonte se calou e a outra graduou — o oposto do que o teste queria.

### 7. QUALIDADE DOS DADOS — coorte de 20 pacientes sintéticos

Farmacologia real, paciente sintético. 48 medicamentos, **68 achados apresentados** (3,4 por paciente), 1 agrupado, 188 declarações de não avaliado, 4 pares de conciliação.

| Por prioridade | | Por confiança do sistema | | Por status da informação | |
|---|---:|---|---:|---|---:|
| CRÍTICO | 1 | ALTA | 0 | EXTRAÍDO AUTOMATICAMENTE | 36 |
| ALTO | 7 | MÉDIA | 31 | DOCUMENTADO | 16 |
| MODERADO | 10 | BAIXA | 37 | NÃO DETERMINADO | 16 |
| BAIXO | 18 | | | REVISADO | **0** |
| INFORMATIVO | 32 | | | PREVISTO (ML) | **0** |

| Evidência | | Conciliação | |
|---|---:|---|---:|
| achados com evidência | 65 (95,6%) | divergências | 3 |
| com trecho literal da fonte | 31 (45,6%) | revisão necessária | 1 |
| com duas ou mais fontes | 0 | **intencionalidade decidida por script** | **0** |
| com conflito declarado | 0 | evidências perdidas no agrupamento | **0** |

**Nenhum achado tem confiança ALTA.** Não é defeito de cálculo: exige extração revisada **ou** carga direta de fonte de alta confiabilidade com evidência respaldada, e o acervo hoje não tem nenhuma das duas combinações em volume. É o retrato honesto do estado da base.

### 8. LIMITAÇÕES DECLARADAS

- **65,8% das linhas de interação não têm gravidade** porque a fonte não gradua. Não é bug e não tem processamento que recupere: das duas bases, só o DDInter gradua, e ele marca `Unknown` em boa parte.
- **Conflito de gravidade entre fontes é hoje estruturalmente indetectável** — `vw_conflito_gravidade` devolve zero, e não porque as fontes concordem: **só uma delas gradua**. A máquinaria de conflito existe, funciona e está testada, mas com cenário construído dentro da transação do teste, o que está declarado no próprio arquivo de teste.
- **Módulo fármaco × doença cobre 4,9% das substâncias** (102 de 2.094) e **100% dele está pendente de revisão**.
- **Módulo CYP cobre 1,1%** (22 substâncias), só CYP, **nenhum transportador**.
- **Nenhum achado revisado por farmacêutico.** Zero. Todo o sistema declara isso em cada achado.
- **Reação adversa não é avaliada** — VigiMed ainda não carregado (D-005).
- **Medicamento × exame laboratorial fora de escopo** — não existe fonte no acervo. Declarado em `nao_avaliado`, não silenciado.
- **Critério de inadequação em idoso não existe** — a idade é exibida e não altera prioridade (D-027).
- **O sistema guarda um código ATC por substância**; substâncias com mais de uma indicação podem escapar do agrupamento por classe.
- **A conciliação depende de o atendimento ter as duas listas.** Sem prescrição registrada não há divergência a apurar, e isso é declarado (D-031).

### 9. Como a Fase 6 vai consumir isto

A interface chama **uma** função e desenha o que voltar:

- **resumo da conciliação** → `res.resumo` (12 contagens prontas, também gravadas em `conciliacao`);
- **lista de medicamentos e agenda** → `res.agenda.eventos`, com os 22 campos da Fase 4;
- **alertas priorizados** → `res.achados`, já ordenados, cada um com título, mecanismo, efeito, conduta e explicação em português;
- **por que este alerta apareceu** → `achado.por_que_apareceu()`, a cadeia de contexto → detecção → fontes → prioridade;
- **evidências** → `achado.evidencias`, com fonte, documento, trecho literal e gravidade declarada por cada uma;
- **divergências** → `res.divergencias`, com os dois lados lado a lado e `intencionalidade` aguardando um profissional;
- **o que não foi avaliado** → `res.nao_avaliado` e `res.limitacoes`;
- **indicadores** → `res.indicadores`.

Para relatório e histórico, `persistir=True` grava tudo (`conciliacao`, `achado`, `achado_evidencia`, `conciliacao_par`, `nao_avaliado`), e a view `vw_achado_clinico` expõe **só os representantes** — a tabela guarda tudo, a tela mostra o que não é ruído.

### 10. Preparação para o Machine Learning (Fase 7)

Nada de ML foi implementado, por decisão. O que foi preparado:

- `achado.origem_achado` ∈ {`REGRA`, `MODELO`, `REGRA_E_MODELO`} — hoje 100% `REGRA`;
- `CHECK` de esquema: achado de regra **não pode** carregar probabilidade de modelo, e `natureza='PREVISTO'` **exige** `probabilidade_modelo`;
- `(natureza='PREVISTO') = (status_informacao='PREVISTO')` — as duas colunas andam juntas ou o banco recusa;
- `predicao.gravidade_sugerida` continua obrigatoriamente `NULL`.

Quando o modelo entrar, previsão e regra continuarão distinguíveis por consulta, não por convenção.

**PRÓXIMA FASE:** 6 — a aplicação do farmacêutico. Os três motores (busca, agenda, conciliação) estão prontos e testados, cada um com um ponto de entrada único.

---

## FASE 6 — Aplicação do farmacêutico

**STATUS:** CONCLUÍDA (09/09/2026)

Pela primeira vez o projeto tem um **Conciliador de Medicamentos funcional**:
é possível conduzir um atendimento inteiro pela aplicação e o resultado chega
corretamente aos motores construídos nas fases anteriores. Ainda sem ML.

### LEGENDA DE TERMOS

**API** — o conjunto de funções que uma camada oferece à camada de cima. Aqui: `montar_agenda`, `conciliar_atendimento`, `buscar_medicamento`.

**UI** — a interface, as telas.

**CRUD** — criar, ler, atualizar e apagar. O trabalho comum de qualquer cadastro.

**Rota** — um endereço da aplicação (`/a/20260909-001/medicamentos`) e o código que responde por ele.

**Template** — o arquivo que descreve como a página é desenhada. Aqui eles só exibem: nenhum calcula nada clínico.

**Teste de integração** — em vez de testar uma função isolada, exercita o caminho inteiro (formulário → rota → serviço → motor → banco → tela).

**Cliente de teste** — ferramenta que faz requisições HTTP reais contra a aplicação sem abrir o navegador. É como os testes desta fase rodam.

**Cascata (`ON DELETE CASCADE`)** — instrução no banco para que apagar uma linha apague junto as que dependem dela.

**Chave estável** — identificador que sobrevive a um recálculo. Oposto do `id` de uma linha que é regravada a cada análise.

**Flash** — mensagem curta que a aplicação mostra depois de uma ação ("Posologia salva").

---

### 1. Análise arquitetural (feita antes de escrever qualquer arquivo)

Registrada em [APLICACAO.md](APLICACAO.md).

| | |
|---|---|
| **Reutilizado sem tocar** | os dois motores e seus contratos · `rules/_prioridade.py` (só leitura) · `pipeline/_comum.conectar` · `pipeline/normalizacao.skeleton` · o esquema e as 14 views |
| **O que faltava** | `docs/ARQUITETURA.md` §7.3 previa **três** serviços; `buscar_medicamento` **não existia**. Sem ele a interface teria de montar SQL nas telas — exatamente o que a especificação proíbe |
| **Criado** | `app/busca.py` · `app/servicos.py` · `app/relatorio.py` · `app/rotulos.py` · `app/web.py` · 8 templates · `app/static/estilo.css` |
| **Adaptado** | `database/schema.sql` (1 tabela nova, 1 correção de cascata) · `pipeline/executar_tudo.py` · `tests/teste_regressao.py` |
| **Contratos mantidos** | nenhuma assinatura de motor mudou |

### 2. As quatro camadas

```
INTERFACE   app/web.py + templates       rotas, formulários, render
    ↓
SERVIÇOS    app/servicos.py              escreve o atendimento, orquestra
            app/busca.py                 busca tolerante em 4 passes
            app/relatorio.py             monta o relatório
            app/rotulos.py               vocabulário do banco → português
    ↓
MOTORES     rules/motor_horarios.py      agenda e conflitos de horário
            rules/motor_conciliacao.py   12 módulos, achados, prioridade
    ↓
BANCO       database/conciliador.db      44 tabelas, 14 views
```

**`app/web.py` não tem uma linha de SQL** — e isso é verificado lendo o
código-fonte, não por disciplina (D-036).

### 3. O que a aplicação faz

Sete etapas na ordem da anamnese de balcão, com ida e volta livre entre elas.

| Etapa | O que coleta |
|---|---|
| **1. Paciente** | nome, nascimento, sexo, peso, altura, contato, observação, responsável |
| **2. Anamnese** | condições clínicas (lista por grupo), alergias (busca com autocompletar), 8 hábitos com situação, quantidade e frequência |
| **3. Medicamentos** | busca por princípio ativo, marca ou **código de barras**; lista (prescrita / relatada / em uso / anterior / histórico) e origem do uso |
| **3b. Posologia** | dose, unidade, frequência, intervalo, via, duração, datas, horários, contínuo, se necessário, condição de uso, texto da receita |
| **4. Rotina** | acordar, dormir, cinco refeições, trabalho, escola |
| **5. Alimentos, chás e suplementos** | três seções **separadas**, cada uma com o seu catálogo |
| **6. Conciliação** | as listas lado a lado, o pareamento, e o registro da avaliação de cada divergência |
| **7. Resultados** | achados por prioridade, seis filtros, o que não foi avaliado, limitações |
| **Achado** | os seis eixos, a cadeia de evidência, as fontes com trecho literal, revisão profissional |
| **Relatório** | documento do atendimento, pronto para imprimir, e versão em texto puro |

**A busca é o serviço que faltava.** Quatro passes, do determinístico ao
tolerante: código de barras → chave fonética exata → prefixo (autocompletar)
→ nome comercial. Cada resultado diz **de onde veio** e **com que confiança**,
e a tela mostra isso. Associação em dose fixa vira uma linha por componente —
para o farmacêutico continua sendo um item, e a posologia informada uma vez
vale para o grupo.

### 4. O que a aplicação deliberadamente NÃO faz

- não altera prescrição, não suspende, não substitui, não muda dose nem horário;
- não decide intencionalidade de divergência sem nome de profissional (D-034);
- não preenche dado ausente com valor padrão — em branco é "não informado", e é gravado como tal;
- não tem score, porcentagem, "probabilidade de interação" nem botão de IA. `origem_achado` vale `REGRA` em 100% dos achados, e há trava de regressão para isso;
- não mostra erro técnico ao usuário: `ErroDeUso` vira mensagem escrita para ser lida, e falha técnica vai para `data/aplicacao.log`.

### 5. VERIFICAÇÃO 1 — funcional

`tests/teste_aplicacao.py` — **44 verificações, 44 passando.** Requisições HTTP
reais contra as rotas, com os formulários preenchidos como a tela preenche.

Fluxo completo (11 checagens) · interação maior · alergia crítica ·
contraindicação · duplicidade · divergência de dose com registro de
intencionalidade · conflito de horário · item declarado · paciente sem achados
· substância sem cobertura · item não reconhecido · informação incompleta ·
polimedicado · **6 tipos de entrada inválida** · edição e remoção sem duplicar
nem deixar órfão · persistência ao navegar · isolamento entre atendimentos ·
relatório sem análise · análise sem medicamento · concluir e reabrir · busca
por nome, por código de barras, sem resultado e por autocompletar.

### 6. VERIFICAÇÃO 2 — independente

`tests/verificacao_aplicacao.py` — **35 verificações, 35 passando.** Não repete
a V1: a V1 pergunta *"a tela funciona?"*; esta pergunta **"a tela está mesmo
consumindo os serviços, ou produzindo resultado próprio?"**

| Eixo | O que faz | Resultado |
|---|---|---|
| **1. Confronto** | o que a página mostra é comparado, achado a achado, com o que `conciliar_atendimento` devolve **chamado diretamente** — títulos, números do painel, gravidade, confiança, prioridade, status, divergências e o que não foi avaliado | 6 checagens, 0 divergências |
| **2. Inspeção do banco** | depois de cada ação da **interface**, SQL próprio confere coluna a coluna o que foi gravado | 11 checagens |
| **3. Arquitetura** | lê o **código-fonte**: interface sem SQL, templates sem cálculo de prioridade, serviços que chamam o motor, rótulos que não transformam | 6 checagens |
| **4. Persistência** | analisar duas vezes, conferir que nada duplica, que a anotação humana sobrevive, e que o `CHECK` segura o que tem de segurar | 6 checagens |
| **5. Integridade** | nada de órfão, nada de vazamento entre atendimentos, evidência nunca separada do achado | 6 checagens |

### 7. TESTE DE PONTA A PONTA

`tests/teste_ponta_a_ponta.py` — **14 etapas, 14 passando.** Um atendimento
completo, do zero ao relatório, **pela aplicação**.

O caso: idosa em uso de anticoagulante que se automedicou com
anti-inflamatório, relata dose diferente da prescrita para o anti-hipertensivo,
tem alergia registrada, usa uma planta com interação documentada, e traz um
item que o cadastro não reconhece — de propósito, para mostrar como o sistema
declara o que não avaliou.

Resultado real, gravado em [ATENDIMENTO_EXEMPLO.md](ATENDIMENTO_EXEMPLO.md):
6 medicamentos · **16 achados** (1 alto, 5 moderados, 3 baixos, 7 informativos)
· 5 divergências · 8 itens declarados como não avaliados · revisão profissional
necessária. A interação anticoagulante × anti-inflamatório foi detectada com
gravidade **Maior**, sustentada por **duas fontes**.

### 8. DEFEITOS ENCONTRADOS E CORRIGIDOS

| # | Defeito | Como apareceu | Correção |
|---|---|---|---|
| 1 | **Remover um medicamento depois de analisar era impossível.** A linha de pareamento ainda apontava para ele e o banco recusava a exclusão — o farmacêutico ficava preso ao primeiro resultado | **verificação independente**, eixo 5 | `ON DELETE CASCADE` nas duas referências de `conciliacao_par`, e a aplicação avisa que a análise gravada ficou desatualizada (D-035) |
| 2 | **Endereço inexistente virava erro interno 500.** O decorador que traduz erro técnico engolia também o `abort(404)` do próprio Flask | verificação funcional, caso 14.5 | `HTTPException` é repassada antes do tratamento genérico |
| 3 | O selo de "extraído automaticamente" na tela do achado usava texto próprio, diferente do rótulo canônico usado na lista | verificação independente, eixo 1.3 | os dois passaram a usar `rotulos.STATUS_INFORMACAO` |

Três **falsos positivos de teste**, corrigidos no teste e não no código:

- o cliente de teste do Flask não aceita lista de tuplas em `data` — 17 casos falhavam por isso, e nenhum era defeito da aplicação;
- o teste de vazamento entre atendimentos procurava o nome do medicamento no HTML e casava com uma **mensagem de flash pendente** de outro teste, que é comportamento normal do Flask; passou a usar cliente próprio e a comparar as listas de achados;
- o teste que proíbe SQL na interface procurava a palavra `INSERT` solta e casava com `sys.path.insert`.

### 9. REGRESSÃO

Todas as fases anteriores continuam passando. `tests/teste_regressao.py` foi de
34 para **38 travas**, com quatro da Fase 6: remover medicamento após analisar,
chave estável da anotação, intencionalidade sem assinatura e ML inexistente.

**Pipeline completo, do zero, com todas as verificações: 41 segundos.**

```
carga (11 etapas) → validação estrutural → esquema → normalizador →
substâncias → produtos → regras → motor de horários (V1+V2) →
tradução → prioridade → motor de conciliação (V1+V2) → busca →
aplicação (V1+V2) → ponta a ponta → regressão
```

### 10. COMO EXECUTAR

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
PYTHONIOENCODING=utf-8 "$PY" app/web.py
```

Abre em `http://127.0.0.1:5000` (respeita `PORT`). Offline: o banco é um
arquivo local e nada depende de rede.

### 11. LIMITAÇÕES DECLARADAS

- **Sem autenticação e sem perfis.** É uma aplicação local de balcão servida em `127.0.0.1`. Não há usuários nem senhas — e não deve haver antes de existir requisito real.
- **A revisão do achado é anotação, não assinatura digital.** Registra quem olhou, quando e o que escreveu. Não é prescrição nem documento assinado.
- **O relatório é HTML pronto para impressão e texto puro.** Não é PDF assinado.
- **A conciliação gravada é um retrato do momento** e fica desatualizada quando o atendimento muda. A tela sempre mostra o recálculo ao vivo; a aplicação avisa quando o retrato envelhece.
- **O resultado é recalculado a cada abertura de tela.** Correto por decisão (o dado do paciente mudou, o resultado muda junto), mas custa alguns décimos de segundo em atendimentos grandes.
- **A busca por nome comercial é `LIKE` simples**, sem tolerância a erro de digitação. Código de barras e princípio ativo têm o esqueleto fonético; a marca, não.
- **Um atendimento por vez.** Não há edição simultânea nem bloqueio de concorrência.
- **Todas as limitações de dados das Fases 2 a 5 continuam valendo** e aparecem na tela: 65,8% das interações sem gravidade graduada, módulo doença com 4,9% de cobertura, nenhum achado revisado por farmacêutico, reação adversa não avaliada, sem critério de inadequação em idoso.

### 12. Preparação para a Fase 7 — dataset e Machine Learning

Nada de ML foi implementado, por decisão. O que ficou pronto para receber:

- **`achado.origem_achado`** ∈ {`REGRA`, `MODELO`, `REGRA_E_MODELO`} — hoje 100% `REGRA`, com trava de regressão;
- **`CHECK` de esquema**: achado de regra não pode carregar probabilidade de modelo, e `natureza='PREVISTO'` exige `probabilidade_modelo`; as colunas `natureza` e `status_informacao` andam juntas ou o banco recusa;
- **a interface já sabe exibir previsão**: o template do achado tem o selo `PREVISTO`, visualmente distinto do documentado, e mostra a probabilidade quando existir. Hoje o ramo nunca é usado;
- **`predicao.gravidade_sugerida`** continua obrigatoriamente `NULL`;
- **o dataset da Fase 7 já está no banco**: 112.520 linhas de interação, 94.770 pares, 957 substâncias com ao menos uma interação — e, mais importante, **o rótulo humano começa a existir**. Cada revisão gravada em `anotacao_profissional` é um achado que um farmacêutico olhou e classificou, com nome e data. É exatamente o insumo do modelo M5 (relevância do alerta), que a `ARQUITETURA.md` §4 listava como *"não existe ainda"*.

**PRÓXIMA FASE:** 7 — dataset e Machine Learning, sobre M1 (existe interação?),
com split por fármaco e as dez perguntas da especificação respondidas antes de
qualquer treino.

> **Correção da Fase 7:** o parágrafo acima afirmava que o rótulo humano
> "começa a existir". Começou a existir a **estrutura**;
> `anotacao_profissional` está vazia. Ver a seção da Fase 7 abaixo.

---

## FASE 7 — Machine Learning

**STATUS:** CONCLUÍDA (09/09/2026)

Relatório científico completo: **[ML_FASE7.md](ML_FASE7.md)**.
Tabela de comparação: **[ML_COMPARACAO.md](ML_COMPARACAO.md)**.
Decisões: **D-037 a D-044**.

### LEGENDA DE TERMOS

**Alvo** (*target*) — o que o modelo tenta prever. **Atributo** (*feature*) — cada
informação que entra. **Split** — como os dados são separados em treino,
validação e teste. **Vazamento** (*leakage*) — quando a resposta entra
disfarçada de atributo. **Recall** — dos casos que existiam, quantos o modelo
achou. **Precisão** — dos avisos dados, quantos estavam certos. **ROC-AUC** —
0,5 é acaso, 1,0 é perfeito. **PR-AUC** — o piso não é 0,5, é a prevalência.
**Calibração** — se o modelo diz 80%, acontece mesmo em 80% das vezes.
**Aprendizado PU** — aprender só com positivos e não-rotulados, porque não
existe negativo confirmado.

### Uma correção ao que a Fase 6 escreveu aqui

O §12 acima afirmava que *"o rótulo humano começa a existir"*. **A estrutura
começou a existir; o rótulo não.** `anotacao_profissional` tem chave estável,
assinatura e `CHECK` de intencionalidade — e **zero linhas**. Nenhum
farmacêutico anotou nada. O modelo M5 (relevância do alerta) continua
impossível, e a Fase 7 mede quanto falta: **97 avaliações** para estimar uma
taxa com ±10 pontos; 400 a 1.000 para um modelo com concordância entre
avaliadores.

### Implementado

| Arquivo | O que faz |
|---|---|
| `ml/_comum.py` | semente, versão dos dados, par canônico, saída em JSON |
| `ml/_features.py` | **o espaço de atributos, definido aqui e em lugar nenhum mais**; autoteste de simetria |
| `ml/_modelos.py` | as 10 famílias comparadas, atrás da mesma interface |
| `ml/_avaliacao.py` | métricas e os dois pontos de operação |
| `ml/_artefato.py` | gravação em JSON quando a família permite; pickle declarado como amarra |
| `ml/01_auditoria_dataset.py` | volume, multiplicidade, simetria, grafo, cobertura, circularidade |
| `ml/02_auditoria_rotulos.py` | inventário dos 8 alvos possíveis, com veredito por número |
| `ml/10_dataset.py` | universo, 4 splits, subconjunto pareado por grau, controle negativo |
| `ml/20_treinar.py` | 40 execuções: 10 famílias × 6 configurações × 2 splits |
| `ml/25_robustez.py` | pareamento por grau, controle negativo, rótulo mais duro, precisão no topo |
| `ml/30_calibracao.py` | isotônica × Platt, curva de confiabilidade, ECE, Brier |
| `ml/40_explicabilidade.py` | importância por permutação, coeficientes, contribuição por previsão |
| `ml/45_significancia.py` | bootstrap pareado das diferenças entre famílias |
| `ml/50_comparacao.py` | tabela única e aplicação da regra de desempate |
| `ml/60_registrar_modelo.py` | registro em `modelo` com semente, versão dos dados e espaço |
| `ml/70_predizer.py` | **o contrato**: prever, contrato de achado, gravar predição |
| `ml/80_fila_curadoria.py` | as duas filas priorizadas para verificação humana |
| `ml/91_v1_pipeline.py` · `ml/92_v2_independente.py` | as duas verificações |
| `ml/executar_tudo.py` | roda a fase inteira na ordem, ~20 min |
| `tests/teste_ml.py` | 44 travas de regressão das garantias de ML |

### Medido

| | |
|---|---:|
| pares de treino (unidade = par canônico) | **94.770** de 112.520 linhas |
| universo (pares entre as 957 substâncias com interação) | 457.446 · prevalência 20,7% |
| substâncias com **grau zero** no grafo | **1.137 de 2.094 (54,3%)** |
| densidade do subgrafo conectado | 20,72% · 1 componente |
| atributos publicados | **130** (ATC 102 · REG 10 · ADM 11 · PK 7) |
| execuções comparadas | 40 |
| **AUC — protocolo da literatura (split por par)** | **0,9442** |
| **AUC — split por fármaco, dois lados inéditos** | **0,7392** [0,7270 ; 0,7504] |
| PR-AUC nesse regime (piso 0,204) | 0,4451 |
| ECE após calibração isotônica | 0,0223 → **0,0118** |
| precisão no topo 1% da lista (linha de base 0,204) | **0,802** |
| pares pontuados na fila de curadoria | 581.201 · 600 gravados |
| modelos registrados | 2 · **ativos: 0** |
| achados gerados por modelo | **0** |

### Alvos: dois treinados, seis recusados com número

| Alvo | Rótulos | Veredito |
|---|---:|---|
| A — existe interação documentada | 94.770 | **treinado** |
| C2 — tipo PK × PD | 52.261 | treinado, secundário, rótulo declarado como fraco |
| B — relevância do alerta | **0** | recusado — nenhuma anotação humana |
| C1 — gravidade | 38.459 de 94.770, **um único graduador** | recusado (D-015 mantida) |
| prioridade | — | recusado: é calculada pelas nossas regras |
| mecanismo · efeito clínico | texto livre | recusado: sem classes fechadas |
| necessidade de revisão | 0 variação | recusado |
| reação adversa | 0 | recusado: VigiMed não carregado |

### VERIFICAÇÃO 1 — funcional (`ml/91_v1_pipeline.py`, 37 conferências)

O `.npz` corresponde ao banco par por par; o split é completo, disjunto e sem
fármaco em dois grupos; **dois treinos com a mesma semente dão previsões
idênticas** (diferença 0,00e+00); a AUC gravada em `modelo` bate com o recálculo
até a sexta casa; o artefato recarregado do disco dá a mesma previsão; o
contrato recusa modelo experimental. **Todas passam.**

### VERIFICAÇÃO 2 — independente (`ml/92_v2_independente.py`, 32 conferências)

Seis caminhos que não repetem o pipeline:

| Caminho | Resultado |
|---|---|
| Recontagem por SQL próprio, sem ler o `.npz` | 957 / 94.770 / 457.446 — batem |
| Métricas reimplementadas em numpy puro | AUC 0,78787203 nos dois; Brier e ECE idênticos até a 8ª casa |
| Confronto com o banco do **sistema anterior**, por chave normalizada de nome | **98,9%** dos pares deste sistema estão no anterior |
| Caça ao vazamento por força bruta | zero pares de teste no treino, zero invertidos, zero fármacos de teste no grafo |
| Split conferido por combinatória | C(669,2)=223.446 e C(143,2)=10.153, exatos |
| **Artefato JSON recalculado à mão**, sem scikit-learn | mesma probabilidade, ordenação idêntica |

### PROBLEMA ENCONTRADO E CORRIGIDO

Um, e foi a **V2** que achou — como em todas as fases anteriores.

| # | Problema | Como apareceu | Correção |
|---|---|---|---|
| 1 | O recálculo à mão do artefato JSON divergia do scikit-learn em 1,21e-07, contra tolerância de 1e-9 | V2, eixo 6 | **Não era defeito do artefato:** a matriz de atributos é `float32` (475 MB em `float64`), e a diferença é exatamente o epsilon do float32 (1,192e-07). A tolerância estava errada. Corrigida para 1e-6, com o motivo escrito ao lado, e acrescentado o teste que importa: a **ordenação** das 300 previsões é idêntica, logo nenhuma decisão por limiar muda |

Dois defeitos menores foram achados pela execução real, não por teste: o
`artefato` gravado em `modelo` apontava para o `.pkl` em vez do manifesto
`.json` (o leitor tentava ler binário como texto), e o texto de previsão dizia
*"não há interação documentada"* mesmo para par que **está** documentado — o
erro que esta fase existe para impedir, com o sinal trocado. Os dois corrigidos.

### RESULTADO

**Escolhido:** `HistGradientBoostingClassifier`, 130 atributos, sem bloco de
grafo. Empata com a floresta aleatória dentro do intervalo de confiança
(diferença −0,0047, IC [−0,0117 ; +0,0022]) e ganha por prever mais rápido e
gerar artefato menor. Registrado junto: a regressão logística (AUC 0,7147,
artefato JSON de 10 KB) como referência interpretável.

**Não implantado como alerta.** No regime realista, precisão 0,392 e recall
0,556 — 44% das interações passariam batido e seis em cada dez avisos seriam
falsos, o que a especificação §19 proíbe. **Implantado como fila de curadoria:**
precisão 0,80 no topo 1% da lista contra 0,204 de linha de base.

Os dois modelos ficam `EXPERIMENTAL` e `ativo = 0`. O banco recusa ativar quem
não está homologado, e `contrato_achado()` levanta exceção. **Zero achados de
origem MODELO existem no banco.**

### LIMITAÇÕES DECLARADAS

As doze estão em [ML_FASE7.md §10](ML_FASE7.md). As três que mandam:

1. **O negativo é presumido.** O modelo estima probabilidade de o par estar
   **documentado**, não de ser perigoso.
2. **Metade da importância do modelo é propensão a documentação** — o atributo
   mais forte é "este fármaco tem regra de administração cadastrada", isto é,
   *quão estudado ele é*.
3. **Validação apenas computacional.** Nenhum farmacêutico avaliou nenhuma
   previsão. Nada aqui é validação clínica.

**PRÓXIMA FASE:** 8 — testes integrados.

---

## FASE 8 — Testes integrados e integração do modelo preditivo

**STATUS:** CONCLUÍDA (10/09/2026)

Decisões: **D-046 e D-047**. Documento da fase: **[INTEGRACAO_ML.md](INTEGRACAO_ML.md)**.

### LEGENDA DE TERMOS

**View** — consulta gravada no banco que se comporta como tabela; aqui, o filtro
que decide o que pode chegar ao farmacêutico. **Fail-closed** — quando falta
configuração, o sistema não emite nada em vez de emitir errado. **Homologar** —
declarar que um modelo pode ser usado; é ato humano registrado, não efeito
colateral. **Limiar** — probabilidade mínima para uma previsão virar linha na
tela. **Rastreabilidade** — poder ir do alerta na tela até o modelo, a versão, a
semente e os dados que o produziram.

### O que a fase entrega

A costura que a Fase 7 deixou pronta e **desligada** agora existe inteira, é
testada de ponta a ponta, e **continua desligada em produção**.

| Arquivo | O que faz |
|---|---|
| `database/schema.sql` | `modelo.limiar_alerta` · **view `vw_predicao_liberada`** · motivo `PAR_NAO_PONTUADO_PELO_MODELO` |
| `rules/motor_conciliacao.py` | **módulo 13** — interação prevista; lê a view, nunca importa `ml/` |
| `rules/_prioridade.py` | entrada `(FARMACO_FARMACO, PREVISTA)` — teto INFORMATIVO, com o porquê ao lado |
| `app/servicos.py` | `detalhe_previsao()` — segue `predicao.<id>` até modelo, versão, semente |
| `app/web.py` | separa `documentados` de `previstos` antes de renderizar |
| `app/templates/resultados.html` | bloco `id="bloco-previsto"`, tracejado, fora da escala de prioridade |
| `app/templates/achado.html` | painel de rastreabilidade + declaração de ausência de evidência |
| `app/relatorio.py` · `relatorio.html` | seção própria no relatório impresso e no texto puro |
| `app/rotulos.py` | `STATUS_PREDICAO` e o motivo novo, em pt-BR |
| `tests/teste_integracao_ml.py` | **V1**, 59 verificações |
| `tests/verificacao_integracao_ml.py` | **V2**, 42 verificações por caminho independente |

### As quatro travas, e todas estão no banco

`vw_predicao_liberada` só devolve linha quando:

1. o modelo está **ATIVO** e **HOMOLOGADO**;
2. o modelo **declarou `limiar_alerta`** — sem limiar, nada passa (fail-closed);
3. a probabilidade **calibrada** atinge esse limiar;
4. **o par não tem interação documentada.**

A quarta é a garantia estrutural de que previsão nunca substitui, contradiz nem
duplica evidência: onde há documento, o achado vem do documento e a previsão
não aparece. Previsão recusada por um farmacêutico também não volta.

**Hoje nenhum modelo está ativo, a view devolve zero linhas e o módulo 13 não
produz nada.** O comportamento em produção é idêntico ao de antes de existir
ML — e há trava de regressão para isso.

### O que uma previsão registra, quando registra

| Campo | Valor |
|---|---|
| `origem_achado` | `MODELO` |
| `natureza` · `status_informacao` | `PREVISTO` · `PREVISTO` |
| `probabilidade_modelo` | a **calibrada**, não a bruta |
| `origem_afirmacao` | `predicao.<id>` — daí se chega a modelo, versão, semente, versão dos dados, limiar, protocolo, explicação e data |
| `metodo_deteccao` | `MODELO_<nome>_<versão>` |
| `gravidade_fonte` · `nivel_evidencia` | **NULL** — o modelo não gradua e previsão não tem nível de evidência |
| `confianca_sistema` | `BAIXA`, sempre |
| `prioridade` | `INFORMATIVO`, teto por definição |
| `achado_evidencia` | **nenhuma linha** — previsão não tem evidência, e a ausência tem de aparecer |
| `grupo_chave` | `PREVISTA:a-b`, distinta de `PAR:a-b` |

### VERIFICAÇÃO 1 — funcional (`tests/teste_integracao_ml.py`, 59 conferências)

Homologa um modelo **numa cópia do banco**, monta um atendimento com um par
documentado e um par sem documento, e confere as quatro travas uma a uma; os
campos do achado; o que o banco aceita e recusa; a separação no resumo, na tela
e no relatório; e que **desativar o modelo devolve o sistema ao estado
anterior**. Todas passam.

### VERIFICAÇÃO 2 — independente (`tests/verificacao_integracao_ml.py`, 42 conferências)

Não repete o V1: lê **HTML e SQL cru**, sem usar as estruturas do motor, e
procura os oito modos de falha exigidos.

| Alvo | Como foi procurado | Resultado |
|---|---|---|
| previsão apresentada como fato | SQL direto na tabela `achado` | nenhuma |
| perda de rastreabilidade | seguir `predicao.<id>` até semente e versão dos dados | cadeia íntegra |
| vazamento entre pacientes | **dois atendimentos com pares disjuntos** | isolados |
| erro de probabilidade | regex no HTML × valor no banco | exibido = calibrado |
| paciente errado | conferência por atendimento | correto |
| duplicação de alerta | agrupamento por par e por chave | nenhuma |
| conflito regra × modelo | previsão de 0,999 **inserida de propósito** num par documentado | a view a esconde; o achado documentado permanece |
| regressão na aplicação | 6 rotas + ordem no relatório | todas 200 |

### PROBLEMAS ENCONTRADOS E CORRIGIDOS

Quatro, e **três eram defeito do teste, não do produto** — o que só se soube
depois de investigar cada um.

| # | Problema | Como apareceu | Diagnóstico e correção |
|---|---|---|---|
| 1 | `origem='USO_CONTINUO'` recusado ao adicionar medicamento | V1 não produzia achado nenhum | **Defeito do teste.** O valor não está no `CHECK` de `atendimento_medicamento.origem` — exatamente o alerta que o `CLAUDE.md` dá. Corrigido para `PRESCRITO` |
| 2 | `PAR_NAO_PONTUADO_PELO_MODELO` recusado ao gravar | V1, ao persistir | **Defeito do produto.** Motivo novo não estava no `CHECK` de `nao_avaliado.motivo`. Acrescentado ao esquema e ao rótulo em pt-BR |
| 3 | "a tela não mostra mais o bloco previsto" falhava com o modelo desligado | V1 | **Defeito do teste.** Procurava a string `PREVISTO POR MODELO`, que casa com o **comentário HTML** da seção, renderizado mesmo com o bloco vazio. Trocado por `id="bloco-previsto"`, que só existe dentro do bloco |
| 4 | "paciente 2 não recebe o par do outro" falhava | V2 | **Defeito do fixture.** `LIMIT 2` devolvia dois pares que **compartilhavam substância**, então a sobreposição era construção do teste, não vazamento. Passou a escolher pares disjuntos |

O de nº 2 é o único que teria chegado ao usuário. Os outros três são o caso
que a disciplina de dupla verificação prevê: **primeiro descobrir se o defeito
é do código ou do teste** — e aqui foi do teste três vezes em quatro.

### REGRESSÃO

Bateria completa (`pipeline/executar_tudo.py`): **exit 0, 445 verificações OK**.
Rodada **sem `--recriar`**, o que só é possível desde D-045 — e por isso os
2 modelos e as 600 previsões sobreviveram à revalidação.

`pipeline/90_validacao.py` ganhou **8 checagens** da integração;
`tests/teste_ml.py` foi de 44 para **61** travas, e `teste_regressao.py` de 46 para **49**.

| | |
|---|---:|
| tabelas · views | 44 · **15** |
| modelos registrados · **ativos** | 2 · **0** |
| previsões gravadas (fila de curadoria) | 600 |
| **achados de origem MODELO em produção** | **0** |

### LIMITAÇÕES DECLARADAS

- **O caminho está pronto e desligado.** Nenhum modelo está homologado, e a
  decisão da Fase 7 (D-041) não mudou: no regime realista o modelo tem recall
  0,53 e precisão 0,40, o que é fadiga de alerta, não segurança.
- **O motor lê previsões pré-calculadas.** Ele não roda modelo — por desenho,
  para não levar scikit-learn ao caminho determinístico nem ao `.exe`. Par não
  pontuado é **declarado** em `nao_avaliado`, nunca silenciado.
- **Homologar continua sendo ato humano.** O banco recusa `ativo=1` para quem
  não está `HOMOLOGADO`, e recusa dois ativos para o mesmo problema.
- **Nada disto é validação clínica.** O projeto tem um modelo experimental de
  previsão de existência de interação, medido computacionalmente. Nenhum
  farmacêutico avaliou nenhuma previsão.

**PRÓXIMA FASE:** 9 — validação do sistema inteiro.

---

## FASE 9 — Validação do sistema inteiro

**STATUS:** CONCLUÍDA (10/09/2026) · **APTO PARA EMPACOTAMENTO**

Decisões: **D-049 e D-050**. Documento da fase:
**[FASE9_VALIDACAO.md](FASE9_VALIDACAO.md)**. Inventário da Fase 10:
**[EMPACOTAMENTO.md](EMPACOTAMENTO.md)**.

### LEGENDA DE TERMOS

**E2E (ponta a ponta)** — teste que percorre o sistema todo, da primeira tela ao
relatório, sem atalho por dentro. **Convergir** — o pipeline chegar ao resultado
final já na primeira passada. **Saturar** — a calibração devolver exatamente 1,0
por a faixa inteira da validação ter o mesmo desfecho. **Órfão** — linha que
sobrou apontando para outra que já não existe. **Falso positivo** — o teste
acusa, e o defeito é do teste.

### A pergunta que esta fase faz

As fases 1 a 8 validaram um módulo de cada vez, cada uma com duas verificações,
e todas passaram. Esta fase pergunta outra coisa: **o produto inteiro funciona
quando tudo roda junto?** Os quatro defeitos reais encontrados são todos de
costura — nenhum deles apareceria rodando os testes anteriores de novo.

### O que foi construído

| Arquivo | O que faz | Conferências |
|---|---|---:|
| `tests/fase9_cenarios.py` | dez cenários clínicos, cada um do início ao relatório | **90** |
| `tests/fase9_v1_sistema.py` | **V1** — onze eixos de auditoria funcional | **166** |
| `tests/fase9_v2_independente.py` | **V2** — oito caminhos independentes | **64** |
| `tests/fase9_convergencia.py` | do zero → 2ª → 3ª passada, e reprodução | 44 |
| `auditoria/05_integridade_acervo.py` | 689 arquivos do acervo, recalculados | 6 |
| `docs/EMPACOTAMENTO.md` | inventário do que a Fase 10 vai precisar | — |

**Bateria completa: 972 conferências, exit 0, 0 falhas.**
`teste_regressao.py`: 49 → **61**.

### Os dez cenários

Sem problemas (controle negativo) · interação documentada · previsão do modelo ·
documentada **e** prevista no mesmo par · alergia · contraindicação por doença ·
duplicidade terapêutica · conflito de horário · informação insuficiente ·
divergência de conciliação. Farmacologia real do banco, paciente sintético,
identificadores fixados com o motivo escrito ao lado.

### DEFEITOS ENCONTRADOS E CORRIGIDOS — quatro reais

1. **A mensagem de um paciente aparecia na tela de outro.** A fila do Flask é da
   sessão, não do atendimento: *"Posologia de Gliclazida 30 mg salva"* saía no
   alto da tela de quem toma varfarina. Nenhum dado clínico vazou — achado,
   resumo, relatório e banco continuaram corretos. Vazou uma frase, num sistema
   que existe para não confundir paciente. **D-049.**
2. **"100% de probabilidade" para uma previsão sem evidência.** A calibração
   isotônica satura em 1,0; escrito como "100%", três parágrafos abaixo de *"não
   há evidência documental"*, prometia certeza. Agora sai **"acima de 99%"**, e
   o valor exato fica no painel de rastreabilidade com a explicação da
   saturação. **D-050.** Nenhum teste tinha pegado: todos conferiam estrutura,
   nenhum lia a frase.
3. **Código interno chegando cru à tela** — o chip mostrava `interacao
   prevista`. Corrigido com `rotulos.SUBTIPO`.
4. **Cinco pacientes órfãos no banco de produção**, resíduo de
   `verificacao_aplicacao.py`. Removidos; a limpeza agora guarda o id do
   paciente na criação, e a V1 confere que produção termina limpa.

Mais uma asserção fraca herdada da Fase 8 (`"Evid" in html and "nenhuma" in
html`, que casava com quase qualquer página) e **treze falsos positivos meus**,
todos classificados em `FASE9_VALIDACAO.md` §6.

### CONVERGÊNCIA E REPRODUTIBILIDADE

Do zero → 2ª → 3ª passada: **0 diferenças** em qualquer tabela, e a mesma
impressão digital `9e9c85ee3ffea5e0` nas três. Reconstruir do zero reproduz o
banco anterior **tabela por tabela** — e é a mesma impressão digital com que os
dois modelos foram treinados.

### ACERVO ORIGINAL

**689 arquivos, 0 modificados**, 2.268.000.886 bytes — recalculado, não
herdado. Gravado também um manifesto novo com sha256 do conteúdo **inteiro**
(o inventário de 09/09 só cobria os primeiros 8 MB de cada arquivo).

### DESEMPENHO

Análise de 20 medicamentos com 110 achados: **0,045 s**. Tela de resultados:
0,037 s. Relatório: 0,032 s. Duas ordens de grandeza de folga sobre o orçamento
declarado. **Nada foi otimizado** — não havia gargalo.

### LIMITAÇÕES DECLARADAS

- **Apto para empacotar não é validação clínica.** Zero achados revisados por
  farmacêutico; zero linhas em `anotacao_profissional`.
- **Apto para empacotar não é apto para distribuir.** Duas pendências de
  engenharia em `EMPACOTAMENTO.md`: o banco precisa ser gravável (não pode
  viver em `Program Files`), e conhecimento e atendimento estão no **mesmo
  arquivo** — atualizar o primeiro sobrescreveria o segundo.
- **As lacunas de dados continuam as mesmas.** 65,8% das interações sem
  gravidade graduada; fármaco × doença cobrindo 4,9% das substâncias; nenhuma
  das 723 regras revisada.
- **A conferência de conteúdo inteiro do acervo só vale a partir da próxima
  execução** — esta gravou a linha de base, e o script diz isso em vez de
  contar como prova.
