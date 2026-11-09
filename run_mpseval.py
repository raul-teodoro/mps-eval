"""Ponto de entrada do executável (PyInstaller).

O PyInstaller executa o script de entrada como módulo de topo, o que quebra os
imports relativos de mpseval/__main__.py. Este arquivo importa o pacote de forma
absoluta e delega para a função main().
"""
from mpseval.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
