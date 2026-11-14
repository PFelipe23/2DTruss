# POE Treliça v0.9 Desktop — Contrato de arquitetura

## Componentes

- `desktop/app.py`: estado da interface, ribbon, painel lateral, diálogo de cargas, filtros, edição e comando de exportação.
- `desktop/viewport.py`: somente desenho 2D e transformação geométrica. Eventos de mouse selecionam nós/barras e propõem deslocamentos. **Sem resolução estrutural**.
- `desktop/bridge.py`: fachada auditável para `make_model`, `run_project`, cargas nodais e serialização JSON.
- `poe_truss/solver.py`: **inalterado** em relação ao pacote v0.9 anterior (SHA-256 comparável).
- `poe_truss/model.py`: acrescentada leitura/validação opcional de `node_edits`; todos os modelos anteriores continuam compatíveis.

## Estado e invariantes

1. Projeto canônico em `Session.project` (schema `poe-truss-python/v1`).
2. `Session.model` é regenerado pela função Python existente; nenhum modelo de cálculo paralelo é criado na UI.
3. `Session.result` é invalidado sempre que mutação ocorre. O viewport sinaliza explicitamente **NÃO CALCULADO**.
4. `Session.calculate()` executa a mesma análise numérica e calcula os casos/combinações; nunca usa valores do desenho como resultados.
5. Alterar um nó preserva o ID, sua conectividade e as cargas; são aceitos somente nós existentes com coordenadas finitas, x crescente entre painéis, e distância vertical entre banzos de pelo menos 50 mm.
6. Arquivos salvos são gravados atomicamente pelo aplicativo usando arquivo temporário e substituição.
7. Visualização ampliada e deslocada representa exclusivamente uma transformação de viewport.
8. Diagramas têm sinais de tração e compressão por barra; não são apresentados como aprovação resistente.

## Recursos implementados

- Ribbon por tarefas, navegador fixo do modelo, inspector lateral e barra de status.
- Viewer 2D Canvas com zoom, pan, ajustar, seleção, destaque e exagero vertical gráfico.
- Alteração de posição dos nós arrastando com modo de edição, ou digitando X/Y.
- Alteração de restrições UX e UY de nós arbitrários.
- Cadastro de forças nodais por caso + edição de pressão superficial e vento por caso.
- Seleção de casos/combinações, cálculo, cores axiais, rótulos rotacionados, filtros e exportação.
- Desfazer/refazer com cópias do projeto, até 40 alterações; aviso antes de perder mudanças.

## Dívida técnica remanescente

- Editor de topologia livre requer gerador de conectividade, validações de mecanismos e regras de distribuição de carga; não implementar apenas com manipulação Canvas.
- Seleção múltipla, snapping, cotas, grade física calibrada, camadas e comandos CAD ainda pendentes.
- Seleção de perfis duplos pelo catálogo não verifica solidarização nem flexo-torção.
- Construção de `.exe` Windows self-contained está preparada via script de build, mas não está validada. Empacotar em Windows e verificar arquivo ZIP, antivirus corporativo e fontes.
- UI com Tkinter é uma base leve sem bibliotecas externas; caso seja necessária ferramenta CAD maior, avaliar `PySide6/QGraphicsScene`, preservando a fachada `desktop/bridge.py` e o motor atual.

## Auditoria recomendada para Codex

1. Executar testes herdados e específicos. Comparar hash `solver.py` e resultados de três modelos (triangular, Pratt, sucção).
2. Abrir exemplos legados v0.9, editar nó superior, confirmar auditoria do carregamento superficial.
3. Confirmar que editar cargas/apoios/perfis invalida a análise anterior e bloqueia exportação.
4. Testar casos nodais com sinais, unidades e combinação negativa; confrontar com solver e FTool de forma independente.
5. Testar interatividade em 1366×768, 1600×900, 1920×1080 e monitores HiDPI Windows.
6. Verificar compatibilidade com Windows 10/11, sem admin e com execução de `.pyw`/binário eventual.
7. Validar algoritmos normativos apenas em desenvolvimento posterior, com casos independentes.
