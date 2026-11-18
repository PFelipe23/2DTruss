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
- A importação DWG com o conversor ODA exige teste em uma instalação do conversor.
- Sem verificação normativa completa NBR 14762, NBR 8800, estabilidade global fora do plano ou aprovação ELU. O uso continua exploratório/experimental.

## Fluxo de projeto integrado na interface nativa

A aba **Perfis** altera os perfis por grupo, a quantidade de componentes, a modulação e permite registrar fabricante/modelo e massa superficial de telhas informados pelo usuário. O caso `G2` é atualizado como carga superficial de telha, com convenção `1 kgf = 10 N`. O passo das terças é hipótese geométrica, não capacidade resistente comprovada.

A aba **Combinações** permite criar, excluir e editar fatores assinados por caso; não calcula coeficientes normativos automaticamente. A aba **Estabilidade** registra K no plano/fora do plano, eixo, orientação e comprimentos destravados declarados. A aba **Alternativas** pesquisa em segundo plano e mostra até três soluções, sem impedir valores manuais fora da pesquisa. **Diagnóstico** localiza problemas e sinaliza as pendências normativas.

### Inserir e conferir cargas em 2D

Em **Ações → Inserir cargas**, escolha ou crie um caso nodal. Clique num nó no desenho ou escolha seu ID no inspetor. Informe `Fx`, `Fy` e a unidade. `Fx` positivo aponta para a direita e `Fy` positivo para cima. Para repetir a mesma força em vários nós, selecione-os com Ctrl+clique e use **Aplicar a n nós selecionados**. Cada nó recebe uma parcela com os mesmos valores. Clique numa parcela da tabela para editar ou remover essa linha. **Nova** encerra a edição da linha e reaproveita os valores do formulário.

**Ações gerais** mostra os campos pertinentes ao tipo do caso. Selecione um caso ou combinação no desenho e ligue **Cargas** para conferir suas resultantes nodais antes de calcular. As setas ficam acima dos nós, ligadas por uma linha pontilhada. Cada seta mantém a direção da força e seu comprimento é relativo à maior força do caso. A faixa mostra a soma de `Fx` e `Fy` em kN. **Valores** distribui as magnitudes acima das setas e omite os rótulos que não couberem. Passe o cursor sobre o nó para ver as componentes.

## Área de trabalho

A barra superior reúne arquivos, análise e o botão **2D | 3D**. Use as abas da faixa de comandos para criar e editar o modelo, atribuir ações e controlar o que aparece no desenho. À esquerda, **Modelo** filtra nós e barras por ID ou grupo, e **Tarefas** abre as páginas do inspetor à direita.

A barra do desenho oferece seleção, movimentação, pan, enquadramento e escolha de caso ou combinação. A barra inferior mostra as coordenadas em milímetros, o estado da análise e os controles independentes de grade e snap. **Exibição → IDs dos nós** liga os identificadores no desenho.

`F5` calcula e abre a tabela inferior. Clique numa linha para inspecionar a barra ou use **Detalhar** para consultar filtros e envoltórias. Arraste os divisores para redimensionar os painéis. Use **Só desenho** ou `Ctrl+0` para recolher e restaurar os painéis. `Esc` volta à seleção.

## Perfis, aço e vista 3D

Em **Modelagem → Perfis**, escolha o grupo, a biblioteca e a bitola. A seleção é aplicada ao grupo com quantidade **1**. Aumente a quantidade após escolher a bitola para criar uma seção dupla. Projetos abertos mantêm os perfis e as quantidades gravados.

Em **2D | 3D**, a aba **Arranjo** permite editar o mesmo grupo. Um clique direito numa barra seleciona seu grupo no painel. Arraste com o botão esquerdo para girar, use o botão central para deslocar e a roda para aproximar. A troca de bitola, a geometria confirmada no inspetor e os ajustes de arranjo atualizam a vista aberta. Use `F5` para recalcular depois de modificar o projeto.

Em **Exibição** no painel 3D, ajuste cor, modo sólido ou aramado e escala de seção. **Exportar OBJ** gera malhas em milímetros e escala real, independentemente do exagero visual. Seções duplas com espaçamento nulo têm uma separação gráfica de 6 mm. O visor ordena faces por profundidade para inspeção visual. Use o OBJ em um visualizador adequado para examinar interseções.

O seletor **Aço do projeto** aplica propriedades ao material uniforme do modelo. Consulte a [procedência dos perfis e aços](docs/PERFIS_E_ACOS.md) para escolher a biblioteca e conferir as propriedades de referência.

## Limites ainda presentes

- Ambiente de validação sem runtime PySide6: compilação sintática e testes do núcleo concluídos, **sem homologação gráfica real em Windows**.
- O procedimento de build gera um pacote portátil sem assinatura digital.
- Perfis duplos permanecem dependentes de hipóteses de solidarização; resistência por NBR 14762 ainda não implementada.
- Intercâmbio DWG requer ODA File Converter externo.
- Edição CAD com modelo explícito não suporta distribuição superficial automática: ações de área/linha ficam bloqueadas até implementação de associação de superfícies/tramos no CAD.
- Reações/esforços ainda precisam de validação cruzada real no FTool.
