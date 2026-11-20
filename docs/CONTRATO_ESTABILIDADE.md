# Especificação v0.3 — `stability` no JSON

`stability` é **opcional** e não altera o solver 2D. O motor calcula esforços como antes. O módulo complementar gera parâmetros **declarados** para posterior verificação axial.

```json
{
  "stability": {
    "groups": {
      "superior": {
        "unbraced_in_plane_mm": 1000,
        "unbraced_out_of_plane_mm": null,
        "torsion_unbraced_mm": 4000,
        "k_in_plane": 1.0,
        "k_out_of_plane": 1.0,
        "rotation_deg": 0,
        "axis_in_plane": "x",
        "axis_out_of_plane": "y",
        "restraint_note": "Plano físico e desenho de travamento",
        "restraint_reference": "Documento do projetista, desenho nº ..."
      }
    },
    "members": {
      "M002": {"unbraced_out_of_plane_mm": 2500, "k_out_of_plane": 1.1}
    },
    "lateral_bracing": [{
      "group": "superior",
      "node_ids": ["T00", "T04", "T08", "T12", "T16"],
      "assumed_effective": true,
      "reference": "Hipótese declarada; verificação independente do contraventamento exigida"
    }]
  }
}
```

## Precedência

1. `groups` define propriedades padrão por grupo;
2. `members` sobrepõe cada campo no grupo correspondente;
3. comprimento lateral por barra ou grupo explícito prevalece sobre a inferência geométrica entre travamentos;
4. se ausente, o módulo infere comprimento lateral **apenas** entre pares de nós de uma linha de banzo com `assumed_effective=true`, anotando fonte da hipótese;
5. sem condições suficientes, o comprimento lateral é `null` e a barra recebe `state=PENDENTE`.

A distância entre travamentos em banzo é medida **ao longo da poligonal da barra**, não pela projeção horizontal. Os nós indicados devem formar parte da mesma cadeia sem ramificações; intervalos fora dos extremos travados ficam pendentes.

O campo opcional `nodal_restraints` guarda as marcas do editor de nós por ID. Cada item tem `reference` e `confirmed`. Dois nós confirmados no mesmo banzo formam uma hipótese de comprimento lateral para as barras no intervalo. Marcas pendentes sobrevivem à edição geométrica para revisão. O comprimento explícito e uma declaração efetiva de banzo em `lateral_bracing` têm precedência. O resultado registra as duas extremidades do intervalo e as referências com origem `nodal_declared`.

## Propriedades das seções

O catálogo atual traz A, Ix e Iy, mas não caracteriza de forma completa o comportamento à flambagem flexo-torcional, empenamento ou instabilidade distorcional. O módulo não emprega aproximações para Ixy ou propriedade transversal de uma seção composta. Para U e UE **simples**, sem rotação, apresenta raios geométricos de referência quando os eixos são informados. Para seções **duplas**, seções **rotacionadas** e **cantoneiras** (Ixy/eixos principais faltantes), os índices relacionados às propriedades indisponíveis permanecem pendentes.

`rotation_deg` registra a orientação, mas **não transforma tensor de inércia** sem Ixy; não supor Ix e Iy como eixos principais de cantoneira isolada. `torsion_unbraced_mm` só registra a hipótese; não executa cálculo torsional.

## Estados e limites

`DADOS_DECLARADOS`: todas as condições documentais mínimas do módulo foram informadas. **Não significa atendimento ao ELU nem estabilidade comprovada.**

`PENDENTE`: uma ou mais informações necessárias à futura verificação não foram informadas, como travamento, eixo, comprimento torsional ou arranjo geométrico completo.

`resistance_verified`: sempre **false** nesta versão.

Os resultados dos esforços da estrutura **não se alteram** quando `stability` muda; condições fora do plano somente participarão das futuras verificações de resistência e otimização.
