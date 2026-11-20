"""Formatação e seleção de resultados para a interface."""
from math import hypot

EXTREMES = (('max_tension_n', 'tension_case', 'Tração'),
            ('max_compression_n', 'compression_case', 'Compressão'))


def envelope_rank(extremes):
    return max(extremes['max_tension_n'], abs(extremes['max_compression_n']))


def envelope_values(extremes, units, *, unit=True):
    return tuple(units.force_text(extremes[key], signed=True, unit=unit) if extremes[case] else '—'
                 for key, case, _ in EXTREMES)


def envelope_details(extremes, units):
    return [(title, f'{value} · {extremes[case]}' if extremes[case] else value)
            for (_, case, title), value in zip(EXTREMES, envelope_values(extremes, units))]


def displacement_resultant(delta):
    return hypot(delta['ux_mm'], delta['uy_mm'])


def displacement_peaks(displacements):
    """Um nó representativo por extremo de Y e pelo maior deslocamento total."""
    if not displacements:
        return {}
    rows = list(displacements.items())
    upward = max(rows, key=lambda row: row[1]['uy_mm'])
    downward = min(rows, key=lambda row: row[1]['uy_mm'])
    resultant = max(rows, key=lambda row: displacement_resultant(row[1]))
    peaks = {}
    for node, label, value, direction, signed in (
        (upward[0], '↑ Uy', upward[1]['uy_mm'], 1, True),
        (downward[0], '↓ Uy', downward[1]['uy_mm'], -1, True),
        (resultant[0], 'Máx. |u|', displacement_resultant(resultant[1]), 1, False),
    ):
        if direction * value > 1e-9:
            peaks.setdefault(node, []).append((label, value, signed))
    return peaks


def nodal_displacement_text(node, delta, units, *, compact=False):
    ux = units.displacement_text(delta['ux_mm'], signed=True)
    uy = units.displacement_text(delta['uy_mm'], signed=True)
    total = units.displacement_text(displacement_resultant(delta))
    if compact:
        return f'{node} · |u| {total}\nUx {ux} · Uy {uy}'
    return f'{node} · Ux {ux} · Uy {uy} · |u| {total}'
