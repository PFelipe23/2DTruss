# 2DTruss — v0.1

**2DTruss** é um aplicativo desktop em Python/PySide6 para concepção e análise linear de **treliças planas**, com editor de nós e barras, visualização de carregamentos e resultados, importação DXF, inspeção geométrica 3D de perfis U/UE/L e emissão de relatórios.

> **Estado: experimental.** A análise 2D ainda depende de validação cruzada efetiva no FTool. O pré-dimensionamento e a triagem de Euler/escoamento bruto **não são dimensionamento resistente normativo**. A janela PySide6 não está homologada em Windows; a importação DWG depende do ODA Converter; a inspeção 3D não é análise espacial e as seções podem ser idealizadas.

## Instalar e executar

Requer Python 3.10 ou superior, PySide6 e ezdxf. Em computadores que permitem instalação por usuário:

```powershell
py -3 -m pip install --user -r requirements-desktop.txt
py -3 2DTruss.pyw
```

No Windows, também pode executar `INSTALAR_DEPENDENCIAS_USUARIO.bat` e `INICIAR_DESKTOP.bat`. O projeto não fornece um executável Windows autossuficiente homologado.

## Testes

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

O CI executa os testes de regressão sem dependência de UI gráfica real. Testes ignorados devem ser tratados como pendências, não como aprovação. Executar os casos no FTool para a validação externa independente.

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

A licença ainda não foi definida. **MIT é a recomendação, mas não foi concedida formalmente.** O repositório deverá permanecer **privado** até a decisão do titular e revisão de catálogos, bibliotecas e eventuais materiais de terceiros. Consulte [`docs/LICENCIAMENTO.md`](docs/LICENCIAMENTO.md). Não incluir normas ABNT nem cópias da apostila do Olídio.
