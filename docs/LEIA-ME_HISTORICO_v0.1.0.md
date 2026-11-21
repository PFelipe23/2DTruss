# POE Treliça — motor Python v0.1.0

**Pedro Oliveira Engenharia | Primeiro protótipo do novo motor de análise (Python, código aberto à auditoria).**

O projeto reinicia a linhagem do motor numérico em Python. A numeração v0.1.0 deste pacote refere-se ao **motor Python novo**, não à distribuição v0.5.0 (Go) anterior.

## 1. Execução

- **Windows:** descompacte o ZIP e execute `INICIAR.bat`.
- **Linux/macOS:** `python3 -m poe_truss.server` ou `./INICIAR.sh`.
- **Pré-requisito:** **Python 3.10+** instalado ou acessível ao usuário. O motor e a interface **não dependem de bibliotecas Python externas**; usa-se apenas a biblioteca padrão.
- O aplicativo abre o navegador padrão usando um servidor restrito a `127.0.0.1`, em porta aleatória. Não utiliza APIs externas nem transfere informações para servidores de terceiros.
- Sem permissões administrativas necessárias para **executar** o programa com Python disponível. **Não é um .exe autossuficiente**: o interpretador deve estar instalado/portabilizado antes. Não confundí-lo com o aplicativo portátil Go anterior.

**Interface:** projeto, geometria, quatro grupos de seções, casos de ações, combinações manuais, vínculos nodais, diagrama de esforços axiais e inspeção de membros. Projeto salvo/aberto em JSON.

## 2. Motor de cálculo

Unidades internas fixas: **N, mm, MPa**.

Convenção de projeto **imposta pelo usuário**: **1 kgf = 10 N**, **1 tf = 1.000 kgf = 10 kN** (g nominal = 10 m/s²). Não equivale à definição metrológica de kgf.

- Elementos lineares de treliça plana, articulações ideais, UX/UY por nó, pequenos deslocamentos e elasticidade linear.
- Matriz de rigidez global densa, eliminação de graus de liberdade restringidos, fatoração LU com pivoteamento parcial.
- Apoios **por ID de nó**, com restrições UX, UY ou XY. Visualização permite sua edição e exige recalcular para atualizar os resultados.
- Banzos paralelos, uma água, duas águas e trapezoidal; triangulações Pratt, Howe e Warren.
- Massa de barras e peso próprio automático recalculados segundo o catálogo de perfis e multiplicidade simples/duplo.
- Busca preliminar por painéis/altura, classificando massa, passo máximo de terças, ângulos preferenciais e flecha no estado informado. É apenas otimização geométrica/de rigidez, não otimização ELU.
- Casos independentes: superfície, linha, forças nodais e peso próprio; aplicação no banzo superior/inferior; base horizontal projetada ou área de superfície da cobertura; direção vertical, horizontal ou normal à água.
- Integração dos carregamentos uniformes em cada trecho e equivalente de forças nodais (metade da resultante por nó extremo).
- Combinações de coeficientes **livres**, sem coeficientes normativos pré-configurados.
- Deslocamentos UX/UY, reações, esforços normais N (+ tração, − compressão), conferência de equilíbrio e envoltórias por barra.
- Saída CSV para inserção de resistências no fluxo DimPerfil; pacote CSV para reprodução no FTool; memorial HTML de impressão A3 horizontal.

## 3. Como usar

1. Abra o programa e mantenha o exemplo pré-carregado da treliça de duas águas com vão de 16,00 m.
2. Ajuste vão, distância entre pórticos, painéis, alturas e arranjo Pratt/Howe/Warren.
3. Defina grupos de perfis U, UE, L dobrado ou laminado e a quantidade 1×/2×.
4. Edite casos de ação individuais (kgf/m², kgf/m, kN/m², vento normal etc.).
5. Edite combinações **manuais**; clique em **Calcular**.
6. Mude o seletor de caso/combinação no desenho. Clique em nó ou barra para consultar resultados e editar apoios.
7. Na aba **FTool e exportação**, obtenha os arquivos CSV, relatório HTML/A3 e tabela para DimPerfil.
8. Salve o projeto JSON; depois poderá reabri-lo no próprio programa.
9. O botão Abrir JSON também permite importação assistida de arquivos `poe-trelica-cff/v05`. A conversão mantém as cargas legadas; **G_LEG preserva o peso da treliça estimado por m² e não deve ser somado ao novo autopeso G1 sem revisão**.

## 4. Limites rigorosos de uso

**ESTE PROGRAMA NÃO REALIZA DIMENSIONAMENTO RESISTENTE NORMATIVO ELU, NEM CERTIFICA A ESTRUTURA.**

- Sem flambagem local/distorcional/flexotorcional, ligações, fadiga, instabilidade global fora do plano, análise 3D, análise de segunda ordem, verificação de terças, deformação de telhas ou norma automática de vento.
- Seções duplas: soma de áreas/massas para o modelo axial, **sem comprovar solidarização e eficiência das ligações**.
- Cargas transversais são concentradas nos nós equivalentes da treliça, **sem considerar flexão local da barra entre nós**.
- As forças de vento são **pressões equivalentes informadas pelo usuário**, não cálculo automático de parâmetros da NBR 6123.
- Os arquivos legados v0.5 conservam suas ações antigas como aproximadas; o vento anterior é vertical e não deve ser confundido com pressão normal à água.
- Os coeficientes de combinações são informados manualmente; não há garantia de conformidade à NBR 8681.
- O catálogo contém entradas de referência demonstrativa e outras reproduzidas da Gerdau; os dados devem ser confirmados nas fontes primárias e respectivas revisões. **Não usar a coluna de catálogo como resistência ELU.**
- Peso próprio automático cobre as barras selecionadas; excluir explicitamente da configuração dupla contagens de chapas/ligadores. Não incorpora soldas, chapas, pintura, forro/telha/terças — estas devem ser acrescentadas como ações independentes.
- A busca disponível é apenas **geométrica/de rigidez** com critério de flecha configurável (L/250 inicial); não considera resistência ELU ou custos de fabricação. Durante a busca são usados apoios extremos padrão (XY à esquerda e Y à direita).
- Perfil da telha, seu catálogo de fabricante e espaçamento máximo admissível dependente das ações ainda não são verificados automaticamente.
- Cargas superficiais permitem base "projected" (área horizontal) ou "roof_surface" (área inclinada). A base escolhida deve corresponder à definição do carregamento do fabricante ou norma.

## 5. Auditoria e validação FTool

O projeto contém **36 testes automáticos**, incluindo benchmark triangular A02 com esforços, reações e deslocamentos calculados analiticamente. Comandos:

```bat
RODAR_TESTES.bat
```

```bash
python -m unittest discover -s tests -v
python -m poe_truss.cli run examples/cobertura_duas_aguas.json -o resultado.json
python -m poe_truss.cli ftool examples/FTool_A02_trelica_triangular.json --case F10 -o verificacao_A02
```

Para comparação real com o FTool, **abra a aplicação FTool separadamente** e monte os modelos a partir dos CSVs. O resultado do FTool não está fornecido nem é inventado neste pacote. Após preencher a coluna `valor_FTOOL_PREENCHER`:

```bash
python -m poe_truss.cli compare verificacao_A02/FTool_CONFRONTO_COMPLETO.csv -o confronto.json
```

O comando falha se faltar qualquer resultado comparativo. Tol. provisórias: N e R **0,10% ou 0,01 kN**; deslocamento **0,50% ou 0,02 mm** (maior limite). São critérios de teste a justificar e calibrar conforme a precisão das informações disponíveis no FTool.

Consulte `FTool_GUIA.md` e `CODEX_AUDITORIA.md`.

## 6. Arquivos principais

| Caminho | Função |
|---|---|
| `poe_truss/model.py` | Nós, barras, apoios, geração geométrica, verificações geométricas |
| `poe_truss/loads.py` | Casos de ações e transformação nodal |
| `poe_truss/solver.py` | Matriz de rigidez, LU, análise, forças/reação/deslocamento |
| `poe_truss/engine.py` | Orquestração de casos, combinações e envoltórias |
| `poe_truss/catalog.py` | Perfis, massa e área |
| `poe_truss/units.py` | Conversões nominais internas |
| `poe_truss/export.py` | DimPerfil, FTool e memorial HTML |
| `poe_truss/cli.py` | Execução e confrontação numérica, independente da UI |
| `poe_truss/server.py` | HTTP local, com token e acesso restrito |
| `tests/` | Testes de cálculo, HTTP e ensaio visual opcional |
| `output/verification/ftool/` | Pacotes A02/B01/B02 gerados conforme o [guia do FTool](../FTool_GUIA.md) |

## 7. Continuidade

**Próxima etapa técnica:** validação com FTool de cargas nodais equivalentes, ELS/ELU manual, apoios redundantes e treliças não uniformes; em seguida, biblioteca efetiva de telhas com dados de fabricantes e posicionamento livre de terças, otimização de modulação/painéis/altura, devolutiva DimPerfil e verificações normativas documentadas.
