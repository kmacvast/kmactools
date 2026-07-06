#!/usr/bin/env python3
"""Shared lifecycle, signal, and rendering helpers for vast-opstat engines.

Centralizes the cross-cutting concerns that were previously copy-pasted into
each protocol engine: VMS monitor teardown tracking, signal/atexit wiring
(including SIGHUP), local-cluster selection, and flicker-free frame flushing.
"""

import atexit
import signal
import sys

# ---------------------------------------------------------------------------
# Monitor lifecycle registry
# ---------------------------------------------------------------------------
# Every monitor created via a protocol engine is registered here the instant
# the VMS returns an id. Teardown drains this set, so a partially-created
# monitor group (or an unexpected exit path) can never orphan monitors.
_CREATED_MONITORS = set()
_FAILED_DELETES = []


def register_monitor(monitor_id):
    """Record a freshly-created monitor id; returns it for call-site chaining."""
    if monitor_id is not None:
        _CREATED_MONITORS.add(monitor_id)
    return monitor_id


def forget_monitor(monitor_id):
    """Drop a monitor id from the registry (after it has been deleted)."""
    _CREATED_MONITORS.discard(monitor_id)


def drain_monitors(delete_fn):
    """Delete every still-registered monitor using engine-supplied delete_fn."""
    for monitor_id in list(_CREATED_MONITORS):
        delete_fn(monitor_id)
        _CREATED_MONITORS.discard(monitor_id)


def record_failed_delete(monitor_id, detail):
    """Note a DELETE that failed for a non-404 reason, for exit reporting."""
    _FAILED_DELETES.append((monitor_id, detail))


def failed_deletes():
    """Return list of (monitor_id, detail) for deletes that truly failed."""
    return list(_FAILED_DELETES)


def reset_registry():
    """Clear registry + failure log (used between sessions and in tests)."""
    _CREATED_MONITORS.clear()
    _FAILED_DELETES.clear()


# ---------------------------------------------------------------------------
# Cluster selection
# ---------------------------------------------------------------------------
def select_local_cluster(clusters):
    """Pick the local/current cluster by explicit boolean fields.

    Avoids the fragile ``'"local": true' in json.dumps(...)`` string match by
    reading the fields directly. Falls back to the first cluster.
    """
    if not clusters:
        return None
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        for key in ("local", "is_local", "current"):
            if cluster.get(key) is True:
                return cluster
    return clusters[0]


# ---------------------------------------------------------------------------
# Signal + atexit wiring
# ---------------------------------------------------------------------------
def install_signal_handlers(handler):
    """Route SIGINT, SIGTERM, and SIGHUP to *handler* where supported."""
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            # SIGHUP unavailable on some platforms; non-main-thread guard.
            pass


def register_atexit(cleanup_fn):
    """Register *cleanup_fn* as an interpreter-exit backstop."""
    atexit.register(cleanup_fn)


# ---------------------------------------------------------------------------
# Frame rendering
# ---------------------------------------------------------------------------
def flush_frame(text):
    """Write one composed frame with a single syscall.

    Homes the cursor (no full-screen erase, so there is no blank interval),
    writes the whole frame, then erases from the cursor to end-of-screen to
    clear any stale tail from a previous, longer frame. This removes the
    screen tearing caused by ``\\033[2J`` + many per-line prints.
    """
    sys.stdout.write("\033[H" + text + "\033[J")
    sys.stdout.flush()
