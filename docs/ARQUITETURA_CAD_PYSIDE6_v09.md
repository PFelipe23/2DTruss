# Arquitetura de edição avançada — POE Treliça v0.9 PySide6

## Separação de responsabilidades

UI PySide6 → comandos `editing.py` (puro) → `Session.update_project` → `poe_truss.model.make_model` → `poe_truss.engine.run_project` → `solver.py` (imutável).

A renderização lê a saída do motor; em uma alteração de dados, a resposta anterior é invalidada. As transformações de zoom, pan e exagero vertical nunca são persistidas como coordenadas de cálculo. O eixo estrutural Y cresce para cima, ao passo que o viewport Qt usa Y para baixo.

## Confiabilidade da topologia

- Uma edição que incorra em nós coincidentes, barras nulas/duplicadas, IDs inexistentes ou nós isolados no modelo não é aplicada.
- Nós soltos criados no editor pertencem a `cad_drafts` e só se tornam nós de cálculo após serem conectados à malha válida.
- Subdivisão elimina barra original e cria dois segmentos; os comprimentos somam o comprimento inicial e a seção é copiada. Identificadores são monotônicos e não reciclados.
- O arquivo JSON é salvo pela rotina atômica da `desktop.bridge`, mantendo dados explícitos e suporte por nó.
- A alteração de topologia invalida resistências externas declaradas, por dependerem de comprimento/arranjo, e força reconfirmação dos travamentos.

## CAD

O CAD é convertido em uma proposta de eixos estruturais, não em verificação ou projeto. O importador exige confirmação humana de escala e agrupamento por camada. `model_override` deve ser confirmado antes de qualquer análise; nenhum apoio é inventado. Ao substituir a malha, carregamentos geograficamente vinculados à geometria antiga e combinações são removidos; pesos próprios são mantidos/recriados, e os apoios tornam-se vazios. A partir daí, o usuário deve reconstituir condições de contorno.

O modo DWG exige conversor ODA externo instalado. Se indisponível, o aplicativo recusa e indica a alternativa DXF.

## Matriz de testes

| Área | Abordagem | Nível de validação |
|---|---|---|
| Motor Python 2D | testes de regressão do projeto anterior | Executados |
| Edição de topologia | comandos puros, massa/conectividade/IDs | Executados |
| Importação DXF | ezdxf, unidades, tolerâncias, grupos, entidades ignoradas | Executados |
| CAD → apoios → carga → cálculo → JSON → reabertura | teste de integração | Executado |
| Interface PySide6 | sintaxe Python e inspeção estática | Executados, sem runtime Qt |
| Conversão DWG via ODA | exige instalação local e fixtures reais | Pendente |
| Build `.exe` no Windows | requer ambiente Windows com PySide6/PyInstaller | Pendente |
| Solver vs FTool | validação comparativa externa | Pendente |

## Auditoria Codex

1. Instalar dependências em ambiente de teste (somente por usuário), abrir janela PySide6 e verificar interação em monitores 1366×768, 1600×900 e HiDPI.
2. Testar seleção múltipla, criação/remoção, snapping, subdivisão e Undo/Redo.
3. Testar DXF de CAD real de fabricantes e do AutoCAD, com unidades e blocos; verificar exclusão de elementos de anotação.
4. Testar ODA com DWG real no Windows e comparar topologia com DXF do mesmo modelo.
5. Validar modelos importados com FTool, confrontando axial, deslocamentos e reações.
6. Confirmar que nenhum modo de interface concede aprovação ELU normativa ou travamento fora do plano sem evidência.
