"""Run the A1 demo from its historical source entry point."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from financial_evidence_engine.streamlit_app import main

if __name__ == "__main__":
    main()
