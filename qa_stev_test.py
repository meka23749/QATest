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