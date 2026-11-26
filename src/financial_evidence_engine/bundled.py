"""Read-only A1 sample inputs installed alongside the engine code."""

from pathlib import Path


RESOURCES = Path(__file__).resolve().parent / "resources"
DECK_FIXTURE = RESOURCES / "fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf"
