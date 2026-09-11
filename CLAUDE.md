# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este projeto

**Conciliador de Medicamentos** — TCC de Farmácia (Centro Universitário Fametro).
Sistema de conciliação farmacêutica para uso no balcão, durante o atendimento.

O produto final é a **aplicação usada pelo farmacêutico**. Banco, pipeline,
regras e ML são componentes para chegar nela — não o produto.

Todo o sistema funciona em **português do Brasil**: interface, alertas,
mecanismo, efeito, orientação e relatório. Nomenclatura científica é
preservada (`CYP3A4` continua `CYP3A4`), mas o que a descreve sai em
português — `Inibidor da CYP3A4`, nunca `CYP3A4 inhibitor`.

## Os dois diretórios

```
C:\Conteudos banco de dados tcc   ACERVO — SOMENTE LEITURA
C:\Sistema Conciliador projeto    este repositório
```

**Nunca crie, mova, altere ou apague nada no acervo.** Ele é a prova de
origem de tudo que o sistema afirma. Transformação é sempre
`original → cópia → tratado`, com o tratado aqui.

O acervo contém um **sistema anterior completo** (`banco/conciliador.db`,
motor, ETLs, interface). Por decisão do usuário (`docs/DECISIONS.md` D-011)
ele é **fonte de dados, referência de resultado e teste de regressão — nunca
base estrutural**. Não reaproveite sua arquitetura nem sua lógica.

## Comandos

Python não está no PATH; saída com acento quebra no console do Windows:

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
```

Reconstruir tudo e rodar as duas verificações (~15 s):

```bash
PYTHONIOENCODING=utf-8 "$PY" pipeline/executar_tudo.py --recriar
```

O script para no primeiro erro e roda os testes ao final (~41 s com tudo).

**Sem `--recriar` a carga é incremental, e incremental aqui quer dizer uma
coisa precisa: reexecutar não muda nada.** Rodar o pipeline de novo sobre a
mesma origem deixa as 44 tabelas byte a byte idênticas — `tests/teste_idempotencia.py`
tira uma fotografia, roda os 11 ETLs e compara. Use isto sempre que quiser
revalidar o banco **sem** perder `modelo` e `predicao`, que `--recriar` apaga.

**Se um arquivo do acervo mudar, a carga incremental PARA** e manda usar
`--recriar` (`_comum.OrigemAlterada`). Ela sabe não repetir o que já entrou;
não sabe reconciliar dado alterado, e fingir que sabe é como dado errado entra
em silêncio. Ver D-045.

Subir a aplicação:

```bash
PYTHONIOENCODING=utf-8 "$PY" app/web.py
```

`http://127.0.0.1:5000`, respeita `PORT`. Não recarrega sozinha — reinicie
depois de editar `web.py` ou os serviços. O log fica em `data/aplicacao.log`.

**Atenção ao preview do editor:** o acervo tem um `.claude/launch.json` com
uma configuração chamada `conciliador` apontando para o sistema **antigo**. A
deste projeto chama-se `conciliador-fase6`. Se a tela que abrir tiver
"Avaliação dos casos" e "2097 substâncias", é o sistema antigo, não este.

Um teste isolado — todos são executáveis diretos, sem pytest:

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/teste_motor_horarios.py
```

Autotestes embutidos nos módulos de transformação (rodam sozinhos):

```bash
PYTHONIOENCODING=utf-8 "$PY" pipeline/_diretivas.py
PYTHONIOENCODING=utf-8 "$PY" pipeline/_substancia_texto.py
PYTHONIOENCODING=utf-8 "$PY" pipeline/traducao_atc.py
PYTHONIOENCODING=utf-8 "$PY" pipeline/traducao_interacao.py
PYTHONIOENCODING=utf-8 "$PY" rules/_prioridade.py
```

Idempotência da carga (roda os 11 ETLs de novo e compara tabela por tabela):

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/teste_idempotencia.py
```

`--rapido` faz só a parte unitária. **Não está em `executar_tudo.py`** (seria
recursão); as garantias baratas que dela derivam estão em `teste_regressao.py`.

Validação do sistema inteiro (Fase 9) — os três primeiros já rodam na bateria:

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_cenarios.py          # 10 cenários
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_v1_sistema.py        # V1, 11 eixos
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_v2_independente.py   # V2, 8 caminhos
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_convergencia.py      # ~1 min, fora da bateria
PYTHONIOENCODING=utf-8 "$PY" auditoria/05_integridade_acervo.py  # ~3 min, lê 2,2 GB
```

`fase9_convergencia.py` reconstrói o banco e **o devolve ao final** — se for
interrompido, a cópia guardada fica no diretório temporário que ele imprime na
primeira linha.

Quadro de qualidade da conciliação (coorte de 20 pacientes sintéticos):

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/qualidade_fase5.py
```

Validação estrutural do banco (sai 1 se qualquer garantia for violada):

```bash
PYTHONIOENCODING=utf-8 "$PY" pipeline/90_validacao.py
```

**A Fase 7 (ML) é um pipeline à parte** e não roda dentro de
`pipeline/executar_tudo.py` — ele reconstrói o banco e apagaria `modelo` e
`predicao`. Reconstruir a camada de ML inteira (~20 min):

```bash
PYTHONIOENCODING=utf-8 "$PY" ml/executar_tudo.py
```

`--rapido` pula as etapas que levam minutos; `--so-verificacao` roda só V1, V2 e
a regressão. O gargalo é `20_treinar.py` (40 execuções). Uma previsão avulsa:

```bash
PYTHONIOENCODING=utf-8 "$PY" ml/70_predizer.py varfarina omeprazol
```

Reproduzir a auditoria do acervo (lê a origem, não escreve nela):

```bash
PYTHONIOENCODING=utf-8 "$PY" auditoria/01_inventario.py
```

Dependências: `chardet`, `pypdf`, `openpyxl`, `numpy`, `flask` — já
instaladas nesta máquina. Sem framework de teste: tudo é `python arquivo.py`.

## Arquitetura

```
acervo (somente leitura)
   ↓  pipeline/  numerado, a ordem importa
database/conciliador.db          44 tabelas, 15 views
   ↓  rules/     motores determinísticos          ↘  ml/  camada preditiva,
Agenda / Achados                                     desligada por decisão
   ↓  app/       serviços + interface Flask  (Fase 6, funcionando)
relatório → ConciliadorMedicamentos.exe   (Fase 10)
```

**A aplicação tem quatro camadas e nenhuma pula outra:**

```
INTERFACE   app/web.py + app/templates/   rotas, formulários, render
SERVIÇOS    app/servicos.py              escreve o atendimento, orquestra
            app/busca.py                 busca tolerante em 4 passes
            app/relatorio.py             monta o relatório
            app/rotulos.py               vocabulário do banco → português
MOTORES     rules/                       as regras, e só elas
BANCO       database/conciliador.db
```

**`app/web.py` não tem uma linha de SQL.** Toda consulta ao conhecimento
farmacológico passa por `busca.py` ou pelos motores; toda escrita passa por
`servicos.py`. Isso é **verificado lendo o código-fonte** em
`tests/verificacao_aplicacao.py` (eixo 3), junto com: nenhum template calcula
prioridade ou gravidade, e os serviços chamam os motores em vez de
reimplementá-los. Ver D-036.

**A numeração do pipeline dita a ordem e ela importa:** substância antes de
produto (o vínculo precisa da substância), produto antes de ATC (o nível 5
usa o nome em português da DCB já carregada), tudo antes de `90_validacao`.

`pipeline/_comum.py` centraliza leitura do acervo, abertura de carga e
registro de evidência. **O dicionário `LEITURA` guarda encoding,
delimitador e linhas a pular de cada arquivo**, medidos na auditoria —
nenhum script redescobre isso. Arquivo novo exige entrada nova ali, ou
`ler_csv` levanta `KeyError` de propósito.

**Um ponto de entrada por motor, e a tela não reimplementa nenhum:**

```
rules/motor_horarios.py     montar_agenda(con, atendimento_id) -> Agenda
rules/motor_conciliacao.py  conciliar_atendimento(con, atendimento_id)
                                -> ResultadoConciliacao
```

`Agenda` tem `.eventos`, `.conflitos`, `.nao_avaliado`, `.rotina`.
`ResultadoConciliacao` tem `.resumo`, `.achados`, `.achados_agrupados`,
`.divergencias`, `.conciliados`, `.nao_conciliados`, `.nao_avaliado`,
`.limitacoes`, `.indicadores` e a `.agenda` inteira.

**O motor de conciliação CONSOME o de horários, não o reimplementa.** Regra
temporal pertence ao `motor_horarios`; classificação, contexto, agrupamento e
prioridade pertencem ao `motor_conciliacao`. Uma exceção declarada: a
duplicidade da Fase 4 não é importada — aquele motor não conhece listas de
conciliação e marcaria duplicidade para um item que está na prescrição **e**
no relato, que é justamente um item *conciliado*.

`rules/_prioridade.py` guarda a tabela de prioridade, uma linha por regra com
a justificativa escrita ao lado. **Nenhum módulo escreve prioridade na mão.**

## Invariantes — estruturais, não convenções

Implementadas no `CHECK`/`VIEW` do esquema e verificadas por
`tests/teste_schema.py` e `pipeline/90_validacao.py`. **Não as contorne para
fazer uma feature funcionar.**

- **Uma linha por (afirmação, fonte).** `UNIQUE` inclui `fonte_id`, nunca
  `origem` (que é enum). Sem isso a segunda fonte do mesmo par seria
  rejeitada em silêncio e `vw_conflito_gravidade` não existiria.
- **ML nunca atribui gravidade.** `predicao.gravidade_sugerida` tem
  `CHECK (... IS NULL)`. A coluna existe só para tornar a regra testável.
- **Previsão não se disfarça de fato.** `achado.natureza='PREVISTO'` exige
  `probabilidade_modelo` **e** `origem_afirmacao LIKE 'predicao.%'` — sempre dá
  para voltar do alerta ao modelo, à versão e à semente. `'DOCUMENTADO'` exige
  `nivel_evidencia`, e `PREVISTO` **não aceita** nível de evidência de
  publicação. `origem_achado='MODELO'` obriga `natureza='PREVISTO'`.
- **Modelo não é trocado em silêncio.** Índice único parcial: no máximo **um**
  modelo `ativo=1` por `problema`, e `CHECK (ativo=0 OR status='HOMOLOGADO')`.
  Publicar outro exige desativar o anterior no mesmo passo. Homologar é ato
  humano — não é `UPDATE` distraído. `modelo` exige `semente`, `versao_dados`,
  `espaco_features_json` e `limitacoes` em português.
- **Previsão gravada nasce `NAO_REVISADA`** e só muda com `revisado_por`.
- **`vw_predicao_liberada` é a única porta da previsão, e é fail-closed.**
  Quatro travas simultâneas, todas no banco: modelo `ativo=1`, `status='HOMOLOGADO'`,
  `limiar_alerta` declarado **e** atingido pela probabilidade calibrada, e
  **o par sem interação documentada**. A quarta é o que impede previsão de
  substituir, contradizer ou duplicar evidência — onde há documento, a previsão
  nem aparece. Ver D-046.
- **Previsão não tem evidência.** Achado `PREVISTO` não gera nenhuma linha em
  `achado_evidencia`; a rastreabilidade vai por `origem_afirmacao='predicao.<id>'`
  e a tela declara a ausência. Prioridade tem teto `INFORMATIVO` **por
  definição**, não por cálculo. Ver D-047.
- **`origem` diz de onde veio; `metodo_extracao` diz como foi lida.** As
  views de regra expõem `confianca_extracao`; extração por regex aparece
  como `EXTRAIDA_AUTOMATICAMENTE` e nunca como revisada.
- **Ausência de dado nunca vira regra.** `regra_separacao.intervalo_horas`
  aceita NULL e a view devolve *"Requer separação — intervalo não
  estabelecido na fonte"*. **Nunca invente um intervalo**, mesmo "2 horas",
  que é comum na prática — comum não é fonte.
- **Contradição dentro de uma fonte não é gravada** (vai para
  `auditoria_conflito` e nenhuma das regras entra); **entre fontes, as duas
  linhas ficam** e o conflito é registrado. Ver D-023.
- **Ambíguo não é fundido.** `substancia.status_resolucao='AMBIGUA'` +
  `resolucao_ambigua` guardam os candidatos para curadoria.
- **Os seis eixos do achado não se fundem.** `gravidade_fonte` (o que a fonte
  diz) · `confianca_sistema` (o quanto o sistema confia) · `prioridade` (em que
  ordem mostrar) · `natureza` (epistemologia) · `classificacao` (detecção neste
  paciente) · `status_informacao` (procedência e revisão). Um achado pode ser
  grave e pouco confiável, e isso tem de aparecer nos dois lugares.
- **A conciliação classifica a situação; nunca a intencionalidade.**
  `conciliacao_par.intencionalidade` só sai de `NAO_DETERMINADA` com
  `avaliado_por` preenchido — e o `CHECK` recusa sem assinatura. Diferença não
  é erro.
- **Agrupar nunca apaga evidência.** O achado absorvido continua na tabela com
  `status='AGRUPADO'`, e suas evidências vão para o representante. A view
  `vw_achado_clinico` mostra só os representantes.
- **`grupo_chave` identifica o problema, nunca a linha.** Chave presa a
  `atendimento_medicamento.id` faz o agrupamento depender da ordem de cadastro.
- **Gravidade que a fonte não publica não é inventada nem escondida:** fica
  `NAO_DETERMINADA`, prioridade BAIXO, e é contada à parte no resumo.
- **A anotação do profissional é presa a uma chave ESTÁVEL**
  (`achado.grupo_chave`, ou tipo+substância da divergência), nunca ao `id` do
  achado — que muda a cada análise. Presa ao id, a revisão sumiria na primeira
  reanálise. Ver D-033.
- **A interface nunca decide intencionalidade.** O formulário exige o nome do
  profissional, o serviço recusa sem ele, e o `CHECK` do banco recusa depois.
  Duas barreiras independentes, e as duas testadas.
- **A tela mostra o que o motor devolve, e isso é comparado por teste.** O
  eixo 1 da verificação independente confronta a página com
  `conciliar_atendimento` chamado direto, achado a achado.

## Detalhes que economizam tempo

- **`pipeline/normalizacao.py`** é o esqueleto fonético que une PT↔EN
  (`dipirona monoidratada` → `metamisol`). Todo join entre fontes depende
  dele. Cópia do acervo com procedência no cabeçalho; duas correções já
  aplicadas (hidratos superiores, `ácido` após sal). **Alterá-lo muda todo o
  casamento** — rode `tests/teste_normalizacao.py` (33 casos fixados).
- **`_comum.chaves_candidatas()`** resolve forma ácida (EN) × sal (BR):
  `alendronic acid` → `alendronato`. Efeito colateral conhecido: duas
  entradas da mesma fonte podem colidir numa substância BR (Fenofibrate ×
  Fenofibric acid) — tratado pela limpeza intra-fonte em `50_*`.
- **CMED:** cabeçalho no **registro 41** (linha física 60), não na linha 1.
  Separador de associação é `;` (a ANVISA usa `,`). `TARJA` vem rotulada por
  extenso — use isso, nunca o `CO_TARJA` numérico da ANVISA, que o sistema
  anterior mapeou ao contrário e chegou a dizer que tramadol era venda livre.
- **EAN não é identidade:** 183 aparecem em mais de uma apresentação e `-`
  marca ausente 50.217 vezes. A chave natural é `codigo_ggrem`. Códigos de
  barras ficam em `apresentacao_ean` (até 3 por apresentação).
- **Registro ANVISA de produto = 9 primeiros dígitos.** O número completo da
  CMED inclui sufixo de apresentação.
- **CAS da DCB traz `[Ref. 8]`** quando não há CAS (vacinas, botânicos). Só
  entra o que casa `\d{2,7}-\d{2}-\d`.
- **Nome botânico legitimamente tem parênteses** (`Ananas comosus (L.)
  Merr.`). Não trate como resíduo de divisão.
- **Tradução de classe ATC é por molde, tudo-ou-nada**
  (`pipeline/traducao_atc.py`). Palavra a palavra produzia `Cálcio canal
  bloqueadores`. Níveis 1 e 2 estão em 100%; 75% do total segue em inglês,
  **declarado**, nunca traduzido pela metade.
- **`JANELA_REFEICAO_MIN = 30`** em `rules/motor_horarios.py` é o único
  número temporal que não vem de fonte. **Não é intervalo terapêutico** — é
  a janela de leitura para dizer se um horário está perto de uma refeição. Se
  usada, o conflito sai `POSSIVEL`, nunca `CONFIRMADO`.
- Contar `\n` superestima 8 arquivos do acervo (quebra de linha dentro de
  campo). `wc -l` está errado aqui.
- **`atendimento_medicamento.lista`** diz de QUAL lista o item veio
  (`PRESCRITA` · `RELATADA` · `EM_USO` · `HISTORICO` · `ANTERIOR`), e é distinta
  de `origem`, que diz a natureza do uso. O mesmo fármaco em duas listas são
  **duas linhas**; parear as duas é o ato de conciliar.
- **Duplicidade terapêutica é no 4º nível ATC** (5 caracteres), nunca no 5º: o
  5º *é* a substância, e no banco há **zero** grupos de 5º nível com duas
  substâncias diferentes. No 4º há 248.
- **Não use `interacao_substancia` sem passar por `vw_interacao_liberada`**, e o
  mesmo vale para doença, item e hábito — cada um tem a sua view.
- **`traducao_interacao.py` é tudo-ou-nada.** Molde que casa mas com slot fora
  do glossário devolve o **original intacto**. Cobre 99,97% das descrições do
  `db_drug_interactions`. Rode o autoteste depois de mexer.
- **O DDInter não publica descrição nenhuma** (58.323 linhas sem texto) e o
  `db_drug_interactions` **não gradua gravidade nenhuma**. As duas entram como
  linhas separadas do mesmo par, de propósito.
- **O módulo 13 do motor lê uma VIEW, não roda modelo.** `rules/` e `app/` não
  importam nada de `ml/` e não carregam scikit-learn — o modelo escreve em
  `predicao`, o motor lê `vw_predicao_liberada`. `teste_ml.py` lê o
  código-fonte e reprova `import sklearn/joblib/pickle/numpy` no caminho
  determinístico. Não quebre isso: é o que mantém o `.exe` da Fase 10 leve.
- **Para testar a integração, homologue numa CÓPIA do banco.** Os dois testes
  da Fase 8 copiam `conciliador.db` para um temporário e patcham `sv.BANCO`.
  Homologar em produção seria ligar o que a Fase 7 decidiu manter desligado.
- **Procurar `PREVISTO POR MODELO` no HTML dá falso positivo** — casa com o
  comentário da seção, que é renderizado mesmo com o bloco vazio. Use
  `id="bloco-previsto"`, que só existe dentro do `{% if previstos %}`.
- **`carga` é o LOTE de dados, não o log de execuções.** A identidade é
  (fonte, script, documento, hash do arquivo); reexecutar não cria linha nova,
  e `fechar_carga` só fecha lote aberto — reescrever os números do lote
  original com os zeros de uma passada que não inseriu nada apagaria a
  resposta de "quantas linhas entraram deste arquivo".
- **`_comum.inserir_unico()` é como se insere em tabela de afirmação.**
  `cur.lastrowid` depois de um `INSERT OR IGNORE` que **ignorou** devolve o id
  da inserção anterior — silenciosamente errado, e é o que acontecia em vários
  ETLs. `teste_regressao.py` lê o código-fonte e reprova `INSERT INTO` cru em
  qualquer das 13 tabelas de afirmação.
- **Toda tabela de afirmação precisa de chave de unicidade.**
  `regra_separacao` era a única sem, e o banco carregava **12 cópias exatas**
  (brometo de zinco tinha 15 linhas para 3 regras: cinco entradas do DrugBank
  caem na mesma substância brasileira). A chave inclui todo o conteúdo, para
  que contradição real dentro da fonte continue visível — só cópia idêntica é
  colapsada.
- **O espaço de atributos do ML é definido em `ml/_features.py` e em lugar
  nenhum mais.** Treino e predição importam a mesma função; `70_predizer.py`
  aborta se divergir do gravado em `models/espaco_features.json`. Foi assim que
  o sistema anterior quebrou em silêncio ao acrescentar o ATC.
- **O bloco de atributos de GRAFO existe e está FORA do modelo publicado.**
  Grau e vizinhos comuns são contagem de rótulos positivos disfarçada de
  atributo: com eles a AUC vai a 0,944 em fármaco conhecido e a **0,3415, pior
  que o acaso**, em fármaco inédito. Ele só continua no código porque é a
  ablação que sustenta D-038. Não o traga de volta.
- **O 5º nível do ATC não pode ser atributo** — nenhum código de 5º nível é
  compartilhado por duas substâncias, então ele *é* a substância. Entram os
  níveis 1 a 4.
- **`ml/` não é importado por `rules/` nem por `app/`**, e `tests/teste_ml.py`
  lê o código-fonte para garantir. O ML fala com o resto por uma porta só:
  `ml/70_predizer.py`.
- **Nenhum modelo está ativo, e isso é a decisão, não um pendente** (D-041): no
  regime realista o modelo tem recall 0,56 e precisão 0,39 — viraria fadiga de
  alerta. O uso liberado é a fila de curadoria em
  `reports/fila_curadoria_m1.csv`.

- **Toda mensagem de estado da interface é presa ao atendimento que a gerou.**
  Use `web.avisar(texto, categoria, codigo)`, nunca `flash()` cru — a fila do
  Flask é da SESSÃO, e sem o código do atendimento a confirmação de um paciente
  aparece na tela de outro. `base.html` mostra o que é da tela e devolve o resto
  para a fila; mensagem sem atendimento (erro no início) aparece em qualquer
  tela, de propósito. Ver D-049.
- **A probabilidade de uma previsão é escrita em um lugar só:**
  `rules/_prioridade.percentual_previsao`. A calibração isotônica **satura** —
  a faixa mais alta da validação recebe exatamente 1,0 —, e escrever "100%" ao
  lado de "não há evidência documental" prometia certeza. Acima de 0,995 sai
  "acima de 99%"; o valor exato com quatro casas fica no painel de
  rastreabilidade. Nenhum template, relatório ou módulo formata percentual por
  conta própria. Ver D-050.
- **Vocabulário do banco não chega cru à tela.** O subtipo do achado saía como
  `interacao prevista`; agora passa por `rotulos.SUBTIPO`. Valor desconhecido
  volta como veio, nunca vira outra coisa.
- **Teste que cria atendimento tem de apagar o PACIENTE também.** Procurar o
  paciente a partir do atendimento no fim da limpeza não funciona quando o
  teste apaga o atendimento de propósito — foi assim que cinco linhas
  "Integridade B" ficaram no banco de produção. Guarde o `paciente_id` na
  criação.
- **`tests/fase9_convergencia.py` e `auditoria/05_integridade_acervo.py` NÃO
  entram em `executar_tudo.py`**, e o motivo está escrito lá: o primeiro roda
  os ETLs (seria recursão) e o segundo lê 2,2 GB do acervo. São deliberados.

- **`fonte.confiabilidade` é onde a procedência fraca fica declarada** — não em
  `metodo_extracao`. Marcar como `REGEX` uma linha lida de coluna, porque um
  campo acessório foi derivado, rebaixa a confiança de dezenas de milhares de
  registros por engano.

- **Associação em dose fixa vira uma linha por componente** em
  `atendimento_medicamento`, com o mesmo `nome_relatado` — o módulo de
  interação precisa enxergar os dois lados. As telas agrupam por
  `(lista, nome_relatado, apresentacao_id)`, e a posologia informada uma vez
  vale para o grupo inteiro. `servicos.listar_medicamentos` devolve os grupos.
- **`buscar_medicamento` responde em 4 passes**, do determinístico ao
  tolerante: código de barras → chave fonética exata → prefixo → nome
  comercial. Cada resultado carrega `reconhecimento` e `confianca`, e a tela
  mostra os dois.
- **Campo em branco no formulário fica `None`**, nunca zero nem valor padrão.
  `servicos._validar_numero` recusa zero explicitamente e manda deixar em
  branco.
- **`ErroDeUso` é erro do formulário** e a mensagem vai para a tela como está;
  qualquer outra exceção vira página genérica e o detalhe vai para
  `data/aplicacao.log`. `HTTPException` é repassada — engoli-la transformava
  404 em 500.

## Disciplina de verificação

Toda fase exige **duas verificações independentes** antes de ser marcada
concluída:

1. **Funcional** — testes e execução real (`90_validacao.py`, autotestes).
2. **Independente** — outro caminho, não o mesmo teste de novo: recontagem
   do arquivo bruto com código próprio, comparação com o banco do sistema
   anterior, consulta SQL escrita à parte, implementação alternativa do
   cálculo, casos clínicos conhecidos, teste de propriedade.

Isso não é cerimônia: **todos os defeitos sérios do projeto foram achados
pela segunda verificação, nenhum pela primeira.** Quando ela acusar, primeiro
descubra se o defeito é do código ou do teste — já houve quatro falsos
positivos de teste (parêntese botânico, `+ SERINGA`, fixture de classe usada
como item, horário antes de acordar).

`tests/teste_regressao.py` trava 61 verificações de defeitos já corrigidos. Se algum falhar,
a causa é uma alteração recente.

Casos clínicos usam **farmacologia real do banco**; só o paciente é
sintético. Nunca invente evidência farmacológica para montar um caso.

## Onde estamos

Estado detalhado por fase em `docs/STATUS.md`. Decisões em
`docs/DECISIONS.md` (50 entradas) — **consulte antes de reconstruir uma
justificativa**.

| Fase | | Estado |
|---|---|---|
| 1 | Auditoria, modelo de dados, esquema | **Concluída** |
| 2 | Pipeline de carga e normalização | **Concluída** |
| 3 | Regras de administração e separação | **Concluída** |
| 4 | Motor de horários | **Concluída** |
| 5 | Motor de conciliação (12 módulos) + interações | **Concluída** |
| 6 | **Aplicação do farmacêutico** | **Concluída** |
| 7 | **Machine Learning** | **Concluída** |
| 8 | **Testes integrados + integração do modelo** | **Concluída** |
| 9 | **Validação do sistema inteiro** | **Concluída — apto para empacotamento** |
| 10 | Empacotamento `.exe` | **próxima** |

Carregado hoje: 2.094 substâncias · 8.935 produtos · 25.702 apresentações ·
26.889 códigos de barras · 6.996 classes ATC · 723 regras de administração ·
59 de separação · **112.520 interações fármaco × fármaco (94.770 pares)** ·
289 com item · 199 com hábito · **182 contraindicações de bula** ·
**28 papéis farmacocinéticos (FDA)** · 153.647 registros de evidência.
**44 tabelas, 15 views, 73 MB.** Pipeline completo com as duas verificações e
a bateria inteira (**972 conferências**): ~90 s. Números remedidos pela
Fase 9, que reconstruiu o banco do zero e comparou tabela por tabela.
Camada de ML: **130 atributos**, 40 execuções comparadas, 2 modelos
registrados, **0 ativos**, 600 previsões em fila de curadoria.

**A aplicação existe e funciona de ponta a ponta.** É possível conduzir um
atendimento inteiro — paciente, anamnese, medicamentos, posologia, rotina,
alimentos, conciliação, análise, achados, evidências, relatório — e o
resultado chega corretamente aos motores. Exemplo real de saída em
`docs/ATENDIMENTO_EXEMPLO.md`; arquitetura da aplicação em `docs/APLICACAO.md`.

**A Fase 9 (validação do sistema inteiro) terminou: APTO PARA EMPACOTAMENTO.**
Relatório em `docs/FASE9_VALIDACAO.md`; inventário da Fase 10 em
`docs/EMPACOTAMENTO.md`. Quatro defeitos reais, todos de costura entre módulos.
O pipeline converge na primeira passada e reproduz o banco tabela por tabela; o
acervo continua com 689 arquivos e 0 modificados. **"Apto para empacotar" não é
validação clínica e não é "pronto para distribuir"** — o banco precisa ser
gravável e conhecimento e atendimento ainda estão no mesmo arquivo.

**A Fase 7 (ML) terminou, e a conclusão dela é uma recusa.** Relatório em
`docs/ML_FASE7.md`; leia antes de mexer em qualquer coisa de ML.

- **Dois alvos treinados, seis recusados com número ao lado.** O mais desejado
  — relevância do alerta — é impossível: `anotacao_profissional` tem a
  estrutura pronta e **zero linhas**. A Fase 6 escreveu aqui que "o rótulo
  humano começa a existir"; começou a existir a estrutura, não o rótulo.
- **AUC 0,9442 no protocolo da literatura, 0,7392 no honesto** (split por
  fármaco, os dois lados inéditos). A diferença é inteira de protocolo. Sempre
  reporte os dois lado a lado.
- **Nenhum modelo está ativo, por decisão medida (D-041):** no regime realista
  o modelo tem recall 0,56 e precisão 0,39 — deixaria passar quase metade e
  erraria 6 em 10 avisos. O uso liberado é **priorizar curadoria**, onde a
  precisão no topo 1% é 0,80 contra 0,204 de linha de base.
- **GNN: respondida com medição, antes de treinar.** 1.137 das 2.094
  substâncias têm grau zero; entre as 957 conectadas o grafo é denso (20,7%) e
  tem componente única. A heurística de grafo dá **AUC 0,5000 exata** em
  fármaco inédito. Ver D-038.
- **M3 (gravidade) segue fora**, agora confirmado por medição própria: 38.459
  de 94.770 pares graduados e **um único graduador**, logo a consistência do
  rótulo é imensurável neste acervo.
- **A limitação que ordena todas:** o negativo é presumido. O modelo estima
  probabilidade de o par **estar documentado**, não de ser perigoso — e o
  atributo mais importante é "este fármaco tem regra de administração
  cadastrada", isto é, quão estudado ele é. Ver D-040.

## Lacunas conhecidas — não mascare

- **65,8% das linhas de interação não têm gravidade graduada** — a fonte não
  gradua. Das duas bases, só o DDInter gradua, e ele marca boa parte como
  `Unknown`. Consequência: **`vw_conflito_gravidade` devolve zero**, e não por
  concordância entre fontes — por só uma delas graduar.
- **Módulo fármaco × doença cobre 4,9% das substâncias** (102 de 2.094) e
  **100% dele está pendente de revisão**.
- **Módulo CYP cobre 1,1%** (22 substâncias), só CYP, nenhum transportador.
- **Nenhum achado é revisado por farmacêutico.** Zero, e o sistema declara isso
  em cada um.
- **Reação adversa não é avaliada** (VigiMed não carregado) e **medicamento ×
  exame laboratorial está fora de escopo** — as duas coisas são declaradas em
  `nao_avaliado`, não silenciadas.
- **Não há critério de inadequação em idoso** (Beers, STOPP/START). A idade é
  exibida e **não altera prioridade**.
- **29,6% das substâncias têm regra de administração.** O resto não tem
  porque a fonte não cobre.
- **Nenhuma das 723 regras foi revisada por farmacêutico.**
- **Zero regras de separação fármaco×fármaco diretas** em todo o acervo.
- **75% das classes ATC seguem em inglês**, marcadas como não traduzidas.
- **Zero anotações de farmacêutico** (`anotacao_profissional`). Sem elas não há
  modelo de relevância, não há negativo verdadeiro e nada pode ser homologado.
  Faltam ~97 avaliações para uma estimativa com ±10 pontos; 400 a 1.000 para
  um modelo com concordância entre avaliadores.
- **Nenhuma estrutura química no acervo** — há CAS, que é identificador, não
  estrutura. Sem fingerprint não há similaridade estrutural, e é a lacuna de
  maior impacto potencial no ML.
- **`substancia.atc_codigo` guarda UM código por substância.** Fármaco com
  várias indicações perde as outras, e isso já distorceu uma explicação real
  (metronidazol aparece como preparação odontológica). Ver ML_FASE7.md §7.3.
- Fontes candidatas para as lacunas estão em `docs/novas_fontes.md`. Fonte
  nova entra lá **antes** de ser carregada.

## Ferramentas de outros agentes

Existe um `~/.codex/config.toml` nesta máquina. Se quiser trazer MCP servers,
comandos, subagents ou instruções de lá, responda `/import` para ver o que é
importável e depois `/import --yes=<digest>` para aplicar.
