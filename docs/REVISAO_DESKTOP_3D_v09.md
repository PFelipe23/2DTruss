# POE Treliça v0.9 — Revisão integradora da UI + inspeção 3D

## Contrato de entrega

A identificação principal permanece **v0.9**. O aplicativo de inicialização é `POE_Trelica.pyw`; o solver axial não foi reescrito. Não utiliza navegador na edição desktop. Implementação incremental sobre a edição PySide6/CAD fornecida anteriormente.

### Modificações e destinos

| Função | Arquivo | Estado |
|---|---|---|
| Edição de grupos de perfis e quantidade de componentes | `desktop/workflow.py`, `desktop/qt/workflow_panels.py` | Código integrado, testado no núcleo |
| Registro de telha/fabricante/massa e passo das terças | mesmos módulos | Dados declarados; sem capacidade de fabricante certificada |
| Casos de carga de superfície, linha, vento e peso próprio | mesmos módulos | Interface integrada ao motor existente; conversão e auditoria de carga testadas |
| Criação de combinações e fatores assinados | mesmos módulos | Implementada; sem combinações normativas automáticas |
| Comprimentos destravados e orientação dos perfis por grupo | mesmos módulos | Declaração de hipótese; não verifica contraventamentos |
| Diagnóstico e localização de barras | mesmos módulos | Implementados; não substituem validação FEM |
| Até 3 sugestões e entrada manual de geometria | `workflow_panels.py` | Pesquisa em thread para não travar Qt; ELS/geometria, sem ELU |
| Envoltórias por tração/compressão | `desktop/qt/app.py` | Modo de inspeção na tabela de resultados |
| Snapping por extremidade, ponto médio e grade | `desktop/qt/viewport.py` | Implementado |
| Popup 3D com rotação, zoom, seleção e alteração de cores por grupos, famílias e sinal | `desktop/qt/view3d.py`, `desktop/preview3d.py` | Código integrado, projeção matemática testada; execução PySide6 não homologada |

## Filosofia de cálculo

- A geometria base é XY. O solver tem 2 graus de liberdade translacionais por nó, barras axialmente articuladas e não resolve esforços fora do plano.
- O 3D é **representação tridimensional ilustrativa** de barras por prismas. O uso de material/colorização não implica verificações de seções reais.
- O objeto `roofing` e as ações de tela exigem dados definidos pelo projetista. O editor de telha não presume informações comerciais normativas nem dimensiona telhas e terças.
- A massa superficial de telha declarada (kg/m²) gera a ação de mesmo valor nominal em kgf/m², coerente com a convenção interna de 10 N/kgf.
- Caso/combinação, perfil, geometria ou travamentos modificados derrubam os resultados anteriores, exigindo recálculo. A janela 3D atualiza a geometria independentemente do solver.
- A pesquisa de modulação usa o módulo Python existente `poe_truss.search`; mostra 3 candidatos, preservando liberdade para inserir altura/painéis manualmente.

## Procedimento de QA (auditoria independente)

1. Executar `python -m pytest -q` na raiz do projeto.
2. Executar `python -m compileall -q desktop poe_truss`.
3. Validar em Windows real, com PySide6 disponível:
   - Abrir `INICIAR_DESKTOP.bat` sem elevação administrativa.
   - Alterar geometria; confirmar atualização do viewport e resultado antigo invalidado.
   - Alterar telha (dados manuais), caso de vento e combinação assinada; conferir auditoria das forças nodais.
   - Mudar perfil por grupo; conferir recalculo do peso próprio e da área.
   - Definir lateral destravado; conferir estado declarado e pendências.
   - Calcular; filtrar envelope de tração/compressão e abrir CSV DimPerfil.
   - Abrir vista 3D, girar, aplicar cor por grupo/família/esforço, fechar e reabrir.
   - Importar DXF de linhas analíticas e confirmar apoios/cargas em modelo explícito.
   - Verificar Windows HiDPI, diferentes tamanhos de janela e políticas de antivírus.
4. Repetir benchmarks analíticos e comparar com arquivos/resultados efetivamente gerados pelo FTool. **Ainda pendente.**

## Resultados realizados no ambiente de desenvolvimento

- Testes puros do Python passam (inclusive conversões, ações, combos, travamentos, CAD, geometria prismática e projeção).
- Compilação AST/bytecode dos arquivos Python concluída.
- PySide6 indisponível no ambiente e instalação sem rede; portanto **não foi possível validar interações nativas Qt**, e o ZIP não deve ser anunciado como executável Windows homologado.
- DWG via ODA continua recurso dependente de instalação externa e de validação com arquivos de usuário.

## Pendências técnicas para dimensionamento executivo

- ELU pela NBR 14762 para tração, compressão global, local, distorcional e flexo-torcional; seções compostas e ligações.
- Capacidade real do sistema de travamentos fora do plano e imperfeições.
- Associação automática de superfícies aos elementos em CAD livre, para ações distribuídas sem edição nodal.
- Verificação de carregamentos/combinações com coeficientes normativos atualizados e rastreáveis.
- Bancada FTool e validação gráfica Windows.

**Classificação da entrega:** edição integrada v0.9 para avaliação e desenvolvimento, NÃO software de projeto estrutural homologado.
