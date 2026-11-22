"""Graus de referência para o material uniforme do modelo axial."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SteelGrade:
    name: str
    standard: str
    fy: int
    fu: int
    source: str
    product: str
    E: int = 200_000


CFQ = 'Usiminas · catálogo Tiras a Quente, edição 2020'
ROLLED = 'Gerdau · Barras e Perfis, propriedades mecânicas referenciais'
SHAPES = 'Gerdau · Perfis Estruturais W e HP'

STEEL_GRADES = {
    'cfq210': SteelGrade('CFQ210', 'ABNT NBR 6650', 210, 340, CFQ, 'Chapa de 1,80 a 5,00 mm'),
    'cfq250': SteelGrade('CFQ250', 'ABNT NBR 6650', 250, 400, CFQ, 'Chapa de 1,80 a 5,00 mm'),
    'cfq280': SteelGrade('CFQ280', 'ABNT NBR 6650', 280, 440, CFQ, 'Chapa de 1,80 a 5,00 mm'),
    'cfq300': SteelGrade('CFQ300', 'ABNT NBR 6650', 300, 450, CFQ, 'Chapa de 1,80 a 5,00 mm'),
    'mr250': SteelGrade('MR 250', 'ABNT NBR 7007', 250, 400, ROLLED, 'Laminados'),
    'ar350': SteelGrade('AR 350', 'ABNT NBR 7007', 350, 450, ROLLED, 'Laminados'),
    'ar415': SteelGrade('AR 415', 'ABNT NBR 7007', 415, 520, ROLLED, 'Laminados'),
    'a572gr50': SteelGrade('A572 Grau 50', 'ASTM A572', 345, 450, SHAPES, 'Laminados W/H/HP Gerdau'),
}
