"""Package tools: utilità e script di supporto per il progetto.

Questo package fornisce script vari utilizzati all'interno del progetto.
L'aggiunta di questo file consente di importare correttamente i
sottoscritti, ad esempio `from tools.import_sql import import_sql`.
"""

from .import_sql import import_sql  # type: ignore[F401]
