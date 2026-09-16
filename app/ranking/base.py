"""Ranking strategy base protocol and registry."""

from __future__ import annotations

from typing import Callable, Dict, Type
from app.config import AppConfig
from app.domain.errors import InvalidRequestError
from app.domain.protocols import RankingStrategy

_STRATEGY_REGISTRY: Dict[str, Type[RankingStrategy]] = {}


def register_strategy(name: str) -> Callable[[Type[RankingStrategy]], Type[RankingStrategy]]:
    """Decorator to register a ranking strategy implementation."""
    def decorator(cls: Type[RankingStrategy]) -> Type[RankingStrategy]:
        _STRATEGY_REGISTRY[name] = cls
        return cls
    return decorator


def get_ranking_strategy(name: str, config: AppConfig) -> RankingStrategy:
    """Factory function resolving a ranking strategy instance by name."""
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = list(_STRATEGY_REGISTRY.keys())
        raise InvalidRequestError(
            f"Unknown ranking strategy '{name}'. Available strategies: {available}"
        )
    return cls(config)  # type: ignore[call-arg]
