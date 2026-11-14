"""Núcleo Python 2D do 2DTruss.

O nome interno ``poe_truss`` permanece para preservar imports e compatibilidade
com projetos existentes; a identificação pública é 2DTruss v0.1.
O sistema usa N, mm e MPa e a convenção de 1 kgf = 10 N.
Sem homologação para dimensionamento ELU executivo.
"""
from .version import VERSION as __version__
