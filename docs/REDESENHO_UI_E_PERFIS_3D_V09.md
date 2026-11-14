# POE Treliça v0.9 — Revisão do workspace e perfis 3D

**Escopo:** revisão acumulativa de UI e geometria de visualização, sem alterar a formulação da análise de treliças planas.

## Problema identificado

1. O visualizador anterior utilizava `member_prism()` para todos os perfis. O desenho era sempre uma caixa cheia, inclusive quando a barra estava associada a U, UE e L.
2. A aplicação PySide6 possuía um `QTabWidget` lateral com muitas abas, dificultando a localização das ferramentas.
3. O visor 2D concentrava todos os resultados no inspetor lateral, sem tabela inferior sincronizada.
4. A janela 3D não permitia revisar o arranjo e o espaçamento dos componentes da seção composta.

## Referências de mercado usadas como diretrizes, não como código copiado

- RFEM 6 / RSTAB 9: separação entre navegador de dados, visualização e resultados: https://www.dlubal.com/en/downloads-and-information/documents/online-manuals/rfem-6/000016
- RSTAB 9: cores de objetos, vista renderizada e configuração de exibição: https://www.dlubal.com/en/products/rstab-frame-and-truss-structures/rstab-9/graphical-user-interface
- SCIA Engineer: modelos 1D, representação de seções, opções wireframe e rendered: https://www.scia.net/en/scia-engineer/fact-sheets/modelling/sciabasic-basic-module

## Implementação

### Workspace 2D

- Ribbon com três grupos por aba e ícones Qt padronizados.
- Navegador do modelo com filtro de IDs e barras.
- Árvore fixa de tarefas, organizada por Conceber → Modelar → Ações → Análise.
- Inspetor com páginas persistentes, mas sem faixa horizontal de dezenas de abas.
- Vista XY central e tabela inferior de esforços; selecionar uma linha destaca a barra no desenho.
- Estado visível `NÃO CALCULADO` / `CALCULADO` após as operações sobre o modelo.
- Mantidos edição CAD, snaps, ações, combinações, estabilidade, alternativas e relatórios anteriores.

### Geometria 3D

- `desktop/section_mesh.py`: gera polígonos abertos de seção U, UE com lábios e L; lê `bw_mm`, `bf_mm`, `t_mm` e a aba/lábio UE do nome do perfil existente.
- Contornos centrados pelo centroide geométrico e extrudados na direção dos eixos da barra; eixo da seção no plano da treliça e eixo perpendicular no eixo Z.
- Componentes simples/duplos e três modos básicos de orientação: costas a costas, frente a frente e mesma orientação.
- Distâncias `centroid_dx_mm` (fora do plano, Z) e `centroid_dy_mm` (no plano); rotação `rotation_deg`.
- Configuração no diálogo 3D altera o JSON de `section_arrangements`, preservando o contrato do projeto, e invalida os resultados da análise.
- Se `dx=dy=0` para dois componentes, o visualizador introduz somente uma folga **gráfica** de 6 mm, com aviso obrigatório. A geometria do modelo estrutural não é alterada.
- Geometria de seções laminadas com espessura de mesa não fornecida continua idealizada; contornos retos, sem raios de dobra ou concordância.
- Ao diferir mais de 8% da área axial utilizada pelo solver, o módulo sinaliza a discrepância.
- Visualização 3D opera com QGraphicsScene e projeção CPU, com rotação, zoom, presets, cores por família/grupo/esforço, e modos sólido e aramado; não usa GPU/OpenGL nem faz cálculo estrutural espacial.
- Escala de seção no display, inicialmente **3×** para leitura em vãos longos, ajustável de 1× a 8×. Afeta exclusivamente vértices projetados, e NUNCA os arquivos OBJ ou geometria de análise.
- `export_obj()` exporta malhas fechadas e trianguladas em milímetros, permitindo inspeção em ferramentas CAD/3D externas. OBJ não possui o modelo de cálculo nem informações de projeto de ligações.

## Limitações não resolvidas

- A QGraphicsScene 3D usa algoritmo de pintura por profundidade média, sem z-buffer; interseções visuais podem apresentar sobreposição inadequada em posições específicas de câmera. A malha OBJ é independente dessa limitação.
- Não há discretização de raios, espessuras diferenciais de mesas laminadas ou representação de ligação soldada/parafusada.
- Não realiza verificação de colisões, construtibilidade, comprovação de ações compostas ou dimensionamento à NBR 14762 / NBR 8800.
- O catálogo existente tem 24 entradas com procedência heterogênea. Algumas dimensões são aproximações geométricas para desenho; não constituem confirmação dimensional de fabricante.
- O Python/PySide6 precisa existir no computador ou ser empacotado em um executável Windows, ainda não homologado.
- O ambiente de integração desta entrega **não dispõe do runtime PySide6**. Código Qt: sintaxe aprovada, execução real pendente. Não chamar a UI de homologada.

## Testes auditáveis

Comando executado: `python -m unittest discover -s tests -v`

A execução consolidada registrou **123 testes executados, 3 ignorados** (incluindo o teste Qt real impedido pela ausência do runtime).

A bateria contempla testes antigos do solver e uma nova suíte com áreas de contorno, centragem, UE com lábios, orientações de seção dupla, malhas sobre barras inclinadas, carregamento de projetos anteriores e exportação OBJ. A malha Ue da amostra foi importada com `trimesh` e teve fechamento topológico e volume geométrico corretos.

A comparação SHA-256 de `poe_truss/solver.py` contra a base anterior é idêntica. Os casos FTool continuam pendentes de execução independente.

## Critérios de aceite de interface em Windows (pendente)

1. Iniciar `POE_Trelica.pyw` sem exceções, em 1366×768, 1600×900 e 1920×1080.
2. Selecionar e mover nós; criar/excluir/subdividir barra; desfazer/refazer; editar apoio e carga nodal.
3. Confirmar atualização da árvore de tarefas, da tabela inferior e do estado calculado/desatualizado.
4. Abrir 3D; alternar entre U, UE e L; confirmar perfil correto na janela; orbitar, aproximar, selecionar membro por clique direito.
5. Configurar duplo costas a costas / face a face, espaçamento e rotação; aplicar; salvar/reabrir JSON; conferir invalidação dos resultados.
6. Exportar OBJ, abrir em visualizador externo, confirmar ausência de faces faltantes e uso de milímetros.
7. Reexecutar solver, comparar esforços/reações com referências independentes, quando disponíveis.
