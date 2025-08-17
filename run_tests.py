"""Fallback test runner utilizzando unittest.

Se pytest non è disponibile, questo script permette di eseguire i test
del progetto dalla riga di comando. I test vengono scoperti nella
cartella ``tests`` relativa al file corrente.

Eseguire con:

    python run_tests.py
"""

from __future__ import annotations

import os
import sys
import unittest


def main() -> None:
    # Determina la directory base: il file si trova nella root del progetto
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = os.path.join(base_dir, 'tests')
    # Aggiunge la base_dir al sys.path per consentire import interni
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tests_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == '__main__':
    main()