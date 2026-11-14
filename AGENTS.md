# AGENTS.md — 2DTruss v0.1

## Fonte de verdade
- Aplicativo desktop: `2DTruss.pyw` e `desktop/qt/`.
- Motor único: `poe_truss/` (Python, modelo de treliça plana elástica), preservado por compatibilidade.
- Identidade pública e versão: `poe_truss/version.py` (**2DTruss v0.1**, nunca três componentes).
- Preservar IDs de nós/barras, arquivos JSON e o contrato de unidades (1 kgf = 10 N).
- Testar: `python -m unittest discover -s tests -p 'test_*.py'`.

## Integridade de engenharia
- Não classificar as triagens Euler/área bruta como resistência ELU normativa.
- Não assumir que uma terça constitui travamento lateral efetivo.
- Não afirmar validação FTool sem resultados externos reais.
- O 3D é somente visualização; o solver é estritamente 2D.
- Exigir caso analítico e regressão antes de modificar solver ou distribuição nodal.
- Invalidação de resultados sempre que mudar geometria, cargas ou perfis.
- Preservar informação de procedência e qualidade das propriedades geométricas.

## Entrega
- Branches `feat/...`, `fix/...`, `test/...`, `docs/...`.
- CI verde e testes reproduzíveis; atualizar documentação de novas funcionalidades.
- Não adicionar arquivos proprietários de normas ou conteúdo protegido.
- Versionamento público fixado em `v0.1` até decisão explícita do mantenedor.
