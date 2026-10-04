"""Deterministic MockProvider — regex/heuristic extraction + grounded explanation.

No API key required. Used for demos, CI, and local development.
Produces FactSheet-shaped JSON and a 6–8th grade explanation grounded in quotes.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm.base import LLMProvider


def _span(text: str, quote: str, value: Any) -> dict[str, Any] | None:
    if not quote:
        return None
    idx = text.find(quote)
    if idx < 0:
        # Fallback: case-insensitive search
        idx = text.lower().find(quote.lower())
        if idx < 0:
            return {"value": value, "quote": quote, "start_char": None, "end_char": None}
        quote = text[idx : idx + len(quote)]
    return {
        "value": value,
        "quote": quote,
        "start_char": idx,
        "end_char": idx + len(quote),
    }


def extract_facts_heuristic(report_text: str) -> dict[str, Any]:
    """Rule-based pathology fact extraction. Deterministic for a given report_text."""
    text = report_text
    facts: dict[str, Any] = {
        "diagnosis_or_histologic_type": None,
        "grade": None,
        "tumor_size": None,
        "margins": None,
        "lymph_nodes_positive": None,
        "lymph_nodes_examined": None,
        "pathologic_tnm_stage": None,
        "biomarkers": None,
    }

    # Diagnosis / histologic type
    diagnosis_patterns = [
        (r"(Invasive ductal carcinoma)", "Invasive ductal carcinoma"),
        (r"(Invasive lobular carcinoma)", "Invasive lobular carcinoma"),
        (r"(Ductal carcinoma in situ)", "Ductal carcinoma in situ"),
        (r"(Adenocarcinoma)", "Adenocarcinoma"),
        (r"(Squamous cell carcinoma)", "Squamous cell carcinoma"),
        (r"(Invasive adenocarcinoma)", "Invasive adenocarcinoma"),
        (r"(Moderately differentiated adenocarcinoma)", "Moderately differentiated adenocarcinoma"),
        (r"(Poorly differentiated adenocarcinoma)", "Poorly differentiated adenocarcinoma"),
        (r"(Well[- ]differentiated adenocarcinoma)", "Well-differentiated adenocarcinoma"),
        (r"(Acinar adenocarcinoma)", "Acinar adenocarcinoma"),
        (r"(Mucinous adenocarcinoma)", "Mucinous adenocarcinoma"),
    ]
    for pat, label in diagnosis_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            facts["diagnosis_or_histologic_type"] = _span(text, m.group(1), label)
            break

    # Grade (Nottingham / histologic grade / G1-G3)
    grade_m = re.search(
        r"((?:Nottingham\s+)?(?:histologic\s+)?[Gg]rade\s*[:=]?\s*([1-3]|I{1,3}|low|intermediate|high))",
        text,
    )
    if grade_m:
        raw = grade_m.group(2)
        mapping = {"I": "1", "II": "2", "III": "3", "low": "1", "intermediate": "2", "high": "3"}
        value = mapping.get(raw, raw)
        facts["grade"] = _span(text, grade_m.group(1), value)

    # Tumor size
    size_m = re.search(
        r"((?:greatest\s+dimension|tumor\s+size|measuring|measures?)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:cm|mm))",
        text,
        re.IGNORECASE,
    )
    if not size_m:
        size_m = re.search(r"((\d+(?:\.\d+)?)\s*cm\s*(?:in\s+)?(?:greatest\s+)?(?:dimension|diameter)?)", text, re.IGNORECASE)
    if size_m:
        num = size_m.group(2) if size_m.lastindex and size_m.lastindex >= 2 else re.search(r"(\d+(?:\.\d+)?)", size_m.group(1)).group(1)
        unit = "mm" if "mm" in size_m.group(0).lower() else "cm"
        facts["tumor_size"] = _span(text, size_m.group(1), f"{num} {unit}")

    # Margins
    margin_m = re.search(
        r"((?:surgical\s+)?margins?\s*(?:are\s+)?(?:negative|positive|uninvolved|involved|"
        r"free of (?:tumor|carcinoma)|close))",
        text,
        re.IGNORECASE,
    )
    if margin_m:
        q = margin_m.group(1)
        val = "negative" if re.search(r"negative|uninvolved|free of", q, re.I) else (
            "positive" if re.search(r"positive|involved", q, re.I) else "close"
        )
        facts["margins"] = _span(text, q, val)

    # Lymph nodes: "2 of 15" / "2/15 lymph nodes"
    ln_m = re.search(
        r"((\d+)\s*(?:of|/)\s*(\d+)\s*(?:lymph\s*)?nodes?(?:\s+(?:positive|involved|with\s+metastas))?)",
        text,
        re.IGNORECASE,
    )
    if ln_m:
        pos, exam = int(ln_m.group(2)), int(ln_m.group(3))
        facts["lymph_nodes_positive"] = _span(text, ln_m.group(1), pos)
        facts["lymph_nodes_examined"] = _span(text, ln_m.group(1), exam)
    else:
        exam_m = re.search(r"((\d+)\s+lymph\s+nodes?\s+(?:were\s+)?(?:examined|identified))", text, re.I)
        if exam_m:
            facts["lymph_nodes_examined"] = _span(text, exam_m.group(1), int(exam_m.group(2)))
        pos_m = re.search(r"((\d+)\s+(?:lymph\s+)?nodes?\s+(?:positive|with\s+metastasis))", text, re.I)
        if pos_m:
            facts["lymph_nodes_positive"] = _span(text, pos_m.group(1), int(pos_m.group(2)))

    # Pathologic TNM
    tnm_m = re.search(r"\b(pT[0-4is]+[a-c]?\s*N[0-3x][a-c]?\s*M[01x]|ypT[0-4is]+[a-c]?\s*N[0-3x][a-c]?\s*M[01x])\b", text, re.I)
    if not tnm_m:
        tnm_m = re.search(r"((?:pathologic\s+stage|pTNM)\s*[:=]?\s*(p?T[0-4is]+[a-c]?N[0-3x][a-c]?M[01x]))", text, re.I)
    if tnm_m:
        stage = tnm_m.group(1)
        # Prefer the compact code if group 2 exists
        if tnm_m.lastindex and tnm_m.lastindex >= 2 and tnm_m.group(2):
            stage = tnm_m.group(2)
        # Normalize spaces in stage codes like "pT2 N1 M0"
        compact = re.sub(r"\s+", "", stage) if re.match(r"p?T", stage, re.I) else stage
        if re.match(r"p?T", compact, re.I):
            facts["pathologic_tnm_stage"] = _span(text, tnm_m.group(0).strip(), compact)
        else:
            facts["pathologic_tnm_stage"] = _span(text, tnm_m.group(0).strip(), compact)

    # Biomarkers (ER/PR/HER2, MSI, EGFR, PD-L1, KRAS, etc.)
    biomarkers: dict[str, str] = {}
    bio_quotes: list[str] = []

    for name, pat in [
        ("ER", r"(ER\s*[:=]?\s*(?:positive|negative|\d+%|\+|−|-))"),
        ("PR", r"(PR\s*[:=]?\s*(?:positive|negative|\d+%|\+|−|-))"),
        ("HER2", r"(HER2(?:/neu)?\s*[:=]?\s*(?:positive|negative|equivocal|0|1\+|2\+|3\+))"),
        ("Ki-67", r"(Ki-?67\s*[:=]?\s*\d+%)"),
        ("MSI", r"(MSI[- ]?(?:high|low|stable)|microsatellite\s+instability\s*[:=]?\s*\w+)"),
        ("KRAS", r"(KRAS\s*[:=]?\s*(?:mutant|wild[- ]type|positive|negative|\w+))"),
        ("EGFR", r"(EGFR\s*[:=]?\s*(?:mutant|wild[- ]type|positive|negative|\w+))"),
        ("PD-L1", r"(PD-L1\s*[:=]?\s*(?:positive|negative|\d+%|TPS\s*\d+%))"),
        ("ALK", r"(ALK\s*[:=]?\s*(?:positive|negative|rearranged|wild[- ]type))"),
        ("MLH1", r"(MLH1\s*[:=]?\s*(?:retained|lost|positive|negative))"),
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            q = m.group(1)
            # Normalize value after colon/equals or last token
            val_m = re.search(r"(positive|negative|equivocal|mutant|wild[- ]type|retained|lost|high|low|stable|\d+%|\d+\+|0)", q, re.I)
            biomarkers[name] = val_m.group(1) if val_m else q
            bio_quotes.append(q)

    if biomarkers:
        joined = "; ".join(bio_quotes)
        # Use first quote for offsets if possible
        first = bio_quotes[0]
        span = _span(text, first, biomarkers)
        if span:
            span["quote"] = joined
        facts["biomarkers"] = span

    return facts


def build_explanation(facts: dict[str, Any]) -> dict[str, Any]:
    """Build a grounded 6–8th grade explanation from extracted facts."""
    sentences: list[dict[str, Any]] = []

    def add(sentence: str, keys: list[str], quote: str | None) -> None:
        sentences.append({"sentence": sentence, "source_fact_keys": keys, "quote": quote})

    diag = facts.get("diagnosis_or_histologic_type")
    if diag and diag.get("value"):
        add(
            f"This report describes {diag['value']}, which is a type of cancer found in the tissue sample.",
            ["diagnosis_or_histologic_type"],
            diag.get("quote"),
        )

    grade = facts.get("grade")
    if grade and grade.get("value"):
        add(
            f"The tumor grade is {grade['value']}. Grade tells how much the cancer cells look like normal cells; higher grades can grow faster.",
            ["grade"],
            grade.get("quote"),
        )

    size = facts.get("tumor_size")
    if size and size.get("value"):
        add(
            f"The tumor measures about {size['value']}.",
            ["tumor_size"],
            size.get("quote"),
        )

    margins = facts.get("margins")
    if margins and margins.get("value"):
        if str(margins["value"]).lower() == "negative":
            add(
                "The surgical margins are negative, meaning no cancer was seen at the edges of the removed tissue.",
                ["margins"],
                margins.get("quote"),
            )
        else:
            add(
                f"The surgical margins are reported as {margins['value']}. Your care team will explain what this means for next steps.",
                ["margins"],
                margins.get("quote"),
            )

    pos = facts.get("lymph_nodes_positive")
    exam = facts.get("lymph_nodes_examined")
    if pos and exam and pos.get("value") is not None and exam.get("value") is not None:
        add(
            f"{pos['value']} out of {exam['value']} lymph nodes contained cancer cells.",
            ["lymph_nodes_positive", "lymph_nodes_examined"],
            pos.get("quote") or exam.get("quote"),
        )
    elif exam and exam.get("value") is not None:
        add(
            f"{exam['value']} lymph nodes were examined.",
            ["lymph_nodes_examined"],
            exam.get("quote"),
        )

    stage = facts.get("pathologic_tnm_stage")
    if stage and stage.get("value"):
        add(
            f"The pathologic stage code is {stage['value']}. This code summarizes tumor size/extent (T), lymph nodes (N), and distant spread (M).",
            ["pathologic_tnm_stage"],
            stage.get("quote"),
        )

    bio = facts.get("biomarkers")
    if bio and isinstance(bio.get("value"), dict) and bio["value"]:
        parts = [f"{k} {v}" for k, v in bio["value"].items()]
        add(
            "Biomarker results include: " + ", ".join(parts) + ". These results help guide treatment choices.",
            ["biomarkers"],
            bio.get("quote"),
        )

    if not sentences:
        add(
            "This pathology report describes findings from the tissue sample. Please review the full report with your care team.",
            [],
            None,
        )

    return {"sentences": sentences}


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, model: str = "mock-heuristic-v1") -> None:
        self._model = model

    def model_id(self) -> str:
        return self._model

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_format: str | None = "json",
        temperature: float = 0.0,
    ) -> str:
        """Inspect the prompt to decide extract vs explain; ignore temperature (deterministic)."""
        combined = (system + "\n" + user).lower()
        # Extract the report text after a common delimiter used by our prompts.
        report = user
        for marker in ["REPORT:", "report text:", "pathology report:", "---"]:
            if marker.lower() in user.lower():
                idx = user.lower().rfind(marker.lower())
                report = user[idx + len(marker) :].strip()
                break

        if "explain" in combined and "extract" not in combined.split("explain")[0][-40:]:
            # Explanation path: try to parse facts from user message if present
            facts: dict[str, Any]
            try:
                # Prefer JSON block in user message
                m = re.search(r"\{[\s\S]*\"diagnosis_or_histologic_type\"[\s\S]*\}", user)
                if m:
                    facts = json.loads(m.group(0))
                else:
                    facts = extract_facts_heuristic(report)
            except json.JSONDecodeError:
                facts = extract_facts_heuristic(report)
            return json.dumps(build_explanation(facts))

        # Default: extraction
        facts = extract_facts_heuristic(report)
        return json.dumps(facts)
