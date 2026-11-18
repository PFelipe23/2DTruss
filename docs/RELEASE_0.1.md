# 2DTruss — v0.1

Primeira edição nomeada 2DTruss para GitHub. Importa cumulativamente o protótipo POE Treliça (antiga linha v0.9) em **um novo histórico Git**, preservando solver e formatos JSON.

## Identidade
- Nome: `2DTruss`; executável/launcher Python: `2DTruss.pyw`.
- Tag: `v0.1`; resultado JSON `software_version: "0.1"`.
- Módulo interno `poe_truss` e schemas `poe-truss-*` conservados por retrocompatibilidade.

## Escopo
- Gerador parametrizado e edição explícita de treliças planas; casos e combinações manuais; forças normais, reações e deslocamentos; importação DXF; vista 3D de perfis geometrizados.
- Requer runtime PySide6 para interface, não homologado em Windows nesta entrega.
- Não possui aprovação normativa ELU, comparação FTool efetivamente realizada nem dimensionamento espacial.

## Propriedade intelectual
- O código está sob a [licença MIT](../LICENSE). A [documentação de licenciamento](LICENCIAMENTO.md) acompanha a revisão dos materiais de terceiros.
- O histórico técnico anterior permanece em `docs/` e pode citar versões legadas; não altera o número público da nova edição.
