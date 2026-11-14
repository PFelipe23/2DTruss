# Evidências de validação — POE Treliça v0.9 Desktop

## Base e escopo

- Motor Python: `poe_truss/solver.py` intacto (SHA-256 `ad68ce5b64cc7352cb5808086a3e63594912ff4cc51a38a476ab47bdf0583612`).
- Resultado para cobertura de duas águas sem `node_edits`: hash SHA-256 de massa, flecha e esforços G1 idêntico ao pacote v0.9 anterior: `710c9a003d07b4bebab4633dcd8aa721e1a02c915341124518d8ef6e82f1cb6e`.
- Interface: Tk/ttk nativa; testes realizados com Xvfb Linux, **não equivalem a execução nativa no Windows**.
- A validação independente com FTool e a aprovação resistente ELU continuam pendentes.

## Testes

- `python -m pytest -q`: testes de motor e sessão sem display; teste da interface é ignorado se não existir sessão gráfica válida.
- `xvfb-run -a -s '-screen 0 1600x950x24' python -m pytest -q`: suite completa, 97 aprovados + 6 subtests.
- Inspeções manuais assistidas de screenshot: modelagem paramétrica, cargas por caso, esforços e painel de nó (arquivos `captures/`).
- Teste de alteração nodal em geometria paramétrica com cargas superficiais: após deslocamento, recalcula sem `model_override`, preservando cargas G2.
- Teste de edição em geometria explícita do benchmark triangular, incluindo apoios.
- Teste de carregamentos nodais com `kgf` e `kN` e persistência no JSON.
- Teste de invalidar análise após alteração; testes de exportação HTML A3 e CSV DimPerfil.

## Limitações de comprovação

Os testes não demonstram estabilidade fora do plano, resistência local/distorcional ou validade de contraventamentos. O relatório não constitui memorial de dimensionamento executivo. O executável Windows poderá ser construído localmente com o script opcional, mas não foi produzido ou testado aqui.
