# Como contribuir

O projeto é experimental. Priorize correções verificáveis no motor e melhorias de UX que preservem a rastreabilidade dos resultados.

1. Crie uma branch a partir de `main`: `feat/...`, `fix/...`, `test/...`.
2. Inclua um teste que reproduza o comportamento desejado ou o erro corrigido.
3. Instale `requirements-test.txt` e execute `python -m pytest -q -rs tests`.
4. Abra PR com resumo, limitações e evidências de validação. Interface Qt exige inspeção gráfica real; FTool exige comparação com execução no próprio programa.

**Não** envie normas digitalizadas, apostilas de terceiros, dados de clientes, credenciais, binários de fornecedores nem arquivos DWG proprietários sem autorização.

O projeto adota a [licença MIT](LICENSE). Para catálogos, exemplos de terceiros e dependências, siga as orientações de [licenciamento e procedência](docs/LICENCIAMENTO.md).
