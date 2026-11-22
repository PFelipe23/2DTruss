# Inclusão obrigatória — revisão UI/3D v0.1

Auditar `desktop/section_mesh.py`, `desktop/qt/view3d.py`, `desktop/qt/ui_theme.py` e as alterações em `desktop/qt/app.py`. Verificar winding de faces OBJ e fechamentos volumétricos, correspondência entre `model.members` e projetos de seções duplas, áreas visuais versus `area_mm2`, estado desatualizado da análise e persistência do JSON. Testar GUI PySide6 em Windows (1366×768 / 1600×900 / 1920×1080) com o roteiro de `docs/REDESENHO_UI_E_PERFIS_3D_V09.md`. Não apresentar teste geométrico de CPU como homologação de interface ou dimensionamento normativo.

---

# Auditoria Codex — 2DTruss v0.1 / PySide6 CAD

O produto atual é **desktop PySide6** (`2DTruss.pyw`) sem navegador, com solver Python separado.

## Auditoria obrigatória

- Instalar `requirements-test.txt` e executar `python -m pytest -q -rs tests`.
- Comparar SHA256 `poe_truss/solver.py` com a edição Tk desktop anterior. Não alterá-lo nesta evolução.
- Inspecionar `desktop/editing.py` para integridade de IDs, nós provisórios, subdivisão, remoção e invalidação de capacidades externas.
- Inspecionar `desktop/cad_io.py` e verificar INSUNITS, tolerância, entidades suportadas, extensão DWG com ODA, importação segura de origem e grupos.
- Após instalar PySide6, executar `2DTruss.pyw` em ambiente gráfico e testar `desktop/qt/app.py`/`viewport.py`: ribbon, QGraphicsScene, modos de seleção, pan, zoom, snapping, criação e exclusão de nós e barras, propriedades e apoio por nó.
- Abrir e salvar um JSON legado; importar um DXF e verificar resultados de um caso analítico no FTool.
- Proibir que geometria CAD não conferida seja apresentada como dimensionamento estrutural certificado.

## Situação de validação

A suíte do motor e DXF foi executada na preparação desta entrega. A interface gráfica PySide6 e a integração DWG/ODA exigem validação externa; **não atribuir status aprovado por inspeção estática**.
