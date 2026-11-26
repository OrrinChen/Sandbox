"""Cutoff-dated Federal Reserve, BLS and federal scholarship evaluation records."""
from __future__ import annotations


def excerpt(source: str, date: str, url: str, locator: str, text: str) -> dict:
    return dict(source=source, published=date, url=url, locator=locator, text=text)


def task(dimension: str, cutoff: str, question: str, evidence: list[dict],
         choice: str, value: str | None, refs: str, forecast: dict | None = None) -> dict:
    row = dict(dimension=dimension, cutoff=cutoff, question=question, evidence=evidence,
               gold=dict(choice=choice, value=value, citations=[list(refs)]))
    if forecast:
        row["forecast"] = forecast
    return row


def forecast(question: str, binary_outcome: int, resolution_date: str, url: str) -> dict:
    return dict(question=question, binary_outcome=binary_outcome, resolution_date=resolution_date, url=url)


def fed(date: str, suffix: str, locator: str, text: str) -> dict:
    title = "Federal Reserve implementation note" if suffix == "a1" else "FOMC statement"
    url = f"https://www.federalreserve.gov/newsevents/pressreleases/monetary{date.replace('-', '')}{suffix}.htm"
    return excerpt(title, date, url, locator, text)


def fed_event() -> dict:
    early, late = "2023-07-26", "2023-09-20"
    jul = fed(early, "a", "Policy decision, paragraph 3",
              "raise the target range for the federal funds rate to 5-1/4 to 5-1/2 percent.")
    jun = fed("2023-06-14", "a", "Policy decision, paragraph 3",
              "maintain the target range for the federal funds rate at 5 to 5-1/4 percent.")
    reserve = fed(early, "a1", "Board action, first bullet",
                  "interest rate paid on reserve balances to 5.4 percent, effective July 27, 2023.")
    goal = fed("2023-05-03", "a", "Objectives, paragraph 3",
               "inflation at the rate of 2 percent over the longer run.")
    inflation = fed(early, "a", "Economic conditions, paragraph 1", "Inflation remains elevated.")
    before = [reserve, jun, goal, jul, inflation]
    sep = fed(late, "a", "Policy decision, paragraph 3",
              "maintain the target range for the federal funds rate at 5-1/4 to 5-1/2 percent.")
    june_jobs = excerpt("BLS June 2023 employment release", "2023-07-07",
                        "https://www.bls.gov/news.release/archives/empsit_07072023.htm", "Opening paragraph",
                        "the unemployment rate changed little at 3.6 percent")
    aug_jobs = excerpt("BLS August 2023 employment release", "2023-09-01",
                       "https://www.bls.gov/news.release/archives/empsit_09012023.htm", "Opening paragraph",
                       "the unemployment rate rose to 3.8 percent")
    jobs = fed(late, "a", "Economic conditions, paragraph 1",
               "Job gains have slowed in recent months but remain strong,")
    after = [aug_jobs, jul, jobs, sep, june_jobs]
    return dict(
        id="fed-september-2023", name="September 2023 US monetary policy meeting", famous=True,
        direction="flat", outcome=dict(date=late, url=sep["url"],
            description="The FOMC maintained the federal funds target range at 5.25–5.50 percent."),
        questions=[
            task("relevance", early,
                 "For the July 2023 FOMC decision, identify the measure that describes the policy target range "
                 "as distinct from interest on reserve balances. Choose target_range or reserve_remuneration "
                 "and give the range's upper bound in percent.", before, "target_range", "5.50", "D",
                 forecast("Will the September 2023 FOMC statement retain both July target-range bounds?", 1,
                          late, sep["url"])),
            task("importance", early,
                 "A hypothetical July credit mandate requires a review if the decided federal funds target "
                 "midpoint has risen by at least 20 basis points from the June meeting. Which action follows? "
                 "Choose review or defer and give the signed midpoint change in basis points.",
                 before, "review", "25", "BD"),
            task("association", late,
                 "Compare the July and September 2023 policy snapshots. Pair each meeting's target upper bound "
                 "with its latest published unemployment reading (June and August respectively). Which rose "
                 "from the first snapshot to the second? Choose unemployment_only, target_only, both, or neither. "
                 "Give the signed change in unemployment in percentage points. Document both dated target "
                 "decisions and both labor observations.", after, "unemployment_only", "0.2", "ABDE"),
            task("causality", late,
                 "Does juxtaposing the July 2023 FOMC rate action and the September FOMC description of job "
                 "gains identify how many additional jobs that July action caused by September? Choose "
                 "identified or unidentified and give the signed job count if identified, else null. Support "
                 "both the specific July policy exposure and the later employment observation.",
                 after, "unidentified", None, "BC"),
        ])


def cpi_event() -> dict:
    early, late = "2022-07-27", "2022-08-10"
    june_url = "https://www.bls.gov/news.release/archives/cpi_07132022.htm"
    july_url = "https://www.bls.gov/news.release/archives/cpi_08102022.htm"
    may_url = "https://www.bls.gov/news.release/archives/cpi_06102022.pdf"
    # In the two BLS panels whitespace separates adjacent cells of the original Table A.
    # The question supplies the column order as a reader aid even in the no-material arm.
    jun_all = excerpt("BLS June 2022 CPI release", "2022-07-13", june_url, "Table A, all items",
                      "All items 0.6 0.6 0.8 1.2 0.3 1.0 1.3 9.1")
    jun_food = excerpt("BLS June 2022 CPI release", "2022-07-13", june_url, "Table A, food",
                       "Food 0.5 0.9 1.0 1.0 0.9 1.2 1.0 10.4")
    may_energy = excerpt("BLS May 2022 CPI release", "2022-06-10", may_url, "Table 1, energy",
                         "8.255 235.339 298.469 316.761 34.6 6.1 11.0 -2.7 3.9")
    jul_rate = fed(early, "a", "Policy decision, paragraph 3",
                   "raise the target range for the federal funds rate to 2-1/4 to 2-1/2 percent")
    objective = fed("2022-06-15", "a", "Objectives, paragraph 3",
                    "inflation at the rate of 2 percent over the longer run.")
    before = [jun_food, objective, may_energy, jul_rate, jun_all]
    jul_all = excerpt("BLS July 2022 CPI release", late, july_url, "Table A, all items",
                      "All items 0.6 0.8 1.2 0.3 1.0 1.3 0.0 8.5")
    gas = excerpt("BLS July 2022 CPI release", late, july_url, "Table A, gasoline (all types)",
                  "Gasoline (all types) -0.8 6.6 18.3 -6.1 4.1 11.2 -7.7 44.0")
    after = [jul_rate, jun_food, jul_all, gas, may_energy]
    guide = (" In a Table A row the last number is the unadjusted 12-month change, and the preceding "
             "numbers are seasonally adjusted monthly changes in chronological order.")
    return dict(
        id="us-cpi-july-2022", name="July 2022 US consumer price release", famous=False,
        direction="flat", outcome=dict(date=late, url=july_url,
            description="The initial July release reported monthly seasonally adjusted all-items CPI-U growth of 0.0%."),
        questions=[
            task("relevance", early,
                 "In the June 2022 CPI-U release, which rose faster from May to June, all items or food? "
                 "Choose all_items, food, or equal and give the larger seasonally adjusted monthly change "
                 "in percent. Cite the evidence for both series." + guide,
                 before, "all_items", "1.3", "AE",
                 forecast("Will the initially published July seasonally adjusted monthly all-items CPI-U "
                          "increase exceed 0.5 percent?", 0, late, july_url)),
            task("importance", early,
                 "A hypothetical cost-review policy triggers only when the latest June US all-items CPI-U "
                 "12-month increase strictly exceeds 9.0%. Decide trigger or hold and give the signed "
                 "margin above that threshold in percentage points." + guide,
                 before, "trigger", "0.1", "E"),
            task("association", late,
                 "Compute the change from June to July in the gap between US gasoline price growth and "
                 "all-items CPI-U growth, using seasonally adjusted monthly percentage changes. Form "
                 "gasoline minus all items separately for each month and subtract June's gap from July's. "
                 "Choose rose, fell, or stable and give the signed change in percentage points." + guide,
                 after, "fell", "-17.6", "CD"),
            task("causality", late,
                 "Do the July US policy-rate announcement and the July monthly gasoline CPI observation "
                 "identify the size of that announcement's causal effect on the gasoline index? Choose "
                 "identified or unidentified and give the signed percentage effect if identified, else null. "
                 "Cite the July action and the observed gasoline series." + guide,
                 after, "unidentified", None, "AD"),
        ])


def scholarship_event() -> dict:
    early, late = "2017-07-01", "2019-05-15"
    law = "https://www.govinfo.gov/content/pkg/PLAW-112publ10/html/PLAW-112publ10.htm"
    first = "https://ies.ed.gov/ncee/2025/01/20174022-pdf"
    final = "https://files.eric.ed.gov/fulltext/ED594875.pdf"
    appendix = ("https://ies.ed.gov/sites/default/files/migrated/nces_pubs/ncee/pubs/"
                "20194006/pdf/20194006_Technical_Appendix.pdf")
    low = excerpt("Public Law 112-10", "2011-04-15", law, "SOAR Act sec. 3007(a)(3)(B)(i), initial cap (I)",
                  "$8,000 for attendance in kindergarten through grade 8;")
    high = excerpt("Public Law 112-10", "2011-04-15", law, "SOAR Act sec. 3007(a)(3)(B)(i), initial cap (II)",
                   "$12,000 for attendance in grades 9 through 12.")
    math = excerpt("NCEE 2017-4022, year one", "2017-04-27", first, "Executive summary, p. xiii, mathematics",
                   "5.4 percentile points for students offered a scholarship and 7.3 percentile points "
                   "for students who used their scholarship")
    expenses = excerpt("Public Law 112-10", "2011-04-15", law, "SOAR Act sec. 3007(a)(2), payments",
                       "tuition, fees, and transportation expenses (if any)")
    objectives = excerpt("NCEE 2017-4022, year one", "2017-04-27", first, "Executive summary, opening",
                         "tuition vouchers to low-income parents")
    before = [low, expenses, math, objectives, high]
    design = excerpt("NCEE 2019-4006, year three", late, final, "Overview of the evaluation, p. 2",
                     "Lotteries were used to randomly award scholarships to applicants.")
    base = excerpt("NCEE 2019-4006 technical appendix", late, appendix, "Table C-3, full sample, chronic absence",
                   "Full sample 21.9 27.3 -5.4* -0.12 -7.5 -0.17 0.03")
    subset = excerpt("NCEE 2019-4006 technical appendix", late, appendix, "Table C-3, schools in need of improvement",
                     "SINI 24.7 30.4 -5.7 -0.12 -8.1 -0.18 0.06")
    after = [subset, expenses, design, high, base]
    columns = (" In the year-three chronic absence table the first two numbers are the estimates for "
               "those offered and those not offered, in percent, in that order.")
    return dict(
        id="dc-scholarship-attendance", name="Washington DC Opportunity Scholarship lottery follow-up",
        famous=False, direction="down", outcome=dict(date=late, url=final,
            description="The year-three impact estimate for an offer on full-sample chronic absence was −5.4 percentage points."),
        questions=[
            task("relevance", early,
                 "A reviewer wants the absolute magnitude of the one-year math impact estimate of using a "
                 "DC Opportunity Scholarship during the 2012–14 lottery study, separately from the offer "
                 "estimate. Choose use or offer for the applicable estimand and give the magnitude in "
                 "percentile points.", before, "use", "7.3", "C",
                 forecast("Will the published year-three full-sample chronic absence point estimate be lower "
                          "for applicants offered a scholarship than for applicants not offered one?",
                          1, late, final)),
            task("importance", early,
                 "An auditor tests a hypothetical flat $10,000 scholarship against both initial 2011–12 "
                 "SOAR Act grade-band caps, before inflation adjustments. Which band alone would exceed "
                 "its statutory ceiling? Choose K8, G9_12, both, or neither. Give the dollar overage for "
                 "the breaching band and substantiate both bands.", before, "K8", "2000", "AE"),
            task("association", late,
                 "Compare the year-three chronic absence gap (offered minus not offered) for DC applicants "
                 "from schools in need of improvement (SINI) to the full-sample gap. Give SINI gap minus "
                 "full-sample gap as signed percentage points, and choose wider, narrower, or equal for "
                 "the SINI gap in magnitude." + columns, after, "wider", "-0.3", "AE"),
            task("causality", late,
                 "Does the DC scholarship allocation design support estimating the effect of being offered "
                 "a scholarship on chronic absenteeism as reported for the full study sample three years "
                 "later? Choose offer_effect or descriptive_only. Give the study's signed offer-effect "
                 "estimate in percentage points if supported, else null. Support the design and the "
                 "numerical contrast." + columns, after, "offer_effect", "-5.4", "CE"),
        ])


def build() -> list[dict]:
    return [fed_event(), cpi_event(), scholarship_event()]
