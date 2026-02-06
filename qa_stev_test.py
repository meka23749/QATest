#!/usr/bin/env python3
"""

Small QA stability test runner:
- Sends repeated HTTP requests
- Measures latency + availability
- Writes logs (file + console)
- Creates a JSON report
- Optionally captures docker logs for quick debugging context
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

try:
    import requests
except ImportError:
    print("Dependency missing: requests. Install with: pip install requests", file=sys.stderr)
    raise SystemExit(2)

@dataclass
class Result:
    ts_utc: str
    ok: bool
    status_code: Optional[int]
    latency_ms: Optional[float]
    error: Optional[str]

def utc_now() -> str:
    """Return UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def setup_logging(log_path: str, verbose: bool) -> None:
    """Configure logging to write both to a file and to the console."""
    level = logging.DEBUG if verbose else logging.INFO # DEBUG shows everything, INFO shows only important messages
    logging.basicConfig(
        level=level,
        format="%(asctime)sZ %(levelname)s %(message)s",  
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            # Handlers define where logs are sent
            # Write logs to a file (UTF-8 to support all characters)
            logging.FileHandler(log_path, encoding="utf-8"),

            # Also print logs to standard output (terminal)
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.info("Logging initialized. log_path=%s verbose=%s", log_path, verbose)

    

def docker_logs(container: str, tail: int = 120) -> Optional[str]:
    """Fetch last docker logs lines for debugging context (if docker is available)."""
    try:
        out = subprocess.check_output(
            ["docker", "logs", "--tail", str(tail), container],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
        return out
    except Exception as e:
        logging.debug("Could not read docker logs for '%s': %s", container, e)
        return None

def probe(url: str, timeout_s: float, expected: Optional[str]) -> Result:
    """One HTTP GET probe with basic validation + latency measurement."""
    ts = utc_now()
    t0 = time.perf_counter()

    try:
        r = requests.get(url, timeout=timeout_s)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if expected and expected not in r.text:
            return Result(ts, False, r.status_code, latency_ms, f"Expected '{expected}' not found")

        if 200 <= r.status_code < 300:
            return Result(ts, True, r.status_code, latency_ms, None)

        return Result(ts, False, r.status_code, latency_ms, f"Non-2xx status: {r.status_code}")

    except requests.RequestException as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return Result(ts, False, None, latency_ms, str(e))