# FTool — protocolo de validação cruzada (2DTruss Python v0.1.0)

## Status

**Referências analíticas: verificadas por testes automatizados. Resultados numéricos efetivamente produzidos no FTool: PENDENTES.**

Os CSVs foram preparados para reproduzir a geometria e os carregamentos no FTool; **não são arquivos nativos de projeto FTool**. Não confundir saída POE com referência FTool.

## Benchmark A02 — triângulo (prioridade obrigatória)

- Nós: A(0,0), B(4,0), C(2,1,5) em m.
- Barras: AB, AC, BC; E = 200 GPa; área A = 10 cm² cada.
- Apoios: A restrito X/Y; B restrito somente Y.
- Ação: nó C; FY = −10 kN.
- Convenção POE: tração positiva; compressão negativa.

| Resultado analítico | Valor |
|---|---:|
| AB | +6,666667 kN |
| AC e BC | −8,333333 kN |
| RAY e RBY | +5,000000 kN |
| RAX | 0 kN |
| UX(C) | +0,066667 mm |
| UY(C) | −0,262500 mm |
| UX(B) | +0,133333 mm |

**Atenção ao grau de liberdade horizontal:** geometria e carga simétricas NÃO implicam UX(C)=0 quando somente a extremidade A bloqueia X; o apoio B permite deslocamento horizontal.

A flecha do nó C é verificável por energia de deformação / trabalho virtual:

\[\delta_{C,Y}=-\frac{(6.666,667)^2(4.000)+2(8.333,333)^2(2.500)}{10.000(200.000)(1.000)}=-0,2625\text{ mm}.\]

A fórmula considera as magnitudes de N em newtons (valores apresentados com pontuação decimal brasileira acima).

## Benchmark B01 — Pratt com 16 painéis

Arquivo `examples/cobertura_duas_aguas.json`; caso `S_GRAV`.

- Treliça de 16 m, duas águas, altura base 1,10 m e elevação de cumeeira 1,20 m.
- Área de influência definida por distância entre pórticos de 5 m.
- Barras por grupo com E=200 GPa, área multiplicada pelas seções duplas.
- Forças **nodais** no arquivo `verification/FTool_B01_Pratt_cobertura/nodes.csv` (kN).
- Apoios no arquivo `supports.json`.
- Confronte esforços N, reações e deslocamentos nos nós para a combinação selecionada.

## Benchmark B02 — sucção com componentes horizontais

Mesmo modelo B01, estado `W_UP` apenas. Os esforços nodais são gerados pela pressão normal à superfície inclinada.

Verificar particularmente componentes FX, FY e o balanço das reações horizontais. O cálculo simplificado de vento **não equivale ao procedimento da NBR 6123**.

## Montagem no FTool

1. Registrar o número de versão do FTool utilizado e sua edição.
2. Definir as unidades do FTool com cuidado. Coordenadas e comprimentos nos CSVs estão em m, esforços em kN, áreas em cm², módulo E em MPa (200.000 MPa = 200 GPa).
3. Reproduzir **exatamente** os nós e conectividades fornecidos em `nodes.csv` e `members.csv`.
4. Configurar o modelo como treliça plana ideal: barras axiais/articuladas. Caso o FTool use elemento de pórtico, ajustar as liberações de momento com estabilidade e consistência apropriadas ao tipo de ligação.
5. Configurar as restrições em `supports.json`: UX e UY são **independentes**.
6. Aplicar as cargas nodais FX e FY do caso selecionado; não aplicar cargas distribuídas adicionais nem autopeso automático no FTool para os casos em que os CSVs já incorporam a parcela G1.
7. Coletar N por barra, UX/UY por nó e RX/RY em apoios. Verificar e, se necessário, adaptar **apenas a convenção do sinal do esforço normal** antes de comparar.
8. Copiar os valores efetivamente obtidos no FTool para a coluna vazia `valor_FTOOL_PREENCHER` de `FTool_CONFRONTO_COMPLETO.csv`.
9. Executar `python -m poe_truss.cli compare <arquivo CSV preenchido> -o resultado.json`.
10. Arquivar o projeto real do FTool, captura de tela, versão e planilha comparada. Sem essa documentação o benchmark permanece pendente.

## Tolerâncias iniciais (não são tolerâncias normativas)

| Resultado | Critério |
|---|---|
| Normal N | maior entre 0,10% e 0,01 kN |
| Reação R | maior entre 0,10% e 0,01 kN |
| Deslocamentos UX/UY | maior entre 0,50% e 0,02 mm |

A comparação requer todas as linhas preenchidas, inclusive zeros. O código não marca nenhuma comparação como validada se o FTool não tiver fornecido resultados.

## Testes complementares propostos

- A01 barra isolada com restrição transversal na extremidade livre.
- A03 inversão de cargas.
- A04 rigidez dobrada.
- C01 dois apoios em Y sem X: instabilidade.
- C02 mudança de vinculação XY do lado esquerdo para o direito.
- C03 apoios intermediários e estruturas hiperestáticas estáveis.
- C04 perfis duplos com áreas equivalentes.
- C05 vento assimétrico sobre uma água.
