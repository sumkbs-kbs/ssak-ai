"""Prometheus metrics registry and ASGI app for the Ssak-Ai API.

Exposes standard RED (Rate, Errors, Duration) metrics for HTTP requests plus a
few process-level gauges. The metrics are served at ``/metrics`` via the
``prometheus_client`` ASGI app, mounted in ``server.py``.

This module is intentionally side-effect-free at import time: the metric
objects are created on first access so that importing it in a test does not
register duplicate collectors.
"""

from __future__ import annotations

import importlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar, cast

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.metrics import MetricWrapperBase

_T = TypeVar("_T", bound=MetricWrapperBase)

logger = logging.getLogger(__name__)

# Use a dedicated registry so we do not accidentally pick up unrelated
# collectors from third-party libraries that register on the default.
REGISTRY = CollectorRegistry()

# Metric name constants — kept short to keep the exposition compact.
_REQUEST_COUNT = "http_requests_total"
_REQUEST_LATENCY = "http_request_duration_seconds"
_REQUESTS_IN_FLIGHT = "http_requests_in_flight"
_LLM_CALL_COUNT = "llm_calls_total"
_LLM_ERROR_COUNT = "llm_errors_total"
_VAULT_WRITE_COUNT = "vault_writes_total"
_UPTIME = "process_uptime_seconds"

_metrics: dict[str, MetricWrapperBase] = {}
_START_TIME = time.time()
_ASGIApp: TypeAlias = Callable[..., Awaitable[object]]


def _get_or_create(name: str, factory: Callable[[], _T]) -> _T:
    """Lazily create a metric on first access, caching it in ``_metrics``."""
    if name not in _metrics:
        _metrics[name] = factory()
    return cast(_T, _metrics[name])


def request_counter() -> Counter:
    """Total HTTP requests by method, path template, and status code."""

    def _make() -> Counter:
        return Counter(
            _REQUEST_COUNT,
            "Total HTTP requests processed.",
            labelnames=("method", "path", "status"),
            registry=REGISTRY,
        )

    return _get_or_create(_REQUEST_COUNT, _make)


def request_latency() -> Histogram:
    """HTTP request latency in seconds."""

    def _make() -> Histogram:
        return Histogram(
            _REQUEST_LATENCY,
            "HTTP request latency in seconds.",
            labelnames=("method", "path"),
            buckets=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
                float("inf"),
            ),
            registry=REGISTRY,
        )

    return _get_or_create(_REQUEST_LATENCY, _make)


def requests_in_flight() -> Gauge:
    """Number of HTTP requests currently being processed."""

    def _make() -> Gauge:
        return Gauge(
            _REQUESTS_IN_FLIGHT,
            "Number of HTTP requests currently in flight.",
            registry=REGISTRY,
        )

    return _get_or_create(_REQUESTS_IN_FLIGHT, _make)


def llm_call_counter() -> Counter:
    """Total LLM inference calls by provider and model."""

    def _make() -> Counter:
        return Counter(
            _LLM_CALL_COUNT,
            "Total LLM inference calls.",
            labelnames=("provider", "model"),
            registry=REGISTRY,
        )

    return _get_or_create(_LLM_CALL_COUNT, _make)


def llm_error_counter() -> Counter:
    """Total LLM inference errors by provider and model."""

    def _make() -> Counter:
        return Counter(
            _LLM_ERROR_COUNT,
            "Total LLM inference errors.",
            labelnames=("provider", "model"),
            registry=REGISTRY,
        )

    return _get_or_create(_LLM_ERROR_COUNT, _make)


def vault_write_counter() -> Counter:
    """Total vault note writes (successful commits)."""

    def _make() -> Counter:
        return Counter(
            _VAULT_WRITE_COUNT,
            "Total successful vault note writes.",
            labelnames=("result",),
            registry=REGISTRY,
        )

    return _get_or_create(_VAULT_WRITE_COUNT, _make)


def uptime_gauge() -> Gauge:
    """Process uptime in seconds (set on each scrape)."""

    def _make() -> Gauge:
        return Gauge(_UPTIME, "Process uptime in seconds.", registry=REGISTRY)

    return _get_or_create(_UPTIME, _make)


def render_metrics() -> bytes:
    """Render the current metric values in the Prometheus exposition format."""
    uptime_gauge().set(time.time() - _START_TIME)
    return generate_latest(REGISTRY)


def metrics_asgi_app() -> _ASGIApp:
    """Return the prometheus_client ASGI app for mounting at /metrics."""
    module = importlib.import_module("prometheus_client")
    factory = cast(Callable[..., _ASGIApp], getattr(module, "make_asgi_app"))
    return factory(registry=REGISTRY)
