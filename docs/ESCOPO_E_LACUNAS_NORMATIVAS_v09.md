# Matriz de implementação acumulativa — v0.9.0-beta

| Etapa | Funcionalidade | Estado comprovado | Não implementado / risco |
|---|---|---|---|
| v0.1 | Treliça 2D, cargas nodais, análises, esforços e deformadas | Motor existente; testes e exemplos | Não analisa pórticos, nem barras sob flexão local |
| v0.2 | Rastreio de cargas, balanços, vento normal, casos/combinações | Testes automatizados | Não calcula vento normativo completo |
| v0.3 | Travamentos, coeficientes K, eixos, Lb por barra | Cadastro validado; testes | Eficácia dos contraventamentos NÃO verificada |
| v0.4 | Tração: triagem de escoamento bruto com fy e fator informado | Calculado + teste unitário | Ruptura líquida, shear lag, ligações e NBR 14762 integral pendentes |
| v0.5 | Compressão: cargas elásticas críticas de Euler (onde cabível) | Calculado + teste unitário | Flambagem global normativa, flexo-torção, imperfeições pendentes |
| v0.6 | Estados-limites local e distorcional | **Marcadores de pendência e bloqueio de aprovação** | **Procedimentos de resistência não implementados** |
| v0.7 | Seções duplas (Ix/Iy, centros deslocados) | Propriedades elásticas + testes | Ixy de L, torção, ligação entre componentes, solidarização pendentes |
| v0.8 | Busca local de perfis por massa e ELS | Funcional, pesquisa determinística | Sem garantia ótimo global, sem garantia ELU |
| v0.9 | Contraflecha preliminar; memorial A3; auditoria CSV/manifesto | Funcional e testado | Desenho executivo, fabricação, validação FTool externa pendentes |

## Não declarar conformidade normativa

As versões **0.4 a 0.6 implementam apenas etapas de triagem**, não o módulo
resistente normativo completo inicialmente previsto. Consequentemente a
marcação de desenvolvimento acumulativo `v0.9-beta` indica integração
arquitetural/funcional, **não** conclusão do dimensionamento ELU.

### Requisitos formais para a versão 1.0

1. Licenciar/consultar integralmente e validar o texto vigente das normas
   ABNT NBR 14762, NBR 8800, NBR 8681 e demais aplicáveis.
2. Verificar tração por escoamento bruto e ruptura líquida efetiva, ligações,
   seções perforadas e condições da ligação adotada.
3. Implementar compressão por mecanismos de instabilidade global (flexão,
   torção e flexo-torção), local e distorcional conforme família de perfil.
4. Verificar perfis duplos com espaçadores/ligação de componentes e rigidez
   dos sistemas de contenção lateral; não inferir por somatório de inércias.
5. Validar modelos de 2D e carregamentos contra FTool real; manter evidências.
6. Calibrar combinação ELU/ELS conforme versões oficiais da norma e categorias
   de ação; o programa atual aceita fatores manuais sem validar sua origem.
7. Criar benchmarks independentes e checagem de casos limite, com rastreio
   até equações e cláusulas das normas.

## Revisão de modelagem necessária

O solver plano determina N por barra e deslocamentos nos graus de liberdade
UX e UY. A avaliação fora do plano é uma checagem **de cada barra sob hipóteses
fornecidas**, e não solução da estabilidade global do galpão. O sistema
fisicamente responsável pelos travamentos deve ser verificado em projeto à
parte. Cargas intermediárias sobre banzos geram flexão local não calculada.

## Protocolo de validação com FTool

- Reconstruir cada modelo usando os CSV de nós, barras, apoios e cargas.
- Articular os membros adequadamente no FTool e usar mesmas propriedades E/A.
- Obter N, UX, UY e reações; conferir convenções.
- Registrar artefatos do FTool, comparação e tolerâncias.
- Não classificar como validado sem evidência do solver FTool.
