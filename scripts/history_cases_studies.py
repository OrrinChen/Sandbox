"""Dated excerpts for three historical scientific studies. build() is author/scorer-side."""
from __future__ import annotations


def excerpt(source: tuple[str, str, str], text: str, locator: str) -> dict:
    name, url, date = source
    return {"source": name, "url": url, "published": date, "locator": locator, "text": text}


def question(dim: str, date: str, text: str, evidence: list, choice: str,
             value: str | None, refs: str, forecast: dict | None = None) -> dict:
    row = {"dimension": dim, "cutoff": date, "question": text, "evidence": evidence,
           "gold": {"choice": choice, "value": value, "citations": [list(refs)]}}
    if forecast:
        row["forecast"] = forecast
    return row


def dart() -> dict:
    nasa = "https://www.nasa.gov/"
    window = ("DART Launch Moves to Secondary Window", nasa + "solar-system/dart-launch-moves-to-secondary-window/", "2021-02-17")
    launch = ("NASA, SpaceX Launch DART: First Test Mission to Defend Planet Earth",
              nasa + "news-release/nasa-spacex-launch-dart-first-test-mission-to-defend-planet-earth/", "2021-11-24")
    impact = ("NASA’s DART Mission Hits Asteroid in First-Ever Planetary Defense Test",
              nasa + "news-release/nasas-dart-mission-hits-asteroid-in-first-ever-planetary-defense-test/", "2022-09-27")
    result = ("NASA Confirms DART Mission Impact Changed Asteroid’s Motion in Space",
              nasa + "news-release/nasa-confirms-dart-mission-impact-changed-asteroids-motion-in-space/", "2022-10-11")
    delay = excerpt(window, "SMD determined the primary launch period is no longer viable", "Launch-window assessment")
    measure = excerpt(launch, "Researchers will precisely measure that change using telescopes on Earth.", "Paragraph on the planned orbit measurement")
    threat = excerpt(impact, "Neither asteroid poses a threat to Earth.", "Paragraph describing the binary system")
    estimate = excerpt(impact, "Researchers expect the impact to shorten Dimorphos’ orbit by about 1%, or roughly 10 minutes", "Expected orbital change")
    optics = excerpt(launch, "a precise determination of Dimorphos’ mass", "Hera follow-up objective")
    periods = excerpt(result, "shortening the 11 hour and 55-minute orbit to 11 hours and 23 minutes", "Observed period before and after impact")
    threshold = excerpt(result, "change of 73 seconds or more", "Minimum successful period change")
    before = [delay, measure, threat, estimate, optics]
    after = [threat, periods, estimate, threshold, delay]
    return {"id": "dart", "name": "NASA DART / Didymos", "famous": True, "direction": "down",
            "outcome": {"date": result[2], "url": result[1], "description": "The October 11 estimate shortened the orbital period by 32 minutes."},
            "questions": [
                question("relevance", impact[2], "Which planned observing method would measure the orbital change in the DART test: earth_telescopes or followup_mass_measurement? Set value to null.",
                         before, "earth_telescopes", None, "B",
                         {"question": "Will NASA's first confirmed orbital-period result report a shortening greater than 15 minutes?", "binary_outcome": 1,
                          "resolution_date": result[2], "url": result[1]}),
                question("importance", result[2], "Apply NASA's mission minimum for the magnitude of the orbital-period change. Did the first confirmed estimate pass or fail? Set choice to pass or fail and give the positive margin above the minimum in seconds (negative if below).",
                         after, "pass", "1847", "BD"),
                question("association", result[2], "What was the signed change in Dimorphos's orbital period, after minus before impact, using the first confirmed NASA estimate? Use shorter or longer and give signed minutes.",
                         after, "shorter", "-32", "B"),
                question("causality", result[2], "Which claim about this particular encounter is documented: deflected_non_threat or prevented_predicted_earth_collision? Cite both the measured orbital response and the reported Earth-threat status of the binary. Set value to null.",
                         after, "deflected_non_threat", None, "AB")]}


def pubmed(name: str, identifier: int, date: str) -> tuple[str, str, str]:
    return name, f"https://pubmed.ncbi.nlm.nih.gov/{identifier}/", date


def sprint() -> dict:
    design = pubmed("SPRINT study design and rationale", 24902920, "2014-06-05")
    accord = pubmed("ACCORD blood-pressure trial", 20228401, "2010-03-14")
    final = pubmed("SPRINT primary trial report", 26551272, "2015-11-09")
    random = excerpt(design, "recruited and randomized 9361 people at 102 clinics", "Abstract, Results")
    secondary = excerpt(design, "Secondary outcomes include all-cause mortality", "Abstract, Methods")
    baseline = excerpt(design, "average baseline systolic blood pressure ≥130 mm Hg", "Abstract, Methods")
    comparison = excerpt(accord, "4733 participants with type 2 diabetes were randomly assigned", "Abstract, Methods")
    other_result = excerpt(accord, "hazard ratio with intensive therapy, 0.88", "Abstract, Results, primary composite")
    exclusions = excerpt(final, "an increased cardiovascular risk, but without diabetes", "Abstract, Methods, eligibility")
    rate = excerpt(final, "1.65% per year vs. 2.19% per year; hazard ratio with intensive treatment, 0.75", "Abstract, Results, primary composite, intensive versus standard")
    pre = [other_result, baseline, comparison, random, secondary]
    post = [rate, exclusions, other_result, comparison, random]
    return {"id": "sprint", "name": "The SPRINT blood-pressure study", "famous": False, "direction": "down",
            "outcome": {"date": final[2], "url": final[1], "description": "The November trial report gave a primary-composite hazard ratio of 0.75 with intensive treatment."},
            "questions": [
                question("relevance", design[2], "For a review of SPRINT's planned outcomes, how did the design classify death from any cause? Use primary or secondary and set value to null.",
                         pre, "secondary", None, "E",
                         {"question": "Will SPRINT's first full primary trial report give an intensive-versus-standard primary-composite hazard ratio below 0.90?",
                          "binary_outcome": 1, "resolution_date": final[2], "url": final[1]}),
                question("importance", final[2], "An evidence review requires randomized evidence directly enrolling people with type 2 diabetes. Choose the one eligible report, accord or sprint. Cite both the inclusion evidence for the selected report and the population limitation excluding the other. Set value to null.",
                         post, "accord", None, "BD"),
                question("association", final[2], "Compare the reported annual rate of SPRINT's primary composite across its intensive and standard arms. Give intensive minus standard in signed percentage points per year; choose lower or higher.",
                         post, "lower", "-0.54", "A"),
                question("causality", final[2], "For SPRINT's own enrolled population, does its allocation support estimating the effect of assignment to the intensive strategy, or only an observational association of achieved pressures? Choose randomized_assignment or achieved_association and give the reported primary-composite hazard ratio. Support the random allocation and the estimate.",
                         post, "randomized_assignment", "0.75", "AE")]}


def vital() -> dict:
    design = pubmed("VITAL-Bone Health design and rationale", 25623291, "2015-01-24")
    whi = pubmed("WHI calcium plus vitamin D trial", 16481635, "2006-02-16")
    parent = pubmed("VITAL parent trial of cancer and cardiovascular disease", 30415629, "2018-11-10")
    results = pubmed("VITAL supplemental vitamin D and incident fractures", 35939577, "2022-07-27")
    records = excerpt(design, "Study investigators adjudicate fractures through a detailed review of medical records and radiological images", "Abstract, fracture ascertainment")
    age = excerpt(design, "men aged ≥50 and women aged ≥55", "Abstract, parent cohort")
    paired = excerpt(whi, "calcium with vitamin D supplementation", "Abstract, Conclusions, intervention")
    prior = excerpt(whi, "0.96 for total fractures (0.91 to 1.02)", "Abstract, Results, intention-to-treat hazard ratios")
    random = excerpt(parent, "a nationwide, randomized, placebo-controlled trial, with a two-by-two factorial design, of vitamin D3", "Abstract, Methods")
    counts = excerpt(results, "total fractures (which occurred in 769 of 12,927 participants in the vitamin D group and in 782 of 12,944 participants in the placebo group", "Abstract, Results, total fractures")
    pre = [age, prior, records, random, paired]
    post = [random, records, prior, counts, paired]
    return {"id": "vital", "name": "VITAL fracture ancillary study", "famous": False, "direction": "flat",
            "outcome": {"date": results[2], "url": results[1], "description": "The crude total-fracture risk difference was -0.093 percentage points. The benchmark descriptive near-flat band is ±0.25 points; this is not a trial equivalence margin."},
            "questions": [
                question("relevance", parent[2], "Which source of confirmation did the VITAL fracture design specify: records_and_imaging or bone_density_alone? Set value to null.",
                         pre, "records_and_imaging", None, "C",
                         {"question": "Will the primary fracture publication report that supplemental vitamin D had a total-fracture hazard ratio below 0.90 versus placebo?",
                          "binary_outcome": 0, "resolution_date": results[2], "url": results[1]}),
                question("importance", parent[2], "A review accepts prior hazard ratios only if the treatment contrast isolates vitamin D from calcium. For the WHI total-fracture ratio, choose eligible or ineligible and give its point estimate. Cite both the intervention and the total-fracture estimate.",
                         pre, "ineligible", "0.96", "BE"),
                question("association", results[2], "Compute the crude total-fracture percentage in VITAL's vitamin D group minus that in its placebo group using each arm's own denominator. Report signed percentage points to three decimals. For this benchmark classify differences with absolute magnitude at most 0.25 points as near_flat, otherwise outside_band.",
                         post, "near_flat", "-0.093", "D"),
                question("causality", results[2], "From VITAL's allocation and raw arm counts, which interpretation is supported: assignment_effect_estimate or proof_of_exactly_zero_effect? Give the crude risk difference for assignment to vitamin D versus placebo in signed percentage points to three decimals. Cite the design and the counts.",
                         post, "assignment_effect_estimate", "-0.093", "AD")]}


def build() -> list[dict]:
    return [dart(), sprint(), vital()]
