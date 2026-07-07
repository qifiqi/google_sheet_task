#!/usr/bin/env python3
"""Direct script entry for the DingTalk stream microservice."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ding_stream_service.main import main


if __name__ == "__main__":
    main()
