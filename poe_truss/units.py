"""Unidades: o kgf nominal da POE equivale a 10 N, por exigência do projeto.

ATENÇÃO: esta é convenção nominal (g=10 m/s²), não conversão metrológica
sob gravidade padrão. O motor usa exclusivamente N, mm, MPa.
"""
from __future__ import annotations

FORCE_TO_N = {"kgf": 10.0, "tf": 10000.0, "kN": 1000.0, "N": 1.0}
LENGTH_TO_MM = {"m": 1000.0, "cm": 10.0, "mm": 1.0}


def force_n(value: float, unit: str = "kgf") -> float:
    if unit not in FORCE_TO_N:
        raise ValueError(f"Unidade de força desconhecida: {unit}")
    return float(value) * FORCE_TO_N[unit]


def area_pressure_n_per_mm2(value: float, unit: str = "kgf") -> float:
    """Valor por m² -> N/mm²."""
    return force_n(value, unit) / 1_000_000.0


def line_n_per_mm(value: float, unit: str = "kgf") -> float:
    """Valor por m -> N/mm."""
    return force_n(value, unit) / 1000.0


def length_mm(value: float, unit: str = "m") -> float:
    if unit not in LENGTH_TO_MM:
        raise ValueError(f"Unidade de comprimento desconhecida: {unit}")
    return float(value) * LENGTH_TO_MM[unit]
