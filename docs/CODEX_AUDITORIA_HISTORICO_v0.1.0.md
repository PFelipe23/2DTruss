# Instruções objetivas para auditoria Codex — POE Treliça Python v0.1.0

**Auditar o software real deste pacote. Não refazer o programa do zero antes de identificar divergências quantitativas.**

## Contrato numérico

- Internamente N, mm, MPa; conversão nominal de projeto: 1 kgf = 10 N, 1 tf = 10 kN.
- Elemento de treliça 2D sem rotação nodal; deslocamentos UX/UY; tração N positiva.
- Posição de apoios por ID de nó, não por índice implícito; mapeamento de GDL em `solver.py`.
- Cargas uniformes de superfície por projeção (dx) ou área inclinada (ds), multiplicadas pela distância entre pórticos; metade do trecho atribuída a cada nó adjacente. Vento normal usa vetor (-dy/ds, dx/ds) para normal exterior.
- G1 = 10 N/kg × massa total das barras, metade por extremidade de cada barra.
- Envoltória: mín. compressão e máx. tração de **combinações completas** definidas pelo usuário, sem somar extremos de combinações diferentes.

## Ordem obrigatória

1. Executar `python -m unittest discover -s tests -v`. Guardar log e hash do código.
2. Executar o caso `FTool_A02_trelica_triangular.json` pela CLI e comparar com fórmulas fechadas e valores de `FTool_GUIA.md`.
3. Inspecionar tratamento de singularidades e suportes X/Y/XY, permutação de nós, mudança de orientação de barras e consistência global.
4. Verificar cargas de telhas/purlins/forro com base horizontal versus superfícies inclinadas em modelos com diferentes inclinações.
5. Rodar exemplos nos modos Pratt, Howe, Warren e nos quatro formatos de banzos; apresentar índices de equilíbrio.
6. Confrontar com FTool **apenas se tiver acesso real ao FTool** e aos modelos equivalentes. Não gerar referências sintéticas e chamá-las de FTool.
7. Testar persistência JSON, status de erros API, token e restrição local. Validar `INICIAR.bat` em Windows antes de afirmar compatibilidade Windows comprovada.
8. Relatar falhas e divergências com reproduções mínimas, valor POE, valor FTool/analítico, erro absoluto/relativo e hipótese causal.

## Critérios de aceitação

- N e R: 0,10% ou 0,01 kN (o maior limite).
- UX/UY: 0,50% ou 0,02 mm (o maior limite).
- Equilíbrio: resíduos numéricos controlados e invariância de unidades N/mm/MPa.
- Nunca aprovar automaticamente verificações ELU, ELS normativas ou comportamento 3D a partir deste teste do solver.

## Recursos disponíveis

- `poe_truss/model.py`: malha e modelagem por grupos.
- `poe_truss/loads.py`: ações e transformação nodal.
- `poe_truss/solver.py`: matriz global, LU e reações.
- `poe_truss/engine.py`: casos, combinações, envoltória.
- `poe_truss/search.py`: busca preliminar de geometria e flecha, sem resistência.
- `poe_truss/migrate.py`: migração assistida de JSON v0.5, sem duplicação silenciosa do peso próprio.
- `poe_truss/cli.py`: geração e confronto dos benchmarks.
- Os modelos de referência continuam em `examples/`. O [guia do FTool](../FTool_GUIA.md) gera as tabelas em `output/`.
- `tests/test_engine.py`: cálculo analítico e regressões.
- `tests/test_http.py`: servidor local.
- `tests/browser_ui_v09_inmemory.py`: teste opcional de UI com dados reais pré-calculados e fetch simulado, para bancada com Chromium bloqueado.

## Entregáveis esperados do Codex

1. `AUDITORIA_NUMERICA.md`: formulação e riscos de modelagem, incluindo histórico de mudanças.
2. `TEST_MATRIX.csv`: casuística, tolerâncias, estado, origem do resultado de referência, versão FTool.
3. `RESULTADOS_ANALITICOS.json`: resultados de benchmarks analíticos e status.
4. `RESULTADOS_FTOOL.json`: apenas após testes externos executados e evidenciados.
5. Testes de regressão adicionais antes de qualquer alteração no motor.
6. Recomendações para a evolução estrutural (pórtico 2D, ligações, local de cargas, otimização e DimPerfil).

**Não modificar as fontes de catálogo sem procedência rastreável. Não confundir verificação de equilíbrio com validação de resistência.**
