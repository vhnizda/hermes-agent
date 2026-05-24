"""Conservative model routing helpers.

This module intentionally does not hot-swap the main interactive agent.  It is
for separate runs (cron jobs, one-shots, scripts, and future helper agents)
where a caller can ask for a task class and receive the configured provider /
model pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from hermes_cli.config import load_config


TaskClass = str


@dataclass(frozen=True)
class RoutedModel:
    provider: str
    model: str
    task_class: TaskClass
    reason: str
    uses_default: bool = False
    routing_enabled: bool = False


def _model_pair_from_config(model_cfg: Any) -> Tuple[str, str]:
    if isinstance(model_cfg, dict):
        provider = str(model_cfg.get("provider") or "").strip()
        model = str(model_cfg.get("default") or model_cfg.get("name") or "").strip()
        return provider, model
    return "", str(model_cfg or "").strip()


def get_model_routing_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = config if config is not None else load_config()
    routing = cfg.get("model_routing")
    if not isinstance(routing, dict):
        routing = {}
    main_provider, main_model = _model_pair_from_config(cfg.get("model", {}))
    default_raw = routing.get("default_model")
    cheap_raw = routing.get("cheap_model")
    critical_raw = routing.get("critical_model")
    default_cfg: Dict[str, Any] = default_raw if isinstance(default_raw, dict) else {}
    cheap_cfg: Dict[str, Any] = cheap_raw if isinstance(cheap_raw, dict) else {}
    critical_cfg: Dict[str, Any] = critical_raw if isinstance(critical_raw, dict) else {}
    return {
        "enabled": bool(routing.get("enabled", False)),
        "policy": str(routing.get("policy") or "conservative"),
        "auto_route_no_agent_scripts": bool(routing.get("auto_route_no_agent_scripts", False)),
        "default_model": {
            "provider": str(default_cfg.get("provider") or main_provider or "").strip(),
            "model": str(default_cfg.get("model") or main_model or "").strip(),
        },
        "cheap_model": {
            "provider": str(cheap_cfg.get("provider") or main_provider or "").strip(),
            "model": str(cheap_cfg.get("model") or "").strip(),
        },
        "critical_model": {
            "provider": str(critical_cfg.get("provider") or main_provider or "").strip(),
            "model": str(critical_cfg.get("model") or main_model or "").strip(),
        },
        "rules": routing.get("rules") if isinstance(routing.get("rules"), dict) else {},
    }


def route_model_for_task(
    task_class: Optional[TaskClass] = None,
    *,
    job: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> RoutedModel:
    """Resolve provider/model for a task class using conservative routing.

    Explicit job provider/model always wins.  If routing is disabled or the task
    is not safely classed as ``simple``, the default/critical model is returned.
    """
    cfg = config if config is not None else load_config()
    routing = get_model_routing_config(cfg)

    if job:
        explicit_model = str(job.get("model") or "").strip()
        explicit_provider = str(job.get("provider") or "").strip()
        if explicit_model:
            return RoutedModel(
                provider=explicit_provider or routing["default_model"]["provider"],
                model=explicit_model,
                task_class=str(job.get("routing_class") or task_class or "explicit"),
                reason="explicit job model override",
                uses_default=False,
                routing_enabled=routing["enabled"],
            )
        if not task_class:
            task_class = str(job.get("routing_class") or "").strip() or None
        if not task_class and routing["auto_route_no_agent_scripts"] and job.get("no_agent") and job.get("script"):
            task_class = "simple"

    task = str(task_class or "critical").strip().lower()
    default = routing["default_model"]
    critical = routing["critical_model"] or default
    cheap = routing["cheap_model"]

    if routing["enabled"] and task == "simple" and cheap.get("model"):
        return RoutedModel(
            provider=cheap.get("provider") or default.get("provider") or "",
            model=cheap["model"],
            task_class="simple",
            reason="conservative router: simple task",
            uses_default=False,
            routing_enabled=True,
        )

    return RoutedModel(
        provider=critical.get("provider") or default.get("provider") or "",
        model=critical.get("model") or default.get("model") or "",
        task_class=task or "critical",
        reason="conservative router: default/critical fallback",
        uses_default=True,
        routing_enabled=routing["enabled"],
    )
