# POE Treliça Python — Auditoria de código e revisão crítica da interface

**Build:** v0.9.1 (sobre a v0.9.0 beta)  
**Data:** 11/11/2026  
**Escopo auditado:** motor Python da v0.9, servidor HTTP local, contratos JSON, interface HTML/CSS/JS, testes e exportações; **sem alterações nos procedimentos de resistência**.

## 1. Síntese executiva

Esta revisão buscou reduzir erros de interação e de identificação de resultados, e não aumentar o número de módulos estruturais. A v0.9 tinha cálculo centralizado em Python, mas o formulário e o diagrama eram excessivamente acoplados ao último resultado. Alterar dimensões sem recalcular podia manter esforços visíveis de uma topologia anterior. A v0.9.1 acrescenta `POST /api/preview`, que executa apenas geometria, diagnóstico e ações nodais — **nunca análise FEM nem verificação resistente**. A interface marca a prévia e bloqueia a exportação de resultados desatualizados.

A **v0.9.1 não está validada para dimensionamento executivo**. Nenhuma modificação gráfica corresponde a um avanço normativo. Os exemplos FTool continuam sem confronto externo real.

## 2. Mudanças comprovadas e critérios de aceitação

| Área | Diagnóstico da v0.9 | Correção na v0.9.1 | Evidência |
|---|---|---|---|
| Estrutura | Página longa com múltiplos cartões | Workspace de 1 viewport no desktop, tarefas laterais fixas e subtelas | Chromium 1600×900: `body.scrollHeight=900`, `innerHeight=900` |
| Campos | Troca de tela podia descartar edições locais | Commit transacional de ações e fatores ao navegar/calcular/salvar | Smoke browser; inspeção dos handlers |
| Geometria | Atualizava visualização somente após FEM | Prévia isolada, com debounce e descarte de respostas antigas | `test_preview_geometry_responds_to_user_height` |
| Resultados antigos | Sem distinção suficiente quando geometria mudava | Status de modelo desatualizado, prévia sem esforço, tabela bloqueada e exportação recusada | Smoke Chromium + `exportKind` |
| Texto axial | 9,5 px, horizontal, sobreposição | 12 px, acompanhando o ângulo da barra, rotação corrigida para leitura e modo automático anticolisão | Captura `UI_v0.9.1_geometria.png` |
| Sugestões | Lista extensa | No máximo 3; comando independente "Calcular parâmetros atuais" | Interface e teste opcional |
| Carregamentos | Setas sem magnitude, muitos campos irrelevantes | Setas com módulos, resultantes ΣFx/ΣFy, campos condicionais, casos selecionáveis | Captura `UI_v0.9.1_cargas.png` |
| Exportação CSV | Possibilidade de célula interpretada como fórmula | Prefixo de neutralização em textos iniciados com `=`, `+`, `@`, `-` não numérico | `test_formula_injection_is_neutralized` |
| Segurança local | Host, token e Origin já eram checados | Mantidos; CSP ampliada, `X-Frame-Options`, `Referrer-Policy`, `Cross-Origin-Resource-Policy` | `test_security_headers` |
| Validação | Testes unitários anteriores | 82 testes cumulativos, 89% de cobertura de linhas no Python | `python -m coverage report -m` |

## 3. Semântica da atualização dinâmica

- **Mudou a geometria?** A prévia chama `make_model`; mostra barras, nós e apoios segundo os parâmetros atuais, sem inventar esforços.
- **Mudou um caso?** O motor de carregamentos transforma as parcelas em componentes nodais, com o mesmo algoritmo utilizado pela análise. A prévia mostra setas com módulos e o somatório dos vetores por caso.
- **Clicou Calcular?** Somente então o motor completo recalcula cargas, deslocamentos, reações, esforços, envoltórias e as triagens já existentes. O status passa a `Análise atualizada`.
- **Mudou novamente?** O programa marca a análise anterior como obsoleta e impede exportação sem novo cálculo. A saída de análise não é sobrescrita pela prévia.
- **Mudou os apoios?** Dados no modelo de projeto, sem alterar `result.model` do cálculo anterior.

A prévia não é prova de equilíbrio do sistema nem validação ELU.

## 4. Revisão crítica de UX

### Problemas resolvidos nesta iteração

1. **Sobrecarga cognitiva:** um só painel de edição fica visível em Geometria, Estabilidade e Triagem; os demais ficam em subtelas. Na navegação lateral, cada tarefa tem um destino fixo.
2. **Ajustes cegos:** a forma muda automaticamente ao editar vão, altura, quantidade de painéis, tipologia ou perfil, inclusive com escala vertical editável.
3. **Ambiguidade numérica:** gráficos de esforços trazem texto inclinado segundo a barra. O modo de anticolisão seleciona subconjunto de rótulos legíveis e permite exibir todos sob demanda; **não filtra os resultados subjacentes**.
4. **Erros de contexto:** a vista de cargas não usa indevidamente cores de tração/compressão. Há distinção de fontes de dados: `prévia de ações` e `resultado do solver`.
5. **Adoção de alternativas:** sugestões são opcionais; valores manuais, inclusive fora das 3 recomendações, são aceitos pelo modelo sujeito à validação geométrica.

### Limitações que permanecem (em ordem de prioridade)

**P0 — Clareza operacional das ações.** A entrada nodal ainda utiliza JSON para casos complexos. Substituir por editor tabular de linhas (`Nó, Fx, Fy, unidade`) com validação in-line e seleção gráfica de nós. Adicionar filtro visual por zonas de cobertura e distinção entre valores por área projetada e por superfície real.

**P0 — Verificação física externa.** Comparação com FTool deve permanecer requisito impeditivo para o uso do solver em decisões de projeto; 100% de cobertura de testes do arquivo do solver não prova equivalência externa.

**P1 — Resultados de barras.** Criar busca por grupo, aproveitamento, compressão, tração, comprimento e combinação governante. Modo de foco na barra selecionada com painel de detalhes sempre visível e histórico de alterações.

**P1 — Notificações e erros.** Substituir temporariamente o aviso global por uma fila de notificações e estados associados a cada campo. Mostrar conflito entre apoios e geometria na própria aba correspondente.

**P1 — Editor de combinações.** Oferecer matriz tabular com casos nas colunas, combinações nas linhas, fatores assinados e verificação de dados incompletos; sinalização explícita de combinações não normativas.

**P2 — Navegação no desenho.** Acrescentar zoom por roda e pan com limites, opção de enquadramento, seleção por retângulo e marcação geométrica das terças/travamentos; evitar que alterações da visualização mudem o modelo.

**P2 — Tela pequena.** Abaixo de 960 px foi priorizada acessibilidade e continuidade dos campos; nesse cenário o programa permite rolagem da página. A exigência de zero scroll é atendida apenas no desktop em viewport suficiente. Mesmo no desktop, tabelas extensas e campos JSON podem exigir rolagem **interna**, porque eliminar todos os mecanismos de rolagem ocultaria informações necessárias.

**P3 — Acessibilidade.** Navegação por teclado da seleção de barras, rótulos/atalhos de unidades, contraste e identificação de esforços também por sinal/legenda (não apenas por cor).

## 5. Segurança / sanitização

**Superfícies avaliadas:** imports JSON, respostas de servidor, renderização do SVG e DOM, exportação de CSV, autenticação HTTP local, parâmetros de cálculo e formulários.

- O servidor permanece limitado a `127.0.0.1`, exige Host correto, restringe Origin e exige token aleatório para POST.
- `GET /bootstrap.js` exige Referer local; não dispensa a proteção de Host/Origin/token dos endpoints de escrita.
- O front-end escapa texto inserido em HTML; não usa `eval` ou construção de funções a partir de entradas. Rótulos SVG usam `textContent`.
- As conversões geométricas rejeitam entrada obrigatória vazia, NaN, infinito, valores negativos inválidos, painéis fora da faixa e intervalos angulares invertidos.
- Novos valores de casos e combinações são validados antes de persistir, evitando alterações parciais.
- CSV de auditoria neutraliza textos potencialmente interpretados como fórmulas por planilhas.
- O arquivo de projeto selecionado na interface é limitado a 2 MB; o servidor mantém o limite de POST de 1 MB.

**Não foi realizada auditoria independente de segurança por terceiros nem fuzzing amplo.** O saneamento reduz riscos identificados, não certifica segurança absoluta de qualquer arquivo arbitrário.

## 6. Validação executada

Comandos:

```text
python -m compileall -q poe_truss tests
python -m unittest discover -s tests -q
python -m coverage run --source=poe_truss -m unittest discover -s tests -q
python -m coverage report -m
node --check web/app.js
python tests/browser_ui_v091_smoke.py  # opcional, requer Playwright/Chromium
```

Resultados da execução atual: **82/82 testes Python aprovados**, cobertura **89% de linhas** no conjunto de módulos `poe_truss`, `solver.py` com 100% das linhas exercitadas pelos testes. O Chromium foi executado em `page.set_content` com ponte Python para as mesmas funções reais, devido ao bloqueio de navegação loopback pelo ambiente. Foram exercitados: inicialização, alteração ao vivo, nova análise, casos de carga, seleção de tarefas e subtelas. Não ocorreram exceções JavaScript.

Não houve execução nativa do aplicativo em Windows nesta bancada, nem comparação com resultados gerados no FTool.

## 7. Conclusão

A maior melhoria da v0.9.1 é separar claramente **geometria e distribuição de ações**, **resultado FEM vigente** e **verificação resistente não implementada**. A próxima evolução deve concentrar-se no editor visual de cargas nodais, identificação das envoltórias por combinação e validação FTool — antes de expandir outros módulos resistentes.
