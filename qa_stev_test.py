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

def percentile(sorted_vals: List[float], p: float) -> Optional[float]:
    """Nearest-rank percentile on sorted list."""
    if not sorted_vals:
        return None
    idx = int(round((p / 100.0) * (len(sorted_vals) - 1))) #Compute the percentile index (rounded to the nearest rank)
    idx = max(0, min(idx, len(sorted_vals) - 1)) # Prevent index out of range
    return float(sorted_vals[idx])

def main() -> int:
    ap = argparse.ArgumentParser(description="QA smoke/stability tester for an HTTP endpoint.")
    ap.add_argument("--url", required=True, help="Target URL, e.g. http://localhost:8080/health")
    ap.add_argument("--duration", type=int, default=60, help="How long to test (seconds)")
    ap.add_argument("--interval", type=float, default=1.0, help="Seconds between requests")
    ap.add_argument("--timeout", type=float, default=2.0, help="HTTP timeout in seconds")
    ap.add_argument("--expected", default=None, help="Expected substring in response body (optional)")
    ap.add_argument("--log", default="qa_test.log", help="Log file path")
    ap.add_argument("--out", default="qa_report.json", help="Output JSON report")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = ap.parse_args()

    setup_logging(args.log, args.verbose)  # Initialize logging system (file + console)

    start_ts = utc_now()                   # Record test start time in UTC (ISO format)
    start_perf = time.perf_counter()       # Start precision timer for duration measurement

    results: List[Result] = []             # List to store individual probe results

    end_time = start_perf + max(1, args.duration)  # Compute test end time (minimum 1 second)

    i = 0
    while time.perf_counter() < end_time:
        i += 1
        res = probe(args.url, args.timeout, args.expected)
        results.append(res)

        if res.ok:
            logging.info("OK   #%d status=%s latency_ms=%.2f", i, res.status_code, res.latency_ms or -1.0)
        else:
            logging.warning("FAIL #%d status=%s latency_ms=%s err=%s", i, res.status_code, res.latency_ms, res.error)

        time.sleep(max(0.0, args.interval))

    end_ts = utc_now()
    duration_s = time.perf_counter() - start_perf

    ok_count = sum(1 for r in results if r.ok)
    total = len(results)
    fail_count = total - ok_count
    availability = (ok_count / total * 100.0) if total else 0.0

    lat = sorted([r.latency_ms for r in results if r.ok and r.latency_ms is not None])
    p50 = percentile(lat, 50)
    p95 = percentile(lat, 95)

    report: Dict[str, Any] = {
        "meta": {"tool": "qa_smoke_test", "version": "1.0"},
        "summary": {
            "url": args.url,
            "start_ts_utc": start_ts,
            "end_ts_utc": end_ts,
            "duration_s": round(duration_s, 3),
            "total_requests": total,
            "ok_requests": ok_count,
            "fail_requests": fail_count,
            "availability_pct": round(availability, 2),
            "p50_latency_ms": round(p50, 2) if p50 is not None else None,
            "p95_latency_ms": round(p95, 2) if p95 is not None else None,
            "min_latency_ms": round(lat[0], 2) if lat else None,
            "max_latency_ms": round(lat[-1], 2) if lat else None,
        },
        "results": [asdict(r) for r in results],
    }