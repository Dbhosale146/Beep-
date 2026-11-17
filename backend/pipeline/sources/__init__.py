"""Source registry.

Adding a source = add one file here that exposes fetch() -> list[dict],
then add one line to SOURCES. Explicit beats auto-discovery: you can see
every active source in one place, and a typo fails loudly at import time.
"""

from . import adzuna, ashby, greenhouse, lever

SOURCES = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "adzuna": adzuna,
}
