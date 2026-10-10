"""Guided wizard for people who do not use the command line. Entry: digitize.py -> main(argv)."""


def main(argv):
    from .app import main as _main
    return _main(argv)
