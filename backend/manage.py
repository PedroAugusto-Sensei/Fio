#!/usr/bin/env python
"""Utilitário de linha de comando do Django."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fio.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Não foi possível importar o Django. Ele está instalado e o ambiente "
            "virtual está ativo?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
