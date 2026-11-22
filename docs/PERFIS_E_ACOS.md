# Bibliotecas de perfis e aços

O arquivo `catalogo_perfis.csv` reúne as seções selecionáveis e informa a procedência de cada linha. As dimensões do contorno estão em mm, a área bruta em cm², as inércias em cm⁴ e a massa linear em kg/m.

## Perfis

- **U, Ue e L formados a frio**. A biblioteca inclui 24 bitolas novas de referência geométrica, além das entradas legadas. Para as novas bitolas, a área bruta e as inércias são integradas sobre contornos de paredes retas. A massa usa densidade de 7.850 kg/m³. Os raios de dobra, as tolerâncias de fabricação e a área efetiva dependem da seção e do produto reais. A ABNT NBR 6355 trata da padronização de perfis e a ABNT NBR 14762 trata do dimensionamento de estruturas de perfis formados a frio. [Referências de perfis formados a frio no PBQP-H](https://pbqp-h.mdr.gov.br/wp-content/uploads/2021/04/Minuta-Revisa%CC%83o-da-DIRETRIZ-no003-rev003-2023-REV6.pdf)
- **W, H e HP laminados**. São 22 bitolas selecionadas da Gerdau. As bitolas H preservam a designação W com o sufixo `(H)`, conforme o fabricante. Para as três famílias, o 3D usa a altura, a largura de mesa e as espessuras de alma e mesa publicadas. O contorno de inspeção omite os raios de concordância. A área, a massa e as inércias vêm da publicação, de modo que a área desenhada pode diferir da área do modelo. [Tabela de bitolas Gerdau](https://www2.gerdau.com.br/wp-content/uploads/2022/07/Tabela-de-Bitolas-Gerdau-2.pdf) · [Perfis W e HP e referência à ABNT NBR 15980](https://mais.gerdau.com.br/produtos/perfil-estrutural)

## Aços

- **CFQ210, CFQ250, CFQ280 e CFQ300** usam os mínimos de referência do catálogo de tiras a quente da Usiminas associado à ABNT NBR 6650. O catálogo consultado apresenta os graus para chapas de 1,80 a 5,00 mm. [Usiminas, Tiras a Quente](https://www.usiminas.com/wp-content/uploads/2020/06/US-0073-15F-CAT-TIRAS-A-QUENTE-05-2020-web.pdf)
- **MR 250, AR 350 e AR 415** usam os valores de referência da Gerdau associados à ABNT NBR 7007. O **ASTM A572 Grau 50**, informado pela Gerdau para a linha W e HP, tem opção própria com `fy = 345 MPa` e `fu = 450 MPa`. Confirme a especificação do produto, a faixa de espessura e o certificado de fornecimento. [Gerdau, Barras e Perfis](https://www2.gerdau.com.br/wp-content/uploads/2022/07/Barras-e-Perfis-Catalogo-Gerdau-1.pdf) · [Gerdau, Estacas Metálicas](https://www2.gerdau.com.br/wp-content/uploads/2022/07/Manual-Estacas-Metalicas-Gerdau-1.pdf)

O modelo armazena um aço uniforme por projeto e mantém os valores numéricos em `material`. A alteração da bitola preserva o aço escolhido. A análise axial usa `E`, e a triagem de escoamento usa `fy`. O campo `fu` registra a propriedade para consulta. A verificação resistente pelas normas ABNT NBR 14762 ou ABNT NBR 8800 permanece uma etapa de engenharia separada.
