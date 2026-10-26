"""Connectors read data from supplier portals. Each one is a module with:

    NAME: str                      – 'zsd'
    LABEL: str                     – shown in Nastavenia
    def run(days: int) -> dict     – fetches the last `days` days for every service mapped to
                                     this connector and writes `readings`; returns a summary

Credentials come from `settings`; mapping lives on `services.connector` / `connector_ref`.
Heavy connectors (headless browser) run their fetch in a subprocess so the memory goes back
to the OS when they are done (standard-features § H)."""
from . import zsd

REGISTRY = {zsd.NAME: zsd}
