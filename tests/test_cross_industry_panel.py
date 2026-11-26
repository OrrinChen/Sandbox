from pathlib import Path
import runpy

build = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/build_cross_industry_panel.py")
)


def test_roster_is_order_independent_and_uses_only_eligible_filings():
    rows = []
    for idx, (_, ranges) in enumerate(build["SECTORS"].items(), 1):
        for j in range(7):
            rows.append(
                dict(
                    form="10-K",
                    cik=str(idx * 100 + j),
                    name=f"Issuer {idx}/{j}",
                    sic=str(ranges[0][0]),
                    countryba="US",
                    countryinc="US",
                    afs="1-LAF",
                    filed="20200302",
                    accepted="2020-03-02 11:00:00",
                    adsh=f"id-{idx}-{j}",
                )
            )
    rows.extend(
        [
            dict(rows[0], cik="27419"),
            dict(rows[0], cik="123", filed="20210101"),
            dict(rows[1], cik="124", form="10-K/A"),
            dict(rows[0], cik="125", countryinc="CA"),
        ]
    )
    # Last pre-cutoff filing controls eligibility even when an earlier one would qualify.
    rows.extend([dict(rows[0], cik="999"), dict(rows[0], cik="999", filed="20201210", afs="4-NON")])
    companies, pools = build["select"](rows)
    assert (companies, pools) == build["select"](list(reversed(rows)))
    assert set(pools.values()) == {7} and len({r["cik"] for r in companies}) == 36
    panel = build["observations"](companies)
    assert len({(r["cik"], r["cutoff_us_eastern"]) for r in panel}) == len(panel) == 432
    assert (
        panel[0]["cutoff_us_eastern"] == "2021-03-31" and panel[-1]["cutoff_us_eastern"] == "2023-12-31"
    )
