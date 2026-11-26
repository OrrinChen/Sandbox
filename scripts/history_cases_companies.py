"""Dated reporting and trial records for the two company events in the historical pilot."""
from __future__ import annotations


def excerpt(document: tuple[str, str, str], locator: str, text: str) -> dict:
    source, url, published = document
    return {"source": source, "url": url, "published": published, "locator": locator, "text": text}


def item(dimension: str, cutoff: str, question: str, evidence: list[dict],
         choice: str, value: str | None, refs: str) -> dict:
    return {"dimension": dimension, "cutoff": cutoff, "question": question, "evidence": evidence,
            "gold": {"choice": choice, "value": value, "citations": [list(refs)]}}


def netflix() -> dict:
    letters = "https://s22.q4cdn.com/959853165/files/doc_financials/2023/"
    q1 = ("Netflix Q1 2023 shareholder letter", letters + "q1/Final-Q1-23-Shareholder-Letter.pdf", "2023-04-18")
    q2 = ("Netflix Q2 2023 shareholder letter", letters + "q2/FINAL-Q2-23-Shareholder-Letter.pdf", "2023-07-19")
    feb = ("Netflix news release", "https://about.netflix.com/en/news/an-update-on-sharing", "2023-02-08")
    may = ("Netflix U.S. news release", "https://about.netflix.com/en/news/update-on-sharing-may-us", "2023-05-23")
    guide = excerpt(q1, "p. 3, Forecast, first paragraph", "Q2 paid net adds that are roughly similar to Q1’23")
    geo = excerpt(feb, "second paragraph", "starting today in Canada, New Zealand, Portugal and Spain")
    april = [
        guide, geo,
        excerpt(q1, "p. 1, Global Streaming Paid Net Additions (millions), Q1'23", "1.75"),
        excerpt(feb, "Buy an extra member, Canadian price", "CAD$7.99 a month per person in Canada"),
        excerpt(q1, "p. 1, Revenue (USD millions), Q2'23 Forecast", "$8,242"),
    ]
    july = [
        excerpt(q2, "p. 1, Global Streaming Paid Net Additions (millions), Q1'23 and Q2'23 respectively", "1.75 5.89"),
        excerpt(may, "opening paragraph", "Starting today, we will be sending this email to members who are sharing Netflix outside their household in the United States."),
        excerpt(q2, "p. 2, footnote 3", "extra member accounts are not included in our paid membership count but add revenue that is included in ARM."),
        guide, geo,
    ]
    relevance = item("relevance", q1[2],
        "At the April 2023 results briefing, an analyst is checking management's published outlook for Q2 "
        "global streaming paid net additions against its Q1 result. Was management guiding to approximately "
        "double, similar, or half the prior quarter? Give that prior-quarter baseline in millions as value.",
        april, "similar", "1.75", "AC")
    relevance["forecast"] = {
        "question": "What is your probability that the subsequently reported Q2 2023 global streaming paid net additions will exceed the Q1 2023 figure?",
        "binary_outcome": 1, "resolution_date": q2[2], "url": q2[1],
    }
    return {
        "id": "netflix_paid_sharing", "name": "Netflix paid sharing", "famous": True, "direction": "up",
        "outcome": {"date": q2[2], "url": q2[1], "description": "Q2 global streaming paid net additions rose to 5.89 million from 1.75 million in Q1."},
        "questions": [
            relevance,
            item("importance", q2[2],
                 "A team wants to track both the subscriber and revenue impact of an existing Netflix "
                 "household paying for one extra-member account. Under the reported accounting definition, "
                 "which dashboard responds to the extra charge itself: membership_count, revenue_per_membership, "
                 "both, or neither? Give the number added to the global paid membership count by the "
                 "extra-member account alone as value.", july, "revenue_per_membership", "0", "C"),
            item("association", q2[2],
                 "How did global streaming paid net additions change from Q1 to Q2 2023 at Netflix? Choose "
                 "increase, decrease or unchanged and give Q2 minus Q1 in millions.", july, "increase", "4.14", "A"),
            item("causality", q2[2],
                 "Use Netflix's dated US outreach announcement and the global Q1/Q2 net-additions comparison "
                 "to assess how many of the additional net additions were caused by that US outreach. "
                 "Cite both the outreach and the observed comparison. Choose identified or unidentified and "
                 "give the supported causal estimate in millions, or null if unidentified.", july, "unidentified", None, "AB"),
        ],
    }


def trip() -> dict:
    paper = ("Bloom, Han and Liang, Nature 630, 920–925", "https://pmc.ncbi.nlm.nih.gov/articles/PMC11208135/", "2024-06-12")
    previous = ("Bloom et al., Quarterly Journal of Economics 130, 165–218",
                "https://doi.org/10.1093/qje/qju032", "2014-11-20")
    october = ("Trip.com Group newsroom release",
               "https://www.trip.com/newsroom/trip-com-group-receives-un-award-for-gender-inclusive-workplace/", "2021-10-21")
    february = ("Trip.com Group newsroom release",
                "https://us.trip.com/newsroom/trip-com-group-launches-hybrid-work-policy-as-75-of-employees-report-improved-wellness/", "2022-02-15")
    early = [
        excerpt(previous, "abstract, earlier trial population", "Call center employees who volunteered to WFH"),
        excerpt(october, "Enhancing Employee Happiness and Satisfaction, 2021 trial", "expanded the scope of employees to cover more positions"),
        excerpt(previous, "abstract, earlier trial finding", "Home working led to a 13% performance increase"),
        excerpt(october, "Female Representation Far Exceeds Industry Levels", "41% of mid-level staff are female"),
        excerpt(previous, "abstract, earlier trial attrition", "their attrition rate halved"),
    ]
    late = [
        excerpt(paper, "Effects on employee retention, all participants, control attrition rate (%)", "7.20"),
        excerpt(paper, "Discussion, management estimate of recruitment and training cost per quit", "approximately US$20,000"),
        excerpt(february, "trial participant survey", "over 75% reported feeling an improvement in their wellness"),
        excerpt(paper, "Effects on employee retention, all participants, treatment attrition rate (%)", "4.80"),
        excerpt(paper, "study design, first paragraph beginning Our study describes",
                "Employees were randomized by even or odd birthdays into the option to WFH on Wednesday and Friday"),
    ]
    relevance = item("relevance", october[2],
        "A reader wants to use Ctrip's older home-working result as direct evidence for its 2021 pilot. "
        "Compare the workforce in the earlier published experiment with the scope of the new trial: choose "
        "broader, same or narrower for the 2021 population. Cite both populations and give the earlier "
        "performance increase in percent as value.", early, "broader", "13", "ABC")
    relevance["forecast"] = {
        "question": "What is your probability that by March 31, 2022, Trip.com will publicly report lower employee turnover in its 2021 hybrid-working trial?",
        "binary_outcome": 1, "resolution_date": february[2], "url": february[1],
    }
    return {
        "id": "trip_hybrid_trial", "name": "Trip.com hybrid-working trial", "famous": True, "direction": "down",
        "outcome": {"date": paper[2], "url": paper[1], "description": "The published hybrid-offer arm quit rate was 4.80%, versus 7.20% in the office arm."},
        "questions": [
            relevance,
            item("importance", paper[2],
                 "In a hypothetical six-month budget for 1,000 similar staff, use the published trial-arm quit "
                 "rates as a planning scenario and the company's approximate recruitment-and-training cost per "
                 "quit as the unit saving. Would the implied avoided costs cover a $500,000 implementation "
                 "budget? Choose cover or short and give estimated avoided costs minus budget in USD.",
                 late, "short", "-20000", "ABD"),
            item("association", paper[2],
                 "Among all participants in the 2021–22 Trip.com trial, compare quitting in the group offered "
                 "hybrid working with the office group. Choose higher, lower or same and give the relative "
                 "percentage change using the office rate as the denominator, rounded to the nearest whole percent "
                 "(negative for lower).", late, "lower", "-33", "AD"),
            item("causality", paper[2],
                 "Which effect on quitting does the published design support for these participants: "
                 "effect_of_offer, effect_of_actual_days_home, or neither? Give the estimate in percentage "
                 "points, hybrid group minus office group, or null if neither is supported. Cite the design "
                 "and both outcome rates.", late, "effect_of_offer", "-2.4", "ADE"),
        ],
    }


def build() -> list[dict]:
    return [netflix(), trip()]
