"""Leitura dos perfis existentes, preservando procedência e avisos de qualidade."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import csv
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    name: str
    family: str
    area_mm2: float
    mass_kg_m: float
    ix_mm4: float
    iy_mm4: float
    origin: str
    quality: str

    def as_json(self):
        return asdict(self)


def load_catalog(path: Path) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    with open(path, 'r', encoding='utf-8-sig', newline='') as stream:
        for line, r in enumerate(csv.DictReader(stream, delimiter=';'), 2):
            def n(key):
                return float(r[key].replace(',', '.'))
            p = Profile(
                name=r['perfil'], family=r['familia'], area_mm2=n('A_cm2')*100,
                mass_kg_m=n('massa_kg_m'), ix_mm4=n('Ix_cm4')*10_000,
                iy_mm4=n('Iy_cm4')*10_000, origin=r.get('origem',''),
                quality=r.get('qualidade',''))
            if not p.name or p.area_mm2 <= 0 or p.mass_kg_m <= 0:
                raise ValueError(f'Catálogo: perfil inválido na linha {line}')
            if p.name in profiles:
                raise ValueError(f'Catálogo: perfil duplicado na linha {line}')
            profiles[p.name] = p
    if not profiles:
        raise ValueError('Catálogo vazio')
    return profiles
