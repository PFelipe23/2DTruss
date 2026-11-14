# POE Treliça — Revisão de arquitetura e UX (linha consolidada v0.9)

## Escopo efetivamente implementado

A implementação mantém o **motor FEM 2D em Python**, sem alterações nas
matrizes de rigidez e na análise normativa. A interface foi dividida em
módulos ES nativos, carregados localmente pelo servidor Python:

| Arquivo | Responsabilidade |
|---|---|
| `web/app.js` | Orquestração de tarefas, modelo, serviços HTTP e estados de análise |
| `web/modules/nodal.js` | Editor de cargas nodais por linha, unidades e atribuição de nó |
| `web/modules/diagram.js` | Representação SVG e identificação visual de ações/esforços |
| `web/modules/results.js` | Filtros de barras, ordenação e tabela de envoltórias |
| `poe_truss/server.py` | Rotas locais, autenticação e entrega restrita dos recursos |

O contrato JSON do projeto permanece `poe-truss-python/v1` e cargas nodais
continuam no formato `load_cases[].loads[]` com chaves `node`, `fx`, `fy`,
`force_unit`. As alterações de interface **não modificam** a interpretação
física das ações.

## 1 — Editor de cargas nodais

Cada linha permite escolher nó, Fx, Fy e unidade (kgf, tf, kN). É possível
adicionar e excluir linhas, selecionar a linha ativa e associar o nó clicando
no desenho da treliça. A conversão nominal obrigatória permanece
`1 tf = 1.000 kgf = 10 kN`.

Erros de seleção de nó, campos numéricos inválidos e forças inteiramente
nulas são recusados antes de transferir a edição ao modelo. O programa não
salva esse tipo de entrada como um JSON incorreto; os dados são serializados
no mesmo esquema do motor atual.

**Observação:** ao criar um novo caso nodal, é necessário informar uma carga
não nula antes de calcular. Durante a digitação parcial a prévia pode ficar
indisponível, sem substituir o último resultado aprovado.

## 2 — Resultados filtráveis

A tela de resultados exibe inicialmente as 10 maiores demandas absolutas de
envoltória e oferece filtros por grupo, compressão/tração no caso exibido,
combinação governante, busca por ID ou perfil e ordenação. Os sinais são
preservados. Os valores governantes são aqueles efetivamente calculados para
as combinações disponíveis, sem inferir qualquer ELU normativo.

A tabela compacta exibe barra, N do caso, N mínimo comprimido, N máximo
tracionado e seus IDs governantes. Os dados geométricos e de perfil completos
ficam no inspetor após selecionar a barra, sem exigir rolagem horizontal.

## 3 — Arquitetura de interface

A aplicação permanece offline, sem CDN ou dependências JS de terceiros.
Não se utiliza `eval`, importação dinâmica de fontes externas nem rotas de
arquivos arbitrários. O servidor responde exclusivamente aos módulos
explicitamente permitidos.

A prévia responde a edições de geometria e ações e **não executa análise FEM**;
o último resultado passa a condição de desatualizado até um novo cálculo.
O servidor continua restrito ao endereço `127.0.0.1` e às proteções HTTP
preexistentes.

## Verificações

- `python -m unittest discover -s tests -v`: testes Python do motor + testes
  adicionais do contrato nodal e serviço de módulos.
- `python tests/browser_ui_v09_inmemory.py`: teste opcional com Playwright,
  realizando importação ES nativa a partir de `data:` URLs no ambiente de
  bancada. Cobre edição, clique em nós, cálculo, inspeção e filtros.
- `node --check web/app.js` e arquivos de `web/modules/`: sintaxe JS.
- Resolução do smoke: 1600 × 900; corpo sem rolagem global.

**Limitações verificáveis:** o Chromium da bancada bloqueou a navegação ao
servidor real (`ERR_BLOCKED_BY_ADMINISTRATOR`), por isso a interação foi
testada com HTML em memória e uma ponte ao motor Python. A entrega deve ser
confirmada na execução real em Windows. A execução FTool permanece pendente.

## Riscos técnicos que persistem

1. A resistência axial segundo NBR 14762 não está totalmente implementada.
2. As condições de travamento fora do plano são hipóteses declaradas, não
   análise tridimensional nem comprovação do sistema estabilizante.
3. A validação independente do solver 2D com o FTool não foi concluída.
4. Combinações normativas automáticas não estão disponíveis.
5. A interface desktop evita rolagem **global**; tabelas e formulários
   extensos podem rolar dentro dos seus próprios painéis.

Essas lacunas não são corrigidas por refatoração de interface.
