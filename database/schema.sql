-- =====================================================================
-- CONCILIADOR DE MEDICAMENTOS — esquema canônico
-- SQLite 3 · pt-BR · v2 · 09/09/2026
--
-- Arquitetura nova, escrita do zero. O sistema anterior é fonte de dados
-- e referência de validação, não base estrutural (docs/DECISIONS.md D-011).
-- Correções da revisão pré-carga: docs/REVISAO_SCHEMA.md (P-01 a P-09).
--
-- Regras estruturais, implementadas aqui e verificadas em tests/:
--   1. Posologia é ESTRUTURADA. Texto livre acompanha, nunca é o dado.
--   2. Fato e previsão nunca ocupam a mesma tabela.
--   3. O que a fonte não estabeleceu fica NULL, com motivo declarado.
--   4. Uma linha por (afirmação, fonte). Conflito é consulta, não colisão.
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;


-- =====================================================================
-- CAMADA 6 — FONTES, CARGAS E EVIDÊNCIA
-- Criada primeiro: toda afirmação clínica aponta para cá.
-- =====================================================================

CREATE TABLE fonte (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL UNIQUE,
    tipo                TEXT NOT NULL CHECK (tipo IN (
                            'REGULATORIA',      -- ANVISA, FDA, CMED
                            'GOVERNAMENTAL',    -- RENAME, SNGPC, VigiMed
                            'BASE_CIENTIFICA',  -- DDInter, IUPHAR, DrugBank
                            'LITERATURA',       -- artigo indexado
                            'BULA',             -- bula registrada na ANVISA
                            'CURADORIA',        -- escrita por farmacêutico
                            'COMPILACAO')),     -- sem procedência rastreável
    url                 TEXT,
    licenca             TEXT,
    -- Confiabilidade da FONTE. Distinta de nível de evidência da afirmação
    -- e de confiança do modelo: as três nunca são somadas.
    confiabilidade      TEXT NOT NULL CHECK (confiabilidade IN
                            ('ALTA','MEDIA','BAIXA','NAO_AVALIADA')),
    observacao          TEXT
);

-- Uma linha por execução de script sobre um arquivo. Responde
-- "quando isto entrou, de qual arquivo, em qual versão" (P-02).
CREATE TABLE carga (
    id                  INTEGER PRIMARY KEY,
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    script              TEXT NOT NULL,
    documento_origem    TEXT NOT NULL,      -- caminho relativo no acervo
    versao              TEXT,               -- versão declarada pela fonte
    hash_arquivo        TEXT,               -- detecta troca silenciosa do arquivo
    data_importacao     TEXT NOT NULL DEFAULT (datetime('now')),
    registros_lidos     INTEGER,
    registros_inseridos INTEGER,
    registros_ignorados INTEGER,
    observacao          TEXT
);
CREATE INDEX ix_carga_fonte ON carga (fonte_id);

-- Liga qualquer afirmação à fonte que a sustenta.
-- Polimórfica de propósito: alvo é (tabela, id).
CREATE TABLE evidencia (
    id                  INTEGER PRIMARY KEY,
    tabela_alvo         TEXT NOT NULL,
    id_alvo             INTEGER NOT NULL,
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    carga_id            INTEGER REFERENCES carga(id),
    documento           TEXT,               -- arquivo, DOI, PMID, nº de registro
    trecho              TEXT,               -- citação literal que sustenta
    nivel_evidencia     TEXT NOT NULL CHECK (nivel_evidencia IN (
                            'RESPALDADA',   -- estudo ou fonte regulatória direta
                            'LIMITADA',     -- relato, série pequena, extrapolação
                            'TEORICA',      -- deduzida de mecanismo
                            'NAO_AVALIADA')),
    metodo_extracao     TEXT NOT NULL CHECK (metodo_extracao IN (
                            'CARGA_DIRETA','REGEX','NLP','CURADORIA_HUMANA')),
    revisado_por        TEXT,
    revisado_em         TEXT,
    UNIQUE (tabela_alvo, id_alvo, fonte_id, documento)
);
CREATE INDEX ix_evidencia_alvo  ON evidencia (tabela_alvo, id_alvo);
CREATE INDEX ix_evidencia_fonte ON evidencia (fonte_id);


-- =====================================================================
-- CAMADA 3 — BASE FARMACOLÓGICA
-- =====================================================================

-- Antes de substancia porque é referenciada por ela (P-07).
CREATE TABLE classe_atc (
    codigo              TEXT PRIMARY KEY,
    nome_pt             TEXT NOT NULL,
    nome_en             TEXT,
    nivel               INTEGER NOT NULL CHECK (nivel BETWEEN 1 AND 5),
    codigo_pai          TEXT REFERENCES classe_atc(codigo)
);

CREATE TABLE substancia (
    id                  INTEGER PRIMARY KEY,
    nome_dcb            TEXT NOT NULL UNIQUE,   -- nome oficial brasileiro
    nome_en             TEXT,                   -- INN, junta com fonte externa
    chave_normalizada   TEXT NOT NULL,          -- esqueleto fonético (une PT/EN)
    dcb_numero          TEXT,
    cas                 TEXT,
    atc_codigo          TEXT REFERENCES classe_atc(codigo),
    canal_dispensacao   TEXT CHECK (canal_dispensacao IN (
                            'MIP','TARJA_VERMELHA','TARJA_VERMELHA_RETENCAO',
                            'TARJA_PRETA','NAO_DETERMINADO')),
    indice_terapeutico_estreito INTEGER NOT NULL DEFAULT 0
                            CHECK (indice_terapeutico_estreito IN (0,1)),
    na_rename           INTEGER NOT NULL DEFAULT 0 CHECK (na_rename IN (0,1)),
    n_produtos_ativos   INTEGER NOT NULL DEFAULT 0,
    -- Deduplicação nível 5: ambíguo não é fundido em silêncio (P-05).
    status_resolucao    TEXT NOT NULL DEFAULT 'RESOLVIDA'
                            CHECK (status_resolucao IN
                                   ('RESOLVIDA','AMBIGUA','PENDENTE')),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_substancia_chave ON substancia (chave_normalizada);
CREATE INDEX ix_substancia_atc   ON substancia (atc_codigo);

-- Marca, sinônimo popular, grafia alternativa. Alimenta o autocomplete.
CREATE TABLE substancia_sinonimo (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    nome                TEXT NOT NULL,
    chave_normalizada   TEXT NOT NULL,
    tipo                TEXT NOT NULL CHECK (tipo IN
                            ('MARCA','INN','DCB_ALTERNATIVA','POPULAR','ABREVIACAO')),
    UNIQUE (substancia_id, nome)
);
CREATE INDEX ix_sinonimo_chave ON substancia_sinonimo (chave_normalizada);

-- Identificadores externos: base da deduplicação de nível 1 e 2 (P-04).
CREATE TABLE substancia_identificador (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    sistema             TEXT NOT NULL CHECK (sistema IN
                            ('DRUGBANK','PUBCHEM_CID','CHEMBL','UNIPROT',
                             'DDINTER','GTOPDB','CO_SUBSTANCIA_ANVISA','CAS','DCB')),
    valor               TEXT NOT NULL,
    UNIQUE (sistema, valor, substancia_id)
);
CREATE INDEX ix_ident_subst ON substancia_identificador (substancia_id);
CREATE INDEX ix_ident_valor ON substancia_identificador (sistema, valor);

-- Termo de origem que casou com mais de um candidato. Guardado para
-- curadoria em vez de resolvido por sorteio (P-05).
CREATE TABLE resolucao_ambigua (
    id                  INTEGER PRIMARY KEY,
    termo_origem        TEXT NOT NULL,
    chave_normalizada   TEXT NOT NULL,
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    carga_id            INTEGER REFERENCES carga(id),
    candidatos          TEXT NOT NULL,      -- JSON: [{id, nome_dcb}, ...]
    n_candidatos        INTEGER NOT NULL CHECK (n_candidatos >= 2),
    situacao            TEXT NOT NULL DEFAULT 'AMBIGUO'
                            CHECK (situacao IN ('AMBIGUO','RESOLVIDO','DESCARTADO')),
    resolvido_para      INTEGER REFERENCES substancia(id),
    resolvido_por       TEXT,
    UNIQUE (termo_origem, fonte_id)
);

CREATE TABLE produto (
    id                  INTEGER PRIMARY KEY,
    registro_anvisa     TEXT,
    nome_comercial      TEXT NOT NULL,
    empresa             TEXT,
    cnpj                TEXT,
    categoria           TEXT,               -- Genérico, Similar, Novo, Fitoterápico
    situacao            TEXT NOT NULL CHECK (situacao IN ('ATIVO','INATIVO')),
    UNIQUE (registro_anvisa, nome_comercial)
);
CREATE INDEX ix_produto_nome ON produto (nome_comercial);

CREATE TABLE apresentacao (
    id                  INTEGER PRIMARY KEY,
    produto_id          INTEGER NOT NULL REFERENCES produto(id) ON DELETE CASCADE,
    -- Chave natural da CMED: 25.702 valores, zero repetição (P-06).
    codigo_ggrem        TEXT UNIQUE,
    descricao           TEXT NOT NULL,
    concentracao_valor  REAL,               -- estruturado: 500, não "500 mg"
    concentracao_unidade TEXT,
    forma_farmaceutica  TEXT,
    via_administracao   TEXT,
    quantidade_embalagem INTEGER
);
CREATE INDEX ix_apresentacao_produto ON apresentacao (produto_id);

-- Uma apresentação pode ter mais de um código de barras: a CMED traz EAN 1,
-- EAN 2 e EAN 3, e 1.129 linhas usam o segundo. O leitor de caixa precisa
-- encontrar a apresentação por QUALQUER um deles, então o EAN é tabela
-- própria e não coluna. Não é único: 183 EANs aparecem em mais de uma linha
-- da CMED, e '-' (ausente, 50.217 vezes) vira NULL na carga.
CREATE TABLE apresentacao_ean (
    id                  INTEGER PRIMARY KEY,
    apresentacao_id     INTEGER NOT NULL REFERENCES apresentacao(id) ON DELETE CASCADE,
    ean                 TEXT NOT NULL,
    ordem               INTEGER NOT NULL DEFAULT 1 CHECK (ordem BETWEEN 1 AND 3),
    UNIQUE (apresentacao_id, ean),
    -- EAN-13 ou EAN-8; qualquer coisa fora disso é erro de digitação da fonte
    CHECK (length(ean) IN (8, 12, 13, 14) AND ean NOT GLOB '*[^0-9]*')
);
CREATE INDEX ix_apres_ean ON apresentacao_ean (ean);

-- Associação em dose fixa: uma linha por componente.
CREATE TABLE apresentacao_substancia (
    apresentacao_id     INTEGER NOT NULL REFERENCES apresentacao(id) ON DELETE CASCADE,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id),
    PRIMARY KEY (apresentacao_id, substancia_id)
);
CREATE INDEX ix_apres_subst ON apresentacao_substancia (substancia_id);

-- ---------------------------------------------------------------- alvo e CYP

CREATE TABLE alvo_molecular (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL UNIQUE,
    tipo                TEXT NOT NULL CHECK (tipo IN
                            ('RECEPTOR','ENZIMA','TRANSPORTADOR','CANAL_IONICO','OUTRO')),
    simbolo_gene        TEXT,
    uniprot             TEXT
);

CREATE TABLE substancia_alvo (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    alvo_id             INTEGER NOT NULL REFERENCES alvo_molecular(id),
    acao                TEXT NOT NULL CHECK (acao IN
                            ('AGONISTA','ANTAGONISTA','AGONISTA_PARCIAL','INIBIDOR',
                             'MODULADOR_ALOSTERICO','SUBSTRATO','DESCONHECIDA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    UNIQUE (substancia_id, alvo_id, acao, fonte_id)
);
CREATE INDEX ix_subst_alvo ON substancia_alvo (substancia_id);

CREATE TABLE papel_farmacocinetico (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    sistema             TEXT NOT NULL,      -- CYP3A4, CYP2D6, P-gp, OATP1B1...
    papel               TEXT NOT NULL CHECK (papel IN ('SUBSTRATO','INIBIDOR','INDUTOR')),
    potencia            TEXT NOT NULL CHECK (potencia IN
                            ('FORTE','MODERADA','FRACA','NAO_DECLARADA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    UNIQUE (substancia_id, sistema, papel, fonte_id)
);
CREATE INDEX ix_pk_subst ON papel_farmacocinetico (substancia_id);

-- ------------------------------------------- itens não medicamentosos e doença

CREATE TABLE item_nao_medicamentoso (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL UNIQUE,
    chave_normalizada   TEXT NOT NULL,
    tipo                TEXT NOT NULL CHECK (tipo IN
                            ('ALIMENTO','BEBIDA','CHA','PLANTA_MEDICINAL',
                             'SUPLEMENTO','VITAMINA','MINERAL')),
    taxon               TEXT,               -- nome científico, quando planta
    na_renisus          INTEGER NOT NULL DEFAULT 0 CHECK (na_renisus IN (0,1))
);
CREATE INDEX ix_item_chave ON item_nao_medicamentoso (chave_normalizada);

CREATE TABLE doenca (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL UNIQUE,
    cid10               TEXT,
    mesh                TEXT,
    grupo               TEXT                -- agrupa para o checklist da anamnese
);

CREATE TABLE reacao_adversa (
    id                  INTEGER PRIMARY KEY,
    termo_pt            TEXT NOT NULL UNIQUE,   -- MedDRA PT, já em português
    meddra_soc          TEXT,
    meddra_hlt          TEXT
);


-- =====================================================================
-- REGRAS DE ADMINISTRAÇÃO — núcleo novo do sistema
-- =====================================================================

CREATE TABLE regra_administracao (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    tipo                TEXT NOT NULL CHECK (tipo IN (
                            'JEJUM','COM_ALIMENTO','APOS_ALIMENTO','ANTES_ALIMENTO',
                            'INDIFERENTE_ALIMENTO','COM_AGUA_ABUNDANTE',
                            'PERMANECER_SENTADO','MATINAL','NOTURNO',
                            'CONFORME_SINTOMA','NAO_PARTIR_NAO_TRITURAR','SUBLINGUAL')),
    -- Minutos entre medicamento e refeição. NULL = a fonte não estabeleceu.
    -- Não preencher por analogia (DECISIONS.md D-013).
    intervalo_refeicao_min INTEGER CHECK (intervalo_refeicao_min IS NULL
                                          OR intervalo_refeicao_min BETWEEN 0 AND 720),
    texto_orientacao    TEXT NOT NULL,      -- frase exibida, em pt-BR
    origem              TEXT NOT NULL CHECK (origem IN
                            ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA','INFERIDA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    status_revisao      TEXT NOT NULL DEFAULT 'PENDENTE'
                        CHECK (status_revisao IN ('PENDENTE','APROVADO','REJEITADO')),
    -- Uma linha por fonte: bula e DrugBank podem discordar, e a discordância
    -- precisa ser visível em vez de rejeitada na inserção (P-09).
    UNIQUE (substancia_id, tipo, fonte_id)
);
CREATE INDEX ix_regra_adm_subst ON regra_administracao (substancia_id);

CREATE TABLE regra_separacao (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    alvo_tipo           TEXT NOT NULL CHECK (alvo_tipo IN
                            ('SUBSTANCIA','ITEM','CLASSE_ATC')),
    alvo_substancia_id  INTEGER REFERENCES substancia(id),
    alvo_item_id        INTEGER REFERENCES item_nao_medicamentoso(id),
    alvo_classe_atc     TEXT REFERENCES classe_atc(codigo),
    -- NULL é valor LEGÍTIMO e majoritário: nenhuma fonte do acervo publica
    -- intervalo (0 de 191.541 registros em db_drug_interactions). Quando NULL,
    -- a interface diz "intervalo não estabelecido" e NUNCA sugere um número.
    intervalo_horas     REAL CHECK (intervalo_horas IS NULL
                                    OR intervalo_horas BETWEEN 0.25 AND 24),
    sentido             TEXT NOT NULL DEFAULT 'AMBOS'
                            CHECK (sentido IN ('ANTES','DEPOIS','AMBOS')),
    motivo              TEXT NOT NULL,      -- quelação, alteração de pH, competição
    origem              TEXT NOT NULL CHECK (origem IN
                            ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA','INFERIDA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    status_revisao      TEXT NOT NULL DEFAULT 'PENDENTE'
                        CHECK (status_revisao IN ('PENDENTE','APROVADO','REJEITADO')),
    CHECK ((alvo_tipo='SUBSTANCIA'  AND alvo_substancia_id IS NOT NULL
                                    AND alvo_item_id IS NULL AND alvo_classe_atc IS NULL)
        OR (alvo_tipo='ITEM'        AND alvo_item_id IS NOT NULL
                                    AND alvo_substancia_id IS NULL AND alvo_classe_atc IS NULL)
        OR (alvo_tipo='CLASSE_ATC'  AND alvo_classe_atc IS NOT NULL
                                    AND alvo_substancia_id IS NULL AND alvo_item_id IS NULL))
);
-- Copia EXATA nao entra duas vezes. Esta era a unica tabela de afirmacao sem
-- chave de unicidade, e o efeito estava no banco: 'brometo de zinco' tinha 15
-- linhas para 3 regras, porque cinco entradas do DrugBank (acetato, sulfato,
-- gluconato, cloreto e brometo de zinco) caem na mesma substancia brasileira
-- e cada uma gravava as mesmas 3 regras. As irmas (regra_administracao,
-- interacao_item, interacao_habito) ja tinham UNIQUE e por isso nao inflaram.
--
-- A chave inclui TODO o conteudo da afirmacao — inclusive intervalo, sentido e
-- motivo. Assim, duas regras REALMENTE diferentes para o mesmo par continuam
-- entrando as duas (contradicao dentro da fonte fica visivel, D-023), e so o
-- que e identico letra por letra e colapsado. `status_revisao` fica de fora:
-- aprovar uma regra nao pode abrir espaco para uma copia dela.
CREATE UNIQUE INDEX ux_regra_separacao ON regra_separacao (
    substancia_id, alvo_tipo,
    COALESCE(alvo_substancia_id, -1), COALESCE(alvo_item_id, -1),
    COALESCE(alvo_classe_atc, ''), COALESCE(intervalo_horas, -1),
    sentido, motivo, fonte_id);

CREATE INDEX ix_separacao_subst ON regra_separacao (substancia_id);


-- =====================================================================
-- INTERAÇÕES — uma linha por (afirmação, fonte)
-- =====================================================================

CREATE TABLE interacao_substancia (
    id                  INTEGER PRIMARY KEY,
    substancia_a_id     INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    substancia_b_id     INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    tipo                TEXT NOT NULL CHECK (tipo IN
                            ('FARMACOCINETICA','FARMACODINAMICA','FARMACEUTICA',
                             'NAO_DETERMINADO')),
    mecanismo           TEXT,               -- em pt-BR
    efeito_esperado     TEXT,               -- em pt-BR
    descricao_original  TEXT,               -- texto da fonte, preservado
    gravidade           TEXT NOT NULL CHECK (gravidade IN
                            ('MAIOR','MODERADA','MENOR','NAO_DETERMINADA')),
    conduta             TEXT,
    origem              TEXT NOT NULL CHECK (origem IN
                            ('FONTE_EXTERNA','CURADORIA','INFERENCIA_MECANISTICA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    status_revisao      TEXT NOT NULL DEFAULT 'PENDENTE'
                        CHECK (status_revisao IN ('PENDENTE','APROVADO','REJEITADO')),
    -- Par ordenado: A-B e B-A não viram registros diferentes
    CHECK (substancia_a_id < substancia_b_id),
    -- Por FONTE, não por origem: sem isto, DDInter e db_drug_interactions
    -- colidiriam e o conflito de gravidade seria indetectável (P-01).
    UNIQUE (substancia_a_id, substancia_b_id, fonte_id)
);
CREATE INDEX ix_interacao_a ON interacao_substancia (substancia_a_id);
CREATE INDEX ix_interacao_b ON interacao_substancia (substancia_b_id);

CREATE TABLE interacao_item (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    item_id             INTEGER NOT NULL REFERENCES item_nao_medicamentoso(id),
    mecanismo           TEXT,
    efeito_esperado     TEXT,
    descricao_original  TEXT,
    gravidade           TEXT NOT NULL CHECK (gravidade IN
                            ('MAIOR','MODERADA','MENOR','NAO_DETERMINADA')),
    conduta             TEXT,
    origem              TEXT NOT NULL CHECK (origem IN
                            ('FONTE_EXTERNA','CURADORIA','INFERENCIA_MECANISTICA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    status_revisao      TEXT NOT NULL DEFAULT 'PENDENTE'
                        CHECK (status_revisao IN ('PENDENTE','APROVADO','REJEITADO')),
    UNIQUE (substancia_id, item_id, fonte_id)
);
CREATE INDEX ix_inter_item_subst ON interacao_item (substancia_id);

CREATE TABLE interacao_doenca (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    doenca_id           INTEGER NOT NULL REFERENCES doenca(id),
    -- Sem este campo o dado é inútil: "trata" e "é contraindicado em" ficam
    -- indistinguíveis e o alerta sai invertido (DECISIONS.md D-004).
    relacao             TEXT NOT NULL CHECK (relacao IN
                            ('CONTRAINDICADO','USAR_COM_CAUTELA','AJUSTAR_DOSE',
                             'INDICADO','NAO_DETERMINADA')),
    justificativa       TEXT,
    -- Trecho literal que sustenta a relação. Sem ele, uma linha tirada de
    -- texto corrido não pode ser conferida por ninguém.
    trecho_origem       TEXT,
    gravidade           TEXT NOT NULL CHECK (gravidade IN
                            ('MAIOR','MODERADA','MENOR','NAO_DETERMINADA')),
    origem              TEXT NOT NULL CHECK (origem IN
                            ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA',
                             'INFERENCIA_MECANISTICA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    status_revisao      TEXT NOT NULL DEFAULT 'PENDENTE'
                        CHECK (status_revisao IN ('PENDENTE','APROVADO','REJEITADO')),
    UNIQUE (substancia_id, doenca_id, fonte_id)
);
CREATE INDEX ix_inter_doenca_subst ON interacao_doenca (substancia_id);

CREATE TABLE interacao_habito (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    habito              TEXT NOT NULL CHECK (habito IN
                            ('TABAGISMO','ALCOOL','CAFEINA','ENERGETICO')),
    mecanismo           TEXT,
    efeito_esperado     TEXT,
    gravidade           TEXT NOT NULL CHECK (gravidade IN
                            ('MAIOR','MODERADA','MENOR','NAO_DETERMINADA')),
    conduta             TEXT,
    -- A cessação do tabagismo reverte a indução da CYP1A2 em ~1 semana e pode
    -- exigir redução de dose: é alerta próprio, não nota de rodapé.
    alerta_cessacao     TEXT,
    origem              TEXT NOT NULL CHECK (origem IN
                            ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA',
                             'INFERENCIA_MECANISTICA')),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    status_revisao      TEXT NOT NULL DEFAULT 'PENDENTE'
                        CHECK (status_revisao IN ('PENDENTE','APROVADO','REJEITADO')),
    UNIQUE (substancia_id, habito, fonte_id)
);
CREATE INDEX ix_inter_habito_subst ON interacao_habito (substancia_id);

-- Sinal de farmacovigilância (VigiMed). NÃO é relação causal comprovada:
-- notificação espontânea mede notificação, não incidência.
CREATE TABLE substancia_reacao_adversa (
    id                  INTEGER PRIMARY KEY,
    substancia_id       INTEGER NOT NULL REFERENCES substancia(id) ON DELETE CASCADE,
    reacao_id           INTEGER NOT NULL REFERENCES reacao_adversa(id),
    n_notificacoes      INTEGER NOT NULL,
    n_graves            INTEGER NOT NULL DEFAULT 0,
    ror                 REAL,               -- razão de chances de notificação
    ror_ic95_inferior   REAL,               -- só há sinal se o IC não cruzar 1
    sinal_desproporcionalidade INTEGER NOT NULL DEFAULT 0
                        CHECK (sinal_desproporcionalidade IN (0,1)),
    fonte_id            INTEGER NOT NULL REFERENCES fonte(id),
    UNIQUE (substancia_id, reacao_id, fonte_id)
);
CREATE INDEX ix_ram_subst ON substancia_reacao_adversa (substancia_id);


-- =====================================================================
-- CAMADA 2 — PACIENTE E ATENDIMENTO
-- =====================================================================

CREATE TABLE paciente (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL,
    data_nascimento     TEXT,               -- idade é calculada, nunca digitada
    sexo                TEXT CHECK (sexo IN ('F','M','OUTRO','NAO_INFORMADO')),
    peso_kg             REAL CHECK (peso_kg IS NULL OR peso_kg BETWEEN 0.5 AND 400),
    altura_cm           REAL CHECK (altura_cm IS NULL OR altura_cm BETWEEN 30 AND 250),
    contato             TEXT,
    observacao          TEXT,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE paciente_condicao (
    id                  INTEGER PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
    doenca_id           INTEGER REFERENCES doenca(id),
    descricao_livre     TEXT,               -- para "Outra" do checklist
    desde               TEXT,
    CHECK (doenca_id IS NOT NULL OR descricao_livre IS NOT NULL)
);
CREATE INDEX ix_pac_cond ON paciente_condicao (paciente_id);

CREATE TABLE paciente_alergia (
    id                  INTEGER PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
    substancia_id       INTEGER REFERENCES substancia(id),
    descricao_livre     TEXT,
    reacao              TEXT,
    gravidade           TEXT CHECK (gravidade IN
                            ('ANAFILAXIA','GRAVE','MODERADA','LEVE','NAO_INFORMADA')),
    CHECK (substancia_id IS NOT NULL OR descricao_livre IS NOT NULL)
);
CREATE INDEX ix_pac_alergia ON paciente_alergia (paciente_id);

CREATE TABLE paciente_habito (
    id                  INTEGER PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
    habito              TEXT NOT NULL CHECK (habito IN
                            ('TABAGISMO','ALCOOL','CAFEINA','ENERGETICO',
                             'SUPLEMENTO','CHA_PLANTA','AUTOMEDICACAO','MIP_FREQUENTE')),
    situacao            TEXT NOT NULL CHECK (situacao IN
                            ('ATUAL','EX','NUNCA','NAO_INFORMADO')),
    quantidade          TEXT,
    frequencia          TEXT,
    UNIQUE (paciente_id, habito)
);

-- Uma sessão de conciliação: congela o que foi analisado e quando.
CREATE TABLE atendimento (
    id                  INTEGER PRIMARY KEY,
    paciente_id         INTEGER NOT NULL REFERENCES paciente(id),
    codigo              TEXT NOT NULL UNIQUE,
    farmaceutico        TEXT,
    crf                 TEXT,
    iniciado_em         TEXT NOT NULL DEFAULT (datetime('now')),
    concluido_em        TEXT,
    situacao            TEXT NOT NULL DEFAULT 'EM_ANDAMENTO' CHECK (situacao IN
                            ('EM_ANDAMENTO','CONCLUIDO','CANCELADO'))
);
CREATE INDEX ix_atend_paciente ON atendimento (paciente_id);

CREATE TABLE atendimento_medicamento (
    id                  INTEGER PRIMARY KEY,
    atendimento_id      INTEGER NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    substancia_id       INTEGER REFERENCES substancia(id),
    apresentacao_id     INTEGER REFERENCES apresentacao(id),
    nome_relatado       TEXT NOT NULL,      -- o que o paciente disse, preservado
    origem              TEXT NOT NULL CHECK (origem IN
                            ('PRESCRITO','AUTOMEDICACAO','MIP','SUPLEMENTO',
                             'FITOTERAPICO','NAO_INFORMADO')),
    -- QUAL LISTA da conciliação este item integra. Distinto de `origem`, que
    -- diz a natureza do uso: um MIP pode estar na lista relatada e ausente da
    -- prescrição — e é exatamente essa diferença que a conciliação procura.
    -- O mesmo fármaco em duas listas são DUAS linhas; parear as duas é o ato
    -- de conciliar, e o resultado do pareamento fica em `conciliacao_par`.
    lista               TEXT NOT NULL DEFAULT 'RELATADA' CHECK (lista IN
                            ('PRESCRITA',   -- consta da prescrição apresentada
                             'RELATADA',    -- o paciente informou que usa
                             'EM_USO',      -- confirmado em uso no atendimento
                             'HISTORICO',   -- registro de atendimento anterior
                             'ANTERIOR')),  -- uso passado, possivelmente suspenso
    -- Quando não reconhecemos, dizemos que não reconhecemos.
    reconhecimento      TEXT NOT NULL CHECK (reconhecimento IN
                            ('EAN','NOME_EXATO','NOME_APROXIMADO','MANUAL','NAO_RECONHECIDO')),
    confianca_reconhecimento TEXT CHECK (confianca_reconhecimento IN
                            ('ALTA','MEDIA','BAIXA')),
    observacao          TEXT
);
CREATE INDEX ix_atend_med       ON atendimento_medicamento (atendimento_id);
CREATE INDEX ix_atend_med_subst ON atendimento_medicamento (substancia_id);

-- POSOLOGIA ESTRUTURADA — sem isto o motor de horários não tem o que analisar.
CREATE TABLE posologia (
    id                  INTEGER PRIMARY KEY,
    atendimento_medicamento_id INTEGER NOT NULL UNIQUE
                        REFERENCES atendimento_medicamento(id) ON DELETE CASCADE,
    dose_valor          REAL,               -- NULL legítimo: no balcão o paciente
    dose_unidade        TEXT,               -- muitas vezes não sabe a dose
    vezes_por_dia       INTEGER CHECK (vezes_por_dia IS NULL
                                       OR vezes_por_dia BETWEEN 1 AND 12),
    intervalo_horas     REAL CHECK (intervalo_horas IS NULL
                                    OR intervalo_horas BETWEEN 0.5 AND 168),
    via_administracao   TEXT,
    duracao_dias        INTEGER,
    data_inicio         TEXT,
    data_fim_prevista   TEXT,
    uso_continuo        INTEGER NOT NULL DEFAULT 0 CHECK (uso_continuo IN (0,1)),
    se_necessario       INTEGER NOT NULL DEFAULT 0 CHECK (se_necessario IN (0,1)),
    condicao_uso        TEXT,               -- "se dor", "se PA > 14/9"
    texto_original      TEXT,               -- acompanha, não substitui
    CHECK (uso_continuo = 0 OR data_fim_prevista IS NULL)
);

-- Um horário por linha: permite ao motor detectar coadministração.
CREATE TABLE horario_administracao (
    id                  INTEGER PRIMARY KEY,
    posologia_id        INTEGER NOT NULL REFERENCES posologia(id) ON DELETE CASCADE,
    hora                TEXT NOT NULL,      -- 'HH:MM' 24 h
    definido_por        TEXT NOT NULL CHECK (definido_por IN
                            ('PACIENTE','FARMACEUTICO','SUGERIDO_PELO_SISTEMA')),
    UNIQUE (posologia_id, hora),
    -- '[0-2][0-9]' deixaria passar 29:59 (P-03)
    CHECK (hora GLOB '[0-1][0-9]:[0-5][0-9]' OR hora GLOB '2[0-3]:[0-5][0-9]')
);

CREATE TABLE atendimento_item (
    id                  INTEGER PRIMARY KEY,
    atendimento_id      INTEGER NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    item_id             INTEGER REFERENCES item_nao_medicamentoso(id),
    nome_relatado       TEXT NOT NULL,
    frequencia          TEXT CHECK (frequencia IN
                            ('DIARIO','SEMANAL','OCASIONAL','RARO','NAO_INFORMADA')),
    horario_habitual    TEXT
);
CREATE INDEX ix_atend_item ON atendimento_item (atendimento_id);

-- Rotina real do paciente. O motor de horários precisa dela para responder
-- não só "qual é a posologia" mas "como essa posologia cabe no dia desta
-- pessoa": um medicamento em jejum às 06:30 é inviável para quem acorda às
-- 08:00, e "com alimento" às 15:00 não tem refeição por perto.
-- Nada aqui altera prescrição: serve para detectar e mostrar, não para mudar.
CREATE TABLE rotina_paciente (
    id                  INTEGER PRIMARY KEY,
    atendimento_id      INTEGER NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    evento              TEXT NOT NULL CHECK (evento IN (
                            'ACORDAR','DORMIR',
                            'CAFE_MANHA','LANCHE_MANHA','ALMOCO',
                            'LANCHE_TARDE','JANTAR','CEIA',
                            'TRABALHO_INICIO','TRABALHO_FIM',
                            'ESCOLA_INICIO','ESCOLA_FIM','DESLOCAMENTO')),
    hora                TEXT NOT NULL,
    observacao          TEXT,
    UNIQUE (atendimento_id, evento),
    CHECK (hora GLOB '[0-1][0-9]:[0-5][0-9]' OR hora GLOB '2[0-3]:[0-5][0-9]')
);
CREATE INDEX ix_rotina_atend ON rotina_paciente (atendimento_id);

-- Quais eventos da rotina contam como refeição, para o motor não precisar
-- repetir a lista em código.
CREATE VIEW vw_refeicao AS
SELECT * FROM rotina_paciente
WHERE evento IN ('CAFE_MANHA','LANCHE_MANHA','ALMOCO','LANCHE_TARDE',
                 'JANTAR','CEIA');


-- =====================================================================
-- CAMADA 5 — MACHINE LEARNING (separado do fato, sempre)
-- =====================================================================

-- Um modelo nunca é substituído em silêncio: cada treino é uma LINHA NOVA,
-- com semente, versão dos dados e espaço de atributos gravados junto. Sem
-- esses três campos o resultado não é reproduzível por um terceiro, e um
-- modelo não reproduzível não tem como ser auditado depois de publicado.
CREATE TABLE modelo (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL,
    versao              TEXT NOT NULL,
    problema            TEXT NOT NULL,      -- o que o modelo responde
    algoritmo           TEXT NOT NULL,
    n_features          INTEGER NOT NULL,
    protocolo_validacao TEXT NOT NULL,      -- split por fármaco, por par, externo
    metricas_json       TEXT NOT NULL,
    treinado_em         TEXT NOT NULL,
    -- Reprodutibilidade (Fase 7 §22): o que um terceiro precisa para repetir.
    semente             INTEGER NOT NULL,
    versao_dados        TEXT NOT NULL,      -- impressão digital do banco usado
    espaco_features_json TEXT NOT NULL,     -- nomes das colunas, na ordem
    calibrador_json     TEXT,               -- tabela de pontos, nunca pickle
    artefato            TEXT,               -- caminho do arquivo do modelo
    -- EXPERIMENTAL: medido, não exposto ao farmacêutico.
    -- HOMOLOGADO:   liberado para gerar achado PREVISTO.
    -- APOSENTADO:   substituído; a linha fica para rastrear previsões antigas.
    status              TEXT NOT NULL DEFAULT 'EXPERIMENTAL' CHECK (status IN
                            ('EXPERIMENTAL','HOMOLOGADO','APOSENTADO')),
    limitacoes          TEXT NOT NULL,      -- em pt-BR, obrigatório
    -- Probabilidade mínima para uma previsão virar achado. NULL é o padrão e
    -- significa "este modelo não emite alerta nenhum": um modelo homologado
    -- por engano, sem limiar declarado, continua produzindo zero achados.
    -- O limiar é propriedade da VERSÃO do modelo, escolhido na validação, e
    -- fica gravado junto com as métricas que o justificam.
    limiar_alerta       REAL CHECK (limiar_alerta IS NULL
                                    OR limiar_alerta BETWEEN 0 AND 1),
    ativo               INTEGER NOT NULL DEFAULT 0 CHECK (ativo IN (0,1)),
    -- Modelo ativo tem de estar homologado. Ativar um EXPERIMENTAL seria
    -- levar ao balcão algo que o próprio registro diz não estar liberado.
    CHECK (ativo = 0 OR status = 'HOMOLOGADO'),
    UNIQUE (nome, versao)
);
-- No máximo UM modelo ativo por problema. É o que impede a troca silenciosa:
-- publicar outro exige desativar o anterior no mesmo passo, explicitamente.
CREATE UNIQUE INDEX ux_modelo_ativo ON modelo (problema) WHERE ativo = 1;

CREATE TABLE predicao (
    id                  INTEGER PRIMARY KEY,
    modelo_id           INTEGER NOT NULL REFERENCES modelo(id),
    substancia_a_id     INTEGER NOT NULL REFERENCES substancia(id),
    substancia_b_id     INTEGER NOT NULL REFERENCES substancia(id),
    probabilidade       REAL NOT NULL CHECK (probabilidade BETWEEN 0 AND 1),
    probabilidade_calibrada REAL CHECK (probabilidade_calibrada BETWEEN 0 AND 1),
    explicacao_json     TEXT,               -- contribuição aproximada por atributo
    -- O modelo NÃO gradua gravidade. A coluna existe para tornar a regra
    -- explícita e verificável por teste, e é obrigatoriamente NULL.
    gravidade_sugerida  TEXT CHECK (gravidade_sugerida IS NULL),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
    -- Previsão não vira fato por decurso de prazo: nasce NAO_REVISADA e só
    -- muda por ato humano assinado, pela mesma porta da curadoria.
    status              TEXT NOT NULL DEFAULT 'NAO_REVISADA' CHECK (status IN
                            ('NAO_REVISADA','REVISADA_ACEITA','REVISADA_RECUSADA')),
    revisado_por        TEXT,
    CHECK (status = 'NAO_REVISADA' OR revisado_por IS NOT NULL),
    CHECK (substancia_a_id < substancia_b_id),
    UNIQUE (modelo_id, substancia_a_id, substancia_b_id)
);
CREATE INDEX ix_predicao_par ON predicao (substancia_a_id, substancia_b_id);


-- =====================================================================
-- CAMADA 7 — RESULTADO DA CONCILIAÇÃO
-- =====================================================================

CREATE TABLE conciliacao (
    id                  INTEGER PRIMARY KEY,
    atendimento_id      INTEGER NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    executada_em        TEXT NOT NULL DEFAULT (datetime('now')),
    versao_motor        TEXT NOT NULL,
    n_medicamentos      INTEGER NOT NULL,
    n_achados           INTEGER NOT NULL DEFAULT 0,
    -- Resumo estruturado. São contagens derivadas dos achados desta mesma
    -- conciliação; ficam gravadas para que a interface não precise recontar
    -- e para que o número exibido seja o que foi calculado no atendimento.
    n_criticos          INTEGER NOT NULL DEFAULT 0,
    n_altos             INTEGER NOT NULL DEFAULT 0,
    n_moderados         INTEGER NOT NULL DEFAULT 0,
    n_baixos            INTEGER NOT NULL DEFAULT 0,
    n_informativos      INTEGER NOT NULL DEFAULT 0,
    n_divergencias      INTEGER NOT NULL DEFAULT 0,
    n_informacao_insuficiente INTEGER NOT NULL DEFAULT 0,
    n_nao_avaliado      INTEGER NOT NULL DEFAULT 0,
    n_conciliados       INTEGER NOT NULL DEFAULT 0,
    n_nao_conciliados   INTEGER NOT NULL DEFAULT 0,
    requer_revisao_profissional INTEGER NOT NULL DEFAULT 1
                        CHECK (requer_revisao_profissional IN (0,1))
);
CREATE INDEX ix_conc_atend ON conciliacao (atendimento_id);


-- =====================================================================
-- ACHADO — a unidade de saída do sistema.
--
-- Camada intermediária entre os motores especializados e a interface: todo
-- módulo termina aqui, e a interface lê só daqui. Regra clínica nenhuma
-- mora na tela.
--
-- TRÊS EIXOS QUE NÃO PODEM SER FUNDIDOS, porque respondem perguntas
-- diferentes: um achado pode ser grave e pouco confiável ao mesmo tempo.
--
--   gravidade_fonte    o que a FONTE diz sobre o dano possível
--   confianca_sistema  o quanto o SISTEMA confia no que está afirmando
--   prioridade         em que ordem MOSTRAR, combinando os dois com o
--                      contexto do paciente (rules/_prioridade.py)
--
-- E mais três, sobre o estado do conhecimento:
--
--   natureza           epistemologia da AFIRMAÇÃO (documentada? prevista?
--                      conflitante entre fontes?)
--   classificacao      detecção NESTE PACIENTE (o conflito está confirmado,
--                      ou só é possível porque falta dado?)
--   status_informacao  procedência e revisão
-- =====================================================================
CREATE TABLE achado (
    id                  INTEGER PRIMARY KEY,
    conciliacao_id      INTEGER NOT NULL REFERENCES conciliacao(id) ON DELETE CASCADE,

    -- ---------------------------------------------------- que problema é
    -- modulo é o TIPO do achado: qual dos motores o produziu.
    modulo              TEXT NOT NULL CHECK (modulo IN (
                            'FARMACO_FARMACO','FARMACO_DOENCA','FARMACO_ALERGIA',
                            'FARMACO_ALIMENTO','FARMACO_PLANTA','FARMACO_SUPLEMENTO',
                            'FARMACO_HABITO','FARMACO_CYP','DUPLICIDADE',
                            'REACAO_ADVERSA','CONFLITO_HORARIO','REGRA_ADMINISTRACAO',
                            'POSOLOGIA','DIVERGENCIA_CONCILIACAO',
                            'INFORMACAO_INSUFICIENTE','ADESAO')),
    subtipo             TEXT NOT NULL,      -- especialização dentro do módulo

    -- ------------------------------------------------------- os três eixos
    prioridade          TEXT NOT NULL CHECK (prioridade IN
                            ('CRITICO','ALTO','MODERADO','BAIXO','INFORMATIVO')),
    classificacao       TEXT NOT NULL CHECK (classificacao IN
                            ('CONFIRMADO','POSSIVEL','INFORMACAO_INSUFICIENTE',
                             'REGRA_DESCONHECIDA','CONFLITO_ENTRE_FONTES')),
    natureza            TEXT NOT NULL CHECK (natureza IN
                            ('DOCUMENTADO','PROVAVEL','POSSIVEL','PREVISTO',
                             'DESCONHECIDO','CONFLITANTE')),

    -- ------------------------------------------------- os dois lados do par
    item_a              TEXT NOT NULL,
    substancia_a_id     INTEGER REFERENCES substancia(id),
    item_b              TEXT,
    substancia_b_id     INTEGER REFERENCES substancia(id),
    -- O que é o lado B. Uma coluna em vez de cinco quase sempre vazias
    -- (condicao / alergia / alimento / suplemento / planta): a interface
    -- decide o rótulo por aqui, e o nome legível já está em item_b.
    alvo_tipo           TEXT NOT NULL DEFAULT 'NENHUM' CHECK (alvo_tipo IN
                            ('SUBSTANCIA','DOENCA','ALERGIA','ITEM','HABITO',
                             'CLASSE_ATC','ENZIMA','POSOLOGIA','LISTA','NENHUM')),

    -- --------------------------------------------------- conteúdo clínico
    titulo              TEXT NOT NULL,      -- em pt-BR
    mecanismo           TEXT,
    efeito_esperado     TEXT,
    conduta             TEXT,               -- SUGESTÃO; nunca ordem
    descricao_fonte     TEXT,               -- como a fonte descreveu
    explicacao          TEXT NOT NULL,      -- por que o sistema apontou isto

    -- ---------------------------------------------- evidência e confiança
    gravidade_fonte     TEXT CHECK (gravidade_fonte IN
                            ('MAIOR','MODERADA','MENOR','NAO_DETERMINADA')),
    nivel_evidencia     TEXT CHECK (nivel_evidencia IN
                            ('RESPALDADA','LIMITADA','TEORICA','NAO_AVALIADA')),
    confianca_sistema   TEXT NOT NULL CHECK (confianca_sistema IN
                            ('ALTA','MEDIA','BAIXA')),
    confianca_extracao  TEXT NOT NULL CHECK (confianca_extracao IN
                            ('REVISADA','CARGA_DIRETA','EXTRAIDA_AUTOMATICAMENTE',
                             'CALCULADO','NAO_APLICAVEL')),
    -- Fato, ausência e previsão nunca se disfarçam um do outro.
    status_informacao   TEXT NOT NULL CHECK (status_informacao IN
                            ('DOCUMENTADO','EXTRAIDO_AUTOMATICAMENTE','REVISADO',
                             'INFORMACAO_INSUFICIENTE','NAO_DETERMINADO','PREVISTO')),
    -- Preparado para o ML da Fase 7, que ainda não existe.
    origem_achado       TEXT NOT NULL DEFAULT 'REGRA' CHECK (origem_achado IN
                            ('REGRA','MODELO','REGRA_E_MODELO')),
    metodo_deteccao     TEXT NOT NULL,      -- como o motor chegou até aqui
    probabilidade_modelo REAL CHECK (probabilidade_modelo IS NULL
                                     OR probabilidade_modelo BETWEEN 0 AND 1),
    origem_afirmacao    TEXT NOT NULL,      -- tabela.id que sustenta o achado
    fonte               TEXT,
    documento           TEXT,
    trecho              TEXT,
    -- Preenchido só quando duas fontes discordam. O sistema NÃO escolhe uma:
    -- as duas ficam em achado_evidencia e o conflito é declarado aqui.
    conflito_tipo       TEXT CHECK (conflito_tipo IN
                            ('GRAVIDADE','MECANISMO','ORIENTACAO','INTERVALO',
                             'RELACAO_ALIMENTO','CONTRAINDICACAO')),

    -- ------------------------------------------------- contexto e decisão
    contexto_paciente   TEXT,               -- os dados que fizeram isto disparar
    justificativa_prioridade TEXT NOT NULL, -- por que esta prioridade, e não outra
    requer_revisao_profissional INTEGER NOT NULL DEFAULT 1
                        CHECK (requer_revisao_profissional IN (0,1)),

    -- -------------------------------------------------------- agrupamento
    -- Um mesmo problema achado por dois caminhos vira UM achado com duas
    -- evidências, não dois alertas. O absorvido continua na tabela com
    -- status AGRUPADO: reduzir alerta nunca pode apagar evidência.
    grupo_chave         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'PRINCIPAL' CHECK (status IN
                            ('PRINCIPAL','AGRUPADO')),
    agrupado_em         INTEGER REFERENCES achado(id),

    -- Previsão sem probabilidade seria previsão disfarçada de fato.
    CHECK (natureza <> 'PREVISTO' OR probabilidade_modelo IS NOT NULL),
    CHECK (natureza <> 'DOCUMENTADO' OR nivel_evidencia IS NOT NULL),
    -- As duas colunas de previsão andam juntas ou não andam.
    CHECK ((natureza = 'PREVISTO') = (status_informacao = 'PREVISTO')),
    -- Achado de regra não carrega probabilidade de modelo nenhum.
    CHECK (origem_achado <> 'REGRA' OR probabilidade_modelo IS NULL),
    -- E o contrário: achado que é só previsão tem de dizer QUAL previsão o
    -- sustenta. `origem_afirmacao` aponta a linha de `predicao`, de modo que
    -- seja sempre possível voltar do alerta ao modelo, à versão e à semente.
    -- (REGRA_E_MODELO não entra aqui: ali a afirmação é da regra, e o modelo
    -- só acrescenta ordenação — a probabilidade fica na coluna própria.)
    CHECK (natureza <> 'PREVISTO' OR origem_afirmacao LIKE 'predicao.%'),
    -- Achado que veio SÓ do modelo é previsão, e nada mais.
    CHECK (origem_achado <> 'MODELO' OR natureza = 'PREVISTO'),
    -- Previsto exige nível de evidência NÃO_AVALIADA: previsão não tem
    -- evidência documental, e escrever qualquer outro nível ali seria
    -- emprestar a uma estimativa o respaldo de uma publicação.
    CHECK (natureza <> 'PREVISTO'
           OR nivel_evidencia IS NULL OR nivel_evidencia = 'NAO_AVALIADA'),
    -- REVISADO exige que a evidência tenha sido revisada de fato.
    CHECK (status_informacao <> 'REVISADO' OR confianca_extracao = 'REVISADA'),
    -- Conflito declarado exige natureza conflitante, e vice-versa.
    CHECK ((conflito_tipo IS NOT NULL) = (natureza = 'CONFLITANTE')),
    CHECK ((status = 'AGRUPADO') = (agrupado_em IS NOT NULL))
);
CREATE INDEX ix_achado_conc  ON achado (conciliacao_id, prioridade);
CREATE INDEX ix_achado_grupo ON achado (conciliacao_id, grupo_chave);


-- Uma linha por (achado, fonte que o sustenta). É o que permite agrupar sem
-- perder evidência e declarar conflito sem escolher lado.
CREATE TABLE achado_evidencia (
    id                  INTEGER PRIMARY KEY,
    achado_id           INTEGER NOT NULL REFERENCES achado(id) ON DELETE CASCADE,
    papel               TEXT NOT NULL CHECK (papel IN
                            ('PRINCIPAL','CORROBORA','DIVERGE')),
    fonte               TEXT NOT NULL,
    tipo_fonte          TEXT,
    confiabilidade_fonte TEXT,
    documento           TEXT,
    trecho              TEXT,
    origem_afirmacao    TEXT NOT NULL,
    gravidade_declarada TEXT,
    mecanismo           TEXT,
    efeito_esperado     TEXT,
    conduta             TEXT,
    descricao_original  TEXT,
    nivel_evidencia     TEXT,
    metodo_extracao     TEXT,
    confianca_extracao  TEXT,
    UNIQUE (achado_id, fonte, origem_afirmacao)
);
CREATE INDEX ix_achado_ev ON achado_evidencia (achado_id);


-- =====================================================================
-- CONCILIAÇÃO PROPRIAMENTE DITA — o pareamento entre as listas.
--
-- Uma linha por item conciliado ou por divergência. Diferença NÃO é erro:
-- o sistema classifica a SITUAÇÃO (conciliado, divergência, informação
-- insuficiente) e nunca a INTENÇÃO. Dizer que uma diferença foi erro de
-- conciliação é ato clínico com nome e CRF, não saída de script.
-- =====================================================================
CREATE TABLE conciliacao_par (
    id                  INTEGER PRIMARY KEY,
    conciliacao_id      INTEGER NOT NULL REFERENCES conciliacao(id) ON DELETE CASCADE,
    -- ON DELETE CASCADE, e nao a acao padrao: sem isto, remover um
    -- medicamento DEPOIS de analisar era impossivel — a linha de pareamento
    -- ainda apontava para ele e o banco recusava a exclusao. Na pratica o
    -- farmaceutico ficava preso ao primeiro resultado. Encontrado pela
    -- verificacao independente da Fase 6 (eixo 5).
    -- Um pareamento e uma afirmacao sobre DUAS linhas especificas: se uma
    -- deixa de existir, o pareamento perdeu o objeto. O cabecalho da
    -- conciliacao continua, e a tela sempre mostra o recalculo ao vivo.
    item_prescrito_id   INTEGER REFERENCES atendimento_medicamento(id)
                        ON DELETE CASCADE,
    item_relatado_id    INTEGER REFERENCES atendimento_medicamento(id)
                        ON DELETE CASCADE,
    substancia_id       INTEGER REFERENCES substancia(id),
    nome_exibicao       TEXT NOT NULL,
    situacao            TEXT NOT NULL CHECK (situacao IN
                            ('CONCILIADO','DIVERGENCIA','POSSIVEL_DIVERGENCIA',
                             'INFORMACAO_INSUFICIENTE','REVISAO_NECESSARIA')),
    tipo_divergencia    TEXT CHECK (tipo_divergencia IN
                            ('SO_NA_PRESCRICAO','SO_NO_RELATO','DOSE_DIFERENTE',
                             'FREQUENCIA_DIFERENTE','HORARIO_DIFERENTE',
                             'VIA_DIFERENTE','DUPLICIDADE','POSOLOGIA_INSUFICIENTE',
                             'SEM_CORRESPONDENCIA','DESCONTINUADO_EM_USO')),
    valor_prescrito     TEXT,
    valor_relatado      TEXT,
    detalhe             TEXT,
    -- O sistema grava e mantém NAO_DETERMINADA. Só um profissional
    -- identificado pode dizer outra coisa — e o CHECK exige a assinatura.
    intencionalidade    TEXT NOT NULL DEFAULT 'NAO_DETERMINADA'
                        CHECK (intencionalidade IN
                            ('NAO_DETERMINADA','INTENCIONAL','NAO_INTENCIONAL')),
    avaliado_por        TEXT,
    avaliado_em         TEXT,
    CHECK (item_prescrito_id IS NOT NULL OR item_relatado_id IS NOT NULL),
    CHECK (situacao <> 'CONCILIADO' OR tipo_divergencia IS NULL),
    CHECK (intencionalidade = 'NAO_DETERMINADA' OR avaliado_por IS NOT NULL)
);
CREATE INDEX ix_conc_par ON conciliacao_par (conciliacao_id);


-- Ausência de alerta nunca é ausência de risco: tudo que o motor não
-- conseguiu avaliar é declarado aqui e vai ao relatório.
CREATE TABLE nao_avaliado (
    id                  INTEGER PRIMARY KEY,
    conciliacao_id      INTEGER NOT NULL REFERENCES conciliacao(id) ON DELETE CASCADE,
    item                TEXT NOT NULL,
    motivo              TEXT NOT NULL CHECK (motivo IN (
                            'SUBSTANCIA_NAO_RECONHECIDA','SUBSTANCIA_SEM_COBERTURA',
                            'SEM_INTERACAO_CONHECIDA','POSOLOGIA_NAO_INFORMADA',
                            'HORARIO_NAO_INFORMADO','REGRA_SEM_INTERVALO_ESTABELECIDO',
                            'GRAVIDADE_NAO_GRADUADA_NA_FONTE',
                            'CONDICAO_NAO_RECONHECIDA','ALERGIA_NAO_RECONHECIDA',
                            'ITEM_NAO_RECONHECIDO','DOSE_NAO_INFORMADA',
                            'HABITO_NAO_INFORMADO',
                            'SEM_CORRESPONDENCIA_ENTRE_LISTAS',
                            'MODULO_SEM_FONTE_NO_ACERVO',
                            -- Fase 8: o modelo ativo não pontuou este par, ou
                            -- a probabilidade ficou abaixo do limiar. Declarar
                            -- é obrigatório: silêncio do modelo não é o modelo
                            -- dizendo que não há interação.
                            'PAR_NAO_PONTUADO_PELO_MODELO')),
    modulo              TEXT,               -- qual módulo deixou de avaliar
    detalhe             TEXT
);
CREATE INDEX ix_naoaval_conc ON nao_avaliado (conciliacao_id);

CREATE TABLE auditoria_conflito (
    id                  INTEGER PRIMARY KEY,
    tabela_alvo         TEXT NOT NULL,
    id_alvo             INTEGER,
    descricao           TEXT NOT NULL,
    fonte_a             TEXT NOT NULL,
    valor_a             TEXT NOT NULL,
    fonte_b             TEXT NOT NULL,
    valor_b             TEXT NOT NULL,
    decisao             TEXT NOT NULL CHECK (decisao IN
                            ('MANTEM_A','MANTEM_B','MANTEM_AMBOS','NAO_RESOLVIDO')),
    justificativa       TEXT,
    registrado_em       TEXT NOT NULL DEFAULT (datetime('now'))
);
-- O mesmo conflito, detectado de novo, e o mesmo conflito. Sem esta chave,
-- reexecutar o pipeline acrescentava uma copia de cada linha a cada passada.
-- `id_alvo` e anulavel e em SQLite NULL nao colide com NULL, dai o COALESCE.
CREATE UNIQUE INDEX ux_auditoria_conflito ON auditoria_conflito (
    tabela_alvo, COALESCE(id_alvo, -1), descricao,
    fonte_a, valor_a, fonte_b, valor_b);



-- =====================================================================
-- CAMADA 1 — O QUE O PROFISSIONAL REGISTRA (Fase 6)
--
-- O achado e o par de conciliacao sao RECALCULADOS a cada análise: o `id`
-- deles muda, e é assim que tem de ser, porque mudar o dado do paciente
-- precisa mudar o resultado junto. Por isso a anotação humana **não** pode
-- ser presa a esses ids.
--
-- A chave aqui é ESTÁVEL: `achado.grupo_chave` para um achado, e
-- (tipo de divergência + substância) para uma divergência. As duas
-- sobrevivem a uma reanálise, e é o que permite ao farmacêutico revisar,
-- corrigir um dado, reanalisar, e continuar vendo o que já tinha revisado.
--
-- Esta tabela NUNCA altera prioridade, gravidade ou confiança. Ela registra
-- que uma pessoa olhou, quando, e o que escreveu.
-- =====================================================================
CREATE TABLE anotacao_profissional (
    id                  INTEGER PRIMARY KEY,
    atendimento_id      INTEGER NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    alvo                TEXT NOT NULL CHECK (alvo IN ('ACHADO','DIVERGENCIA')),
    chave               TEXT NOT NULL,      -- chave estável, nunca um id de linha
    situacao            TEXT NOT NULL CHECK (situacao IN
                            ('REVISADO','NAO_APLICAVEL')),
    -- Só faz sentido em divergência, e é a única porta pela qual
    -- `conciliacao_par.intencionalidade` sai de NAO_DETERMINADA.
    intencionalidade    TEXT CHECK (intencionalidade IN
                            ('INTENCIONAL','NAO_INTENCIONAL')),
    observacao          TEXT,
    profissional        TEXT NOT NULL,      -- quem assina a leitura
    crf                 TEXT,
    registrado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (atendimento_id, alvo, chave),
    CHECK (intencionalidade IS NULL OR alvo = 'DIVERGENCIA')
);
CREATE INDEX ix_anotacao_atend ON anotacao_profissional (atendimento_id);


-- =====================================================================
-- VIEWS — o que pode chegar ao farmacêutico
-- =====================================================================

CREATE VIEW vw_interacao_liberada AS
SELECT i.*
FROM interacao_substancia i
WHERE i.origem IN ('FONTE_EXTERNA','CURADORIA')
   OR i.status_revisao = 'APROVADO';

-- `origem` diz de ONDE veio a afirmação; `metodo_extracao` diz COMO ela foi
-- lida. Uma bula da ANVISA é fonte regulatória, mas uma regra tirada dela por
-- expressão regular pode ser leitura errada de texto correto. Por isso a
-- confiança combina os dois, e o motor rebaixa a natureza do achado de
-- DOCUMENTADO para POSSIVEL quando a regra ainda não foi revisada.
CREATE VIEW vw_regra_administracao_liberada AS
SELECT r.*,
       CASE WHEN r.status_revisao = 'APROVADO' THEN 'REVISADA'
            WHEN EXISTS (SELECT 1 FROM evidencia e
                          WHERE e.tabela_alvo = 'regra_administracao'
                            AND e.id_alvo = r.id
                            AND e.metodo_extracao IN ('CARGA_DIRETA',
                                                      'CURADORIA_HUMANA'))
                 THEN 'CARGA_DIRETA'
            ELSE 'EXTRAIDA_AUTOMATICAMENTE'
       END AS confianca_extracao
FROM regra_administracao r
WHERE r.origem IN ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA')
   OR r.status_revisao = 'APROVADO';

CREATE VIEW vw_regra_separacao_liberada AS
SELECT r.*,
       CASE WHEN r.intervalo_horas IS NULL
            THEN 'Requer separação — intervalo não estabelecido na fonte'
            ELSE 'Separar por pelo menos ' ||
                 CAST(CAST(r.intervalo_horas AS INTEGER) AS TEXT) || ' hora(s)'
       END AS orientacao_pt,
       CASE WHEN r.status_revisao = 'APROVADO' THEN 'REVISADA'
            WHEN EXISTS (SELECT 1 FROM evidencia e
                          WHERE e.tabela_alvo = 'regra_separacao'
                            AND e.id_alvo = r.id
                            AND e.metodo_extracao IN ('CARGA_DIRETA',
                                                      'CURADORIA_HUMANA'))
                 THEN 'CARGA_DIRETA'
            ELSE 'EXTRAIDA_AUTOMATICAMENTE'
       END AS confianca_extracao
FROM regra_separacao r
WHERE r.origem IN ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA')
   OR r.status_revisao = 'APROVADO';

-- Concordância entre fontes sobre a mesma regra: duas fontes independentes
-- dizendo 'jejum' para o mesmo fármaco é evidência bem mais forte que uma.
CREATE VIEW vw_regra_concordancia AS
SELECT r.substancia_id, s.nome_dcb, r.tipo,
       COUNT(DISTINCT r.fonte_id) AS n_fontes,
       GROUP_CONCAT(DISTINCT f.nome) AS fontes
FROM regra_administracao r
JOIN substancia s ON s.id = r.substancia_id
JOIN fonte f ON f.id = r.fonte_id
GROUP BY r.substancia_id, r.tipo;

-- Pares em que duas fontes discordam da gravidade. Possível apenas porque
-- a unicidade é por fonte (P-01). Alimenta auditoria_conflito.
CREATE VIEW vw_conflito_gravidade AS
SELECT a.substancia_a_id, a.substancia_b_id,
       fa.nome AS fonte_a, a.gravidade AS gravidade_a,
       fb.nome AS fonte_b, b.gravidade AS gravidade_b
FROM interacao_substancia a
JOIN interacao_substancia b
  ON a.substancia_a_id = b.substancia_a_id
 AND a.substancia_b_id = b.substancia_b_id
 AND a.fonte_id < b.fonte_id
JOIN fonte fa ON fa.id = a.fonte_id
JOIN fonte fb ON fb.id = b.fonte_id
WHERE a.gravidade <> b.gravidade
  AND a.gravidade <> 'NAO_DETERMINADA'
  AND b.gravidade <> 'NAO_DETERMINADA';

CREATE VIEW vw_cobertura_substancia AS
SELECT s.id, s.nome_dcb,
       (SELECT COUNT(*) FROM interacao_substancia i
         WHERE i.substancia_a_id = s.id OR i.substancia_b_id = s.id) AS n_interacoes,
       (SELECT COUNT(*) FROM regra_administracao ra
         WHERE ra.substancia_id = s.id)                              AS n_regras_admin,
       (SELECT COUNT(*) FROM papel_farmacocinetico p
         WHERE p.substancia_id = s.id)                               AS n_papeis_pk,
       (SELECT COUNT(*) FROM substancia_reacao_adversa ra
         WHERE ra.substancia_id = s.id)                              AS n_reacoes
FROM substancia s;

-- Rastreabilidade: toda afirmação com sua fonte, carga e documento.
CREATE VIEW vw_rastreabilidade AS
SELECT e.tabela_alvo, e.id_alvo, f.nome AS fonte, f.tipo AS tipo_fonte,
       e.documento, e.nivel_evidencia, e.metodo_extracao,
       c.script, c.documento_origem, c.data_importacao, c.versao
FROM evidencia e
JOIN fonte f ON f.id = e.fonte_id
LEFT JOIN carga c ON c.id = e.carga_id;


-- =====================================================================
-- VIEWS DA FASE 5 — o caminho único até o farmacêutico
--
-- Toda consulta de regra clínica feita pelo motor de conciliação passa por
-- uma destas. Inferência mecanística não revisada não chega ao balcão por
-- nenhuma delas: entra como achado POSSIVEL, rotulado, e por outro caminho.
-- =====================================================================

CREATE VIEW vw_interacao_doenca_liberada AS
SELECT i.*
FROM interacao_doenca i
WHERE i.origem IN ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA')
   OR i.status_revisao = 'APROVADO';

CREATE VIEW vw_interacao_item_liberada AS
SELECT i.*
FROM interacao_item i
WHERE i.origem IN ('FONTE_EXTERNA','CURADORIA')
   OR i.status_revisao = 'APROVADO';

CREATE VIEW vw_interacao_habito_liberada AS
SELECT i.*
FROM interacao_habito i
WHERE i.origem IN ('FONTE_EXTERNA','BULA_ANVISA','CURADORIA')
   OR i.status_revisao = 'APROVADO';

-- O que a interface exibe como alerta: só o representante de cada grupo.
-- O achado absorvido continua na tabela `achado` com status AGRUPADO e
-- suas evidências continuam em `achado_evidencia` — some da lista, nunca
-- do registro.
-- A ÚNICA porta pela qual uma previsão chega ao farmacêutico.
--
-- Quatro travas, todas aqui e nenhuma no código de aplicação:
--   1. o modelo está ATIVO e HOMOLOGADO — experimental não sai do laboratório;
--   2. o modelo declarou `limiar_alerta` — sem limiar, nada passa (fail-closed);
--   3. a probabilidade calibrada atinge esse limiar;
--   4. **o par NÃO tem interação documentada**. Esta é a garantia estrutural
--      de que previsão nunca substitui, contradiz ou duplica evidência: onde
--      há documento, o achado vem do documento e a previsão não aparece.
-- Previsão recusada por um farmacêutico também não volta.
--
-- Consequência desejada: com nenhum modelo ativo, a view devolve zero linhas e
-- o motor se comporta exatamente como antes de existir ML.
CREATE VIEW vw_predicao_liberada AS
SELECT p.id                AS predicao_id,
       p.substancia_a_id, p.substancia_b_id,
       p.probabilidade, p.probabilidade_calibrada,
       COALESCE(p.probabilidade_calibrada, p.probabilidade) AS probabilidade_exibida,
       p.explicacao_json, p.criado_em, p.status AS status_predicao,
       p.revisado_por,
       m.id                AS modelo_id,
       m.nome              AS modelo_nome,
       m.versao            AS modelo_versao,
       m.algoritmo, m.n_features, m.protocolo_validacao,
       m.limiar_alerta, m.limitacoes, m.versao_dados, m.semente
FROM predicao p
JOIN modelo m ON m.id = p.modelo_id
WHERE m.ativo = 1
  AND m.status = 'HOMOLOGADO'
  AND m.limiar_alerta IS NOT NULL
  AND COALESCE(p.probabilidade_calibrada, p.probabilidade) >= m.limiar_alerta
  AND p.status <> 'REVISADA_RECUSADA'
  AND NOT EXISTS (SELECT 1 FROM interacao_substancia i
                   WHERE i.substancia_a_id = p.substancia_a_id
                     AND i.substancia_b_id = p.substancia_b_id);

CREATE VIEW vw_achado_clinico AS
SELECT a.*, c.atendimento_id, at.codigo AS codigo_atendimento,
       p.id AS paciente_id, p.nome AS paciente,
       (SELECT COUNT(*) FROM achado_evidencia e WHERE e.achado_id = a.id)
           AS n_evidencias,
       (SELECT COUNT(*) FROM achado g WHERE g.agrupado_em = a.id)
           AS n_agrupados
FROM achado a
JOIN conciliacao c  ON c.id = a.conciliacao_id
JOIN atendimento at ON at.id = c.atendimento_id
JOIN paciente p     ON p.id = at.paciente_id
WHERE a.status = 'PRINCIPAL';

-- Resumo estruturado por conciliação, para a interface não recontar.
CREATE VIEW vw_conciliacao_resumo AS
SELECT c.id AS conciliacao_id, c.atendimento_id, at.codigo, p.nome AS paciente,
       c.executada_em, c.versao_motor,
       c.n_medicamentos, c.n_achados,
       c.n_criticos, c.n_altos, c.n_moderados, c.n_baixos, c.n_informativos,
       c.n_divergencias, c.n_informacao_insuficiente, c.n_nao_avaliado,
       c.n_conciliados, c.n_nao_conciliados,
       c.requer_revisao_profissional
FROM conciliacao c
JOIN atendimento at ON at.id = c.atendimento_id
JOIN paciente p     ON p.id = at.paciente_id;

-- Divergências de conciliação, com os dois lados lado a lado.
CREATE VIEW vw_divergencia AS
SELECT cp.*, c.atendimento_id,
       amp.nome_relatado AS nome_prescrito,
       amr.nome_relatado AS nome_relatado_paciente
FROM conciliacao_par cp
JOIN conciliacao c ON c.id = cp.conciliacao_id
LEFT JOIN atendimento_medicamento amp ON amp.id = cp.item_prescrito_id
LEFT JOIN atendimento_medicamento amr ON amr.id = cp.item_relatado_id
WHERE cp.situacao <> 'CONCILIADO';
