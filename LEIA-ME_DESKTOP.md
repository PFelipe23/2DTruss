# 2DTruss v0.1 — Desktop PySide6

**Aplicação nativa sem navegador**: `2DTruss.pyw` abre `QMainWindow` / `QGraphicsView`, com ribbon e painéis de navegação. O solver de treliça plana permanece em `poe_truss/solver.py`.

## Execução no Windows, sem privilégios administrativos

1. Ter **Python 3.10+** instalado no perfil do usuário (com `py -3` disponível).
2. Executar **`INSTALAR_DEPENDENCIAS_USUARIO.bat`** uma vez: instala PySide6 e ezdxf no perfil do usuário, sem elevar privilégios. A instalação requer acesso ao repositório de pacotes e pode ser bloqueada por políticas corporativas.
3. Executar **`INICIAR_DESKTOP.bat`**. Não inicia servidor HTTP ou navegador.
4. Use o procedimento abaixo para gerar um diretório executável com PyInstaller.

Em Linux com dependências instaladas: `python3 2DTruss.pyw`.

## Gerar o executável Windows

Na raiz do repositório, use Python 3.12 de 64 bits em um ambiente virtual. Um Prompt de Comando comum é suficiente.

```bat
py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements-build.txt
call BUILD_EXE_WINDOWS.bat
```

Extraia ou copie a pasta inteira `dist\2DTruss_v0.1` e abra `2DTruss_v0.1.exe`. A pasta `_internal` contém Python, Qt, o catálogo e os exemplos incluídos. O aplicativo empacotado roda sem instalação separada de Python. A importação DWG continua dependendo do conversor ODA local.

Para verificar o pacote pelo Prompt de Comando, execute `start /wait "" "dist\2DTruss_v0.1\2DTruss_v0.1.exe" --smoke-test`. O código de saída 0 confirma a abertura do aplicativo, o cálculo do exemplo, a vista 3D, a importação do DXF de teste, a leitura e gravação JSON e a limpeza da análise ao iniciar outro projeto.

## Interface e atalhos

- Ribbon: Arquivo, Modelagem, Ações, Análise e Exibição, incluindo comando Vista 3D.
- Viewport 2D QGraphicsScene: seleção por clique, seleção múltipla (Ctrl), caixa de seleção, zoom pela roda, ferramenta pan, ajuste da vista, escala vertical exclusivamente visual.
- **Mover**: seleciona e arrasta um nó, com snap por extremidade, ponto médio ou grade de 50 mm. A posição só é aplicada ao modelo após soltar o mouse.
- **Novo nó**: clique cria um *rascunho* de nó; ele passa ao modelo estrutural quando uma barra válida o conecta à malha existente. Isso impede nós isolados no solver.
- **Criar barra**: clique primeiro nó e depois segundo nó; o grupo da barra segue o combo da aba Propriedades.
- **Subdividir**: clique uma barra; cria nó intermediário e duas barras, preservando o comprimento e a área. A barra original deixa de existir e novos IDs são emitidos sem reciclagem.
- **Excluir**: barra ou nó selecionado, com remoção das barras incidentes e cargas nodais órfãs. Se o resultado não for um modelo geométrico válido, a edição é recusada.
- Propriedades: edição X/Y, suporte UX/UY, grupo e perfil por grupo.
- Cargas: nova carga nodal, tabela por caso, Fx/Fy em kgf/tf/kN/N. A aba **Ações gerais** agora permite editar casos de carga de área, linha, peso próprio e vento com intensidade, direção, zona e base de comprimento; o motor distribui as resultantes aos nós. Os valores de pressão e coeficientes são sempre fornecidos pelo projetista.
- Resultados: esforços por caso/combinação, modos de envoltória (tração e compressão), pesquisa de dez barras críticas, exportação CSV DimPerfil e memorial HTML A3.
- `F5` calcula. `Ctrl+S`, `Ctrl+O`, `Ctrl+Z`, `Ctrl+Y` e `Delete` disponibilizam comandos convencionais.

Todas as edições estruturais invalidam os resultados anteriores. Não há um solver no viewport.

## Importação DXF / DWG

**Arquivo > Importar DXF/DWG**:

1. Escolha arquivo; se DXF não tiver `$INSUNITS`, informe a unidade manualmente (mm, cm, m ou polegada).
2. Informe tolerância de união dos nós (valor inicial 1 mm).
3. Confira o desenho preliminar, a quantidade de barras, as camadas, entidades ignoradas e seus grupos.
4. Confirme conscientemente a **substituição da geometria**. Apoios, combinações e carregamentos que não podem ser transferidos serão removidos. A malha importada começa sem apoios; é necessário criá-los.

**Entidades suportadas**: `LINE`, `LWPOLYLINE` sem arcos, `POLYLINE` plana e blocos `INSERT` que contenham tais entidades. Arcos, splines, hachuras, textos, cotas e elementos 3D não são convertidos em barras; são contabilizados como ignorados.

**Não é interpretação estrutural automática**. As linhas devem ser eixos analíticos das barras; cruzamentos de linhas sem vértice explícito não geram nó. Camadas são classificadas por heurísticas e exigem revisão. Não são gerados apoios, perfis resistentes certificados, ações normativas nem ligações.

**DWG**: a biblioteca Python ezdxf não lê DWG diretamente. A opção usa a integração local `ezdxf.addons.odafc` e requer que o **ODA File Converter** esteja instalado e acessível. Se não estiver, o aplicativo recusa o DWG com mensagem e orienta a convertê-lo previamente para DXF. Não há envio de arquivo à internet.

## Arquitetura auditável

- `poe_truss/` — motor de análise e seus dados; sem dependências PySide6.
- `desktop/bridge.py` — estado de projeto, leitura/escrita JSON e interface com o solver.
- `desktop/editing.py` — comandos imutáveis para edição topológica, geometria e IDs.
- `desktop/cad_io.py` — leitura controlada de CAD e aprovação para modelo explícito.
- `desktop/qt/viewport.py` — QGraphicsView e eventos do desenho.
- `desktop/qt/app.py` — ribbon, painéis de propriedades, cargas e resultados.
- `desktop/app.py` — interface Tkinter legado preservada apenas para compatibilidade e comparação histórica; **não é o launcher atual**.
- `tests/test_cad_editing_pyside.py` — testes automáticos CAD/edição, sem ambiente gráfico.

O esquema persistente continua **`poe-truss-python/v1`**. Um campo opcional `model_override` registra a malha explícita pós-edição/importação; `cad_drafts` guarda nós provisórios. IDs de nó/barra estáveis são preservados quando possível. Alterações de topologia limpam resistências externas potencialmente vencidas e exigem reconfirmação dos travamentos.

## Limitações e evidências

- O roteiro manual de interface nas resoluções-alvo permanece na [documentação de revisão 3D](docs/REDESENHO_UI_E_PERFIS_3D_V09.md).
- O núcleo Python, a importação DXF com arquivos reais gerados para teste, a leitura/escrita JSON e o cálculo estrutural pós-importação foram testados.
- DWG com ODA real e executável Windows não foram testados nesta infraestrutura.
- Sem verificação normativa completa NBR 14762, NBR 8800, estabilidade global fora do plano ou aprovação ELU. O uso continua exploratório/experimental.

## Fluxo de projeto integrado na interface nativa

A aba **Perfis** altera os perfis por grupo, a quantidade de componentes, a modulação e permite registrar fabricante/modelo e massa superficial de telhas informados pelo usuário. O caso `G2` é atualizado como carga superficial de telha, com convenção `1 kgf = 10 N`. O passo das terças é hipótese geométrica, não capacidade resistente comprovada.

A aba **Combinações** permite criar, excluir e editar fatores assinados por caso; não calcula coeficientes normativos automaticamente. A aba **Estabilidade** registra K no plano/fora do plano, eixo, orientação e comprimentos destravados declarados. A aba **Alternativas** pesquisa em segundo plano e mostra até três soluções, sem impedir valores manuais fora da pesquisa. **Diagnóstico** localiza problemas e sinaliza as pendências normativas.

## Vista 3D — seções extrudadas (revisão acumulativa v0.1)

**Exibição > Vista 3D** abre uma janela não modal. O programa lê as dimensões U, UE e L disponíveis no catálogo e extruda o **contorno da seção aberta** no eixo da barra, com orientação e arranjos simples/duplos configuráveis. Não usa mais os prismas cheios genéricos da versão anterior.

- Arraste **esquerdo**: girar; roda: zoom; **clique direito** sobre uma peça: informações da barra. O visor traz modos sólido/aramado e escala de seção **1×–8×** (padrão 3×), exclusivamente gráfica; OBJ é exportado em escala real 1×.
- Presets isométrica, frontal XY, perfil lateral e superior; cor por grupo, família ou sinal da força axial.
- Aba **Arranjo**: componentes simples/duplos, costas a costas / frente a frente / mesma orientação, rotação e distância entre centroides (mm).
- Aba **Arranjo** traz prévia ampliada da seção efetivamente desenhada.
- O botão **Aplicar ao projeto** atualiza o JSON, recalcula a geometria do modelo 2D e invalida resultados anteriores.
- O botão **Exportar malha OBJ** gera malhas fechadas em mm para conferir em visualizadores externos.
- Perfis duplos sem distanciamento explicitado apresentam um aviso; a separação de 6 mm nesse caso é **puramente gráfica**.
- Os perfis laminados com dimensões incompletas usam geometrias **idealizadas** e avisos. Sem raios de concordância ou espessura diferenciada de mesa. Se a área desenhada divergir significativamente da área utilizada no solver, um aviso identifica a discrepância.

A visualização continua **geométrica**, não uma análise 3D ou verificação normativa. A versão atual renderiza faces por ordenação de profundidade sem z-buffer; interseções visuais complexas não estão homologadas para análise de interferências.

A barra superior reúne arquivos, análise e a vista 3D. Use as abas da faixa de comandos para criar e editar o modelo, atribuir ações e controlar o que aparece no desenho. À esquerda, **Modelo** filtra nós e barras por ID ou grupo, e **Tarefas** abre as páginas do inspetor à direita.

A barra do desenho oferece seleção, movimentação, pan, enquadramento e escolha de caso ou combinação. A barra inferior mostra as coordenadas em milímetros, o estado da análise e os controles independentes de grade e snap. **Exibição → IDs dos nós** liga os identificadores no desenho.

`F5` calcula e abre a tabela inferior. Clique numa linha para inspecionar a barra ou use **Detalhar** para consultar filtros e envoltórias. Arraste os divisores para redimensionar os painéis. Use **Só desenho** ou `Ctrl+0` para recolher e restaurar os painéis. `Esc` volta à seleção.

## Limites ainda presentes

- Ambiente de validação sem runtime PySide6: compilação sintática e testes do núcleo concluídos, **sem homologação gráfica real em Windows**.
- O procedimento de build gera um pacote portátil sem assinatura digital.
- Perfis duplos permanecem dependentes de hipóteses de solidarização; resistência por NBR 14762 ainda não implementada.
- Intercâmbio DWG requer ODA File Converter externo.
- Edição CAD com modelo explícito não suporta distribuição superficial automática: ações de área/linha ficam bloqueadas até implementação de associação de superfícies/tramos no CAD.
- Reações/esforços ainda precisam de validação cruzada real no FTool.
