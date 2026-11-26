"""Build AI data-platform framing artifacts from local deterministic evidence."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.reports.data_platform import write_data_platform_artifacts


def main() -> None:
    manifest = write_data_platform_artifacts()
    print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
