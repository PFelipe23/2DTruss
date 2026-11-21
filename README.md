# 2DTruss — v0.1

**2DTruss** é um aplicativo desktop em Python/PySide6 para concepção e análise linear de **treliças planas**, com editor de nós e barras, visualização de carregamentos e resultados, importação DXF, inspeção geométrica 3D de perfis U, Ue, L, W, H e HP e emissão de relatórios.

> **Estado: experimental.** A análise 2D ainda depende de validação cruzada efetiva no FTool. O pré-dimensionamento e a triagem de Euler/escoamento bruto **não são dimensionamento resistente normativo**. A janela PySide6 não está homologada em Windows; a importação DWG depende do ODA Converter; a inspeção 3D não é análise espacial e as seções podem ser idealizadas.

## Instalar e executar

Requer Python 3.10 ou superior, PySide6 e ezdxf. Em computadores que permitem instalação por usuário:

```powershell
py -3 -m pip install --user -r requirements-desktop.txt
py -3 2DTruss.pyw
```

No Windows, também pode executar `INSTALAR_DEPENDENCIAS_USUARIO.bat` e `INICIAR_DESKTOP.bat`. Para gerar o executável portátil com PyInstaller, siga o [guia desktop](LEIA-ME_DESKTOP.md#gerar-o-executável-windows).

O [manual do usuário](docs/MANUAL_DO_USUARIO.md) acompanha uma treliça Pratt de 16 m da preparação do modelo à leitura da envoltória ELU e da deformada ELS.

## Testes

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q -rs tests
```

O CI executa a regressão em Linux com Qt offscreen e verifica a inicialização do pacote gerado no Windows. A inspeção gráfica nas resoluções-alvo e a comparação independente dos casos no FTool têm roteiros próprios.

## Organização

| Pasta | Escopo |
|---|---|
| `poe_truss/` | Solver Python 2D, ações, combinações, estabilidade declarada e resultados |
| `desktop/qt/` | UI nativa PySide6, viewport 2D e visualizador geométrico 3D |
| `desktop/` | Editor CAD, importação de DXF e preparação para DWG |
| `tests/` | Testes analíticos e regressão |
| `examples/` | Projetos e arquivos de teste |
| `verification/` | Benchmarks e evidências **não homologadas** |
| `docs/` | Arquitetura, histórico e limitações |
| `web/` | Interface web legada, sem uso pelo launcher principal |

**Compatibilidade:** o pacote interno `poe_truss` e os esquemas `poe-truss-python/v1` foram preservados para abrir os projetos das versões anteriores. Esse nome interno não representa a marca pública.

**Unidades:** por convenção deste software, `1 tf = 1.000 kgf = 10 kN` (`1 kgf = 10 N`). O cálculo interno usa N, mm e MPa.

## Versão e contribuição

A identificação pública é **2DTruss v0.1**, com uma casa decimal. Tag Git: `v0.1`. O código foi importado de um protótipo anterior, mas possui um **novo histórico Git inicial**. Consulte `AGENTS.md`, `CODEX_AUDITORIA.md` e `docs/RELEASE_0.1.md` antes de alterar o solver.

## Licença e direitos

O código do 2DTruss é distribuído sob a [licença MIT](LICENSE). A [documentação de licenciamento](docs/LICENCIAMENTO.md) registra a procedência de dados e as licenças das dependências usadas no pacote Windows.
