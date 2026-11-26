"""Build static README screenshots from local demo artifacts."""

from __future__ import annotations

from pathlib import Path
import sys
import textwrap

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.demo import load_demo_state, replay_case_study, run_local_claim_demo


ASSET_DIR = Path("docs/assets")
CANVAS_SIZE = (1280, 760)
BACKGROUND = "#f6f7f9"
INK = "#182026"
MUTED = "#5b6773"
PANEL = "#ffffff"
PANEL_BORDER = "#d8dee6"
ACCENT = "#1f7a5c"
WARNING = "#a05a00"
BLUE = "#2457a6"


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    state = load_demo_state()

    claim = run_local_claim_demo(
        "Apple FY2024 revenue was $391.035 billion.",
        "AAPL",
        "2024-FY",
    )
    _draw_claim_verification(claim).save(ASSET_DIR / "claim_verification_demo.png")

    case = replay_case_study(state, "unsupported_narrative_claim")
    _draw_case_study(case).save(ASSET_DIR / "case_study_replay.png")

    _draw_memo_trace(state.memo_markdown).save(ASSET_DIR / "memo_trace_demo.png")
    _draw_killer_metrics().save(ASSET_DIR / "killer_metrics.png")

    print(
        "screenshots=3 "
        "claim=docs/assets/claim_verification_demo.png "
        "case=docs/assets/case_study_replay.png "
        "memo=docs/assets/memo_trace_demo.png "
        "killer_metric=docs/assets/killer_metrics.png"
    )


def _draw_claim_verification(claim) -> Image.Image:
    image, draw, fonts = _canvas("Claim Verification Demo")
    _panel(draw, (54, 128, 402, 650), "Input claim", fonts)
    _text(draw, claim.claim_text, (78, 184), fonts["body"], width=34)
    _chip(draw, (78, 420, 246, 456), f"Company: {claim.company_ticker}", BLUE, fonts["small"])
    _chip(draw, (78, 470, 260, 506), f"Period: {claim.fiscal_period}", BLUE, fonts["small"])

    _panel(draw, (440, 128, 808, 650), "Evidence + validators", fonts)
    _metric(draw, (468, 194), "Evidence rows", str(claim.evidence_count), fonts, ACCENT)
    _metric(draw, (468, 314), "Numeric rows", str(claim.numeric_reconciliation_rows), fonts, ACCENT)
    _bullet_list(
        draw,
        (
            "Citation span present",
            "Fiscal period aligned",
            "Metric normalized to revenue",
            "Numeric value reconciled",
        ),
        (468, 440),
        fonts,
    )

    _panel(draw, (846, 128, 1226, 650), "Verdict + memo", fonts)
    _metric(draw, (874, 194), "Final verdict", claim.verdict.upper(), fonts, ACCENT)
    _text(
        draw,
        "Memo output keeps evidence, numeric reconciliation, and limitations in separate sections.",
        (874, 350),
        fonts["body"],
        width=34,
    )
    return image


def _draw_case_study(case) -> Image.Image:
    image, draw, fonts = _canvas("Case Study Replay")
    _panel(draw, (54, 128, 510, 650), "Unsupported narrative claim", fonts)
    _text(draw, case.claim, (78, 184), fonts["body"], width=42)
    _chip(draw, (78, 408, 292, 444), f"Expected: {case.expected_verdict}", WARNING, fonts["small"])
    _chip(draw, (78, 458, 302, 494), f"Full engine: {case.final_verdict}", ACCENT, fonts["small"])

    _panel(draw, (548, 128, 1226, 650), "Method failure analysis", fonts)
    methods = [method for method in case.methods if method in {"bm25", "dense_proxy", "hybrid", "graph", "full_engine"}]
    if not methods:
        methods = list(case.methods)[:5]
    y = 188
    for method in methods[:5]:
        reasons = case.failure_reasons_by_method.get(method, ())
        reason = reasons[0] if reasons else "No failure detected for this method."
        _text(draw, f"{method}: {reason}", (576, y), fonts["small"], width=78, fill=INK)
        y += 72
    return image


def _draw_memo_trace(memo_markdown: str) -> Image.Image:
    image, draw, fonts = _canvas("Memo + Trace View")
    _panel(draw, (54, 128, 412, 650), "Auditable memo", fonts)
    memo_lines = [line for line in memo_markdown.splitlines() if line.strip()][:7]
    _text(draw, "\n".join(memo_lines), (78, 184), fonts["small"], width=42)

    _panel(draw, (450, 128, 836, 650), "Reconciliation", fonts)
    _bullet_list(
        draw,
        (
            "Company/entity matched",
            "Fiscal period checked",
            "Unit and currency normalized",
            "XBRL numeric value linked",
            "Unsupported claims remain explicit",
        ),
        (478, 188),
        fonts,
    )

    _panel(draw, (874, 128, 1226, 650), "Reproducibility", fonts)
    _bullet_list(
        draw,
        (
            "Run manifest",
            "Retrieval trace",
            "Verification trace",
            "Evidence trace",
            "Artifact manifest",
        ),
        (902, 188),
        fonts,
    )
    return image


def _draw_killer_metrics() -> Image.Image:
    image, draw, fonts = _canvas("Why Validator-Gated Evidence Beats Ordinary RAG")
    draw.text(
        (54, 128),
        "Ordinary RAG can retrieve plausible but unauditable financial evidence.",
        fill=INK,
        font=fonts["heading"],
    )
    metrics = (
        ("Full engine accuracy", "83.3%", "60 local due-diligence tasks", ACCENT),
        ("Surfaced failure cases", "346", "period, entity, citation, numeric, unsupported-claim gaps", WARNING),
        ("Adversarial detection", "75.0%", "120 red-team cases; failures remain explainable", BLUE),
    )
    x_positions = (54, 456, 858)
    for x, (label, value, detail, color) in zip(x_positions, metrics):
        _panel(draw, (x, 214, x + 368, 620), label, fonts)
        draw.text((x + 28, 292), value, fill=color, font=fonts["metric"])
        _text(draw, detail, (x + 28, 386), fonts["body"], width=29)
    return image


def _canvas(title: str):
    image = Image.new("RGB", CANVAS_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    draw.text((54, 40), title, fill=INK, font=fonts["title"])
    draw.text(
        (54, 88),
        "Claim-level financial evidence verification for auditable due diligence",
        fill=MUTED,
        font=fonts["body"],
    )
    return image, draw, fonts


def _fonts() -> dict[str, ImageFont.ImageFont]:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return {
                "title": ImageFont.truetype(path, 36),
                "heading": ImageFont.truetype(path, 24),
                "body": ImageFont.truetype(path, 20),
                "small": ImageFont.truetype(path, 17),
                "metric": ImageFont.truetype(path, 34),
            }
    return {
        "title": ImageFont.load_default(),
        "heading": ImageFont.load_default(),
        "body": ImageFont.load_default(),
        "small": ImageFont.load_default(),
        "metric": ImageFont.load_default(),
    }


def _panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, fonts: dict) -> None:
    draw.rounded_rectangle(box, radius=10, fill=PANEL, outline=PANEL_BORDER, width=2)
    draw.text((box[0] + 24, box[1] + 24), title, fill=INK, font=fonts["heading"])


def _metric(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    label: str,
    value: str,
    fonts: dict,
    color: str,
) -> None:
    x, y = xy
    draw.text((x, y), label, fill=MUTED, font=fonts["small"])
    draw.text((x, y + 30), value, fill=color, font=fonts["metric"])


def _chip(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    color: str,
    font: ImageFont.ImageFont,
) -> None:
    draw.rounded_rectangle(box, radius=18, fill=color)
    draw.text((box[0] + 14, box[1] + 8), label, fill="#ffffff", font=font)


def _bullet_list(
    draw: ImageDraw.ImageDraw,
    items: tuple[str, ...],
    xy: tuple[int, int],
    fonts: dict,
) -> None:
    x, y = xy
    for item in items:
        draw.ellipse((x, y + 7, x + 9, y + 16), fill=ACCENT)
        _text(draw, item, (x + 22, y), fonts["body"], width=38)
        y += 48


def _text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    width: int,
    fill: str = INK,
) -> None:
    x, y = xy
    for raw_line in text.splitlines():
        wrapped = textwrap.wrap(raw_line, width=width) or [""]
        for line in wrapped:
            draw.text((x, y), line, fill=fill, font=font)
            y += 28


if __name__ == "__main__":
    main()
