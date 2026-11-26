"""Finds every PriceSource in this package and builds one by name."""

import importlib
import pkgutil

from app.config import Settings
from app.sources import base

_discovered = False


def _discover() -> None:
    """Import every module in app/sources so their @register decorators run."""
    global _discovered
    if _discovered:
        return
    import app.sources as pkg

    for module in pkgutil.iter_modules(pkg.__path__):
        if module.name not in {"base", "registry"}:
            importlib.import_module(f"{pkg.__name__}.{module.name}")
    _discovered = True


def available_sources() -> list[str]:
    _discover()
    return sorted(base._REGISTRY)


def create_source(name: str, settings: Settings) -> base.PriceSource:
    _discover()
    cls = base._REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown price source {name!r}. Available: {', '.join(available_sources())}"
        )
    return cls.from_settings(settings)
