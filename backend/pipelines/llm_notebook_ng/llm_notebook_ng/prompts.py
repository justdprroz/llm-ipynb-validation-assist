"""Prompt text and user-content builders for every stage.

Scoring is ternary {0, 0.5, 1} for BOTH mark and confidence. Confidence is a
reference-distance signal independent of the mark: how far the student's work
sits above the blank skeleton and how comparable it is to the gold solution.
"""

from __future__ import annotations

from llm_notebook_ng.notebook import cells_to_blocks, cells_to_text

# Bump when prompt semantics change — folded into the cache fingerprint so a
# new version regenerates structure/rubric/grades instead of reusing stale ones.
PROMPT_VERSION = "3"

_JSON_RULES = """
=== OUTPUT FORMAT — ABSOLUTE COMPLIANCE ===
Output is parsed by json.loads(). First character = {, last character = }.
NO markdown fences. NO text before or after the JSON.
"""

_SHARED_ENV = """
=== ENVIRONMENT IS SHARED — DO NOT PENALIZE SETUP PER TASK ===
Imports and one-time setup (e.g. `import numpy as np`, loading data) are written
ONCE for the whole notebook, NOT repeated inside every task. Assume the
environment is fully set up and all needed libraries are imported. NEVER treat a
missing import/setup within a single task's own cells as a fault, NEVER lower a
mark for it, and NEVER make "imports X" or general setup a criterion. Judge ONLY
the task-specific logic and its output.
"""

_OUTPUT_TOLERANCE = """
=== JUDGE THE ANSWER, NOT ITS WORDING ===
Grade the CORRECTNESS of the computed result / data / logic — NOT how it is
printed. Students phrase output freely; the reference wording is just ONE way.
NEVER require an exact printed phrase, label, caption, prompt string, language
(Russian vs English), column header, ordering of prints, rounding, or
formatting. If the correct value/answer is present and identifiable, that earns
FULL marks even when labels/wording/format differ from the gold (this is NOT
"partial"). Only penalize when the required value/result is missing, wrong, or
not computed. The sole exception: when the task's ANSWER itself IS a specific
literal (e.g. the answer is the name "Susan"), that literal is the value, not a
caption. Do NOT put exact-phrase/label/format requirements in any criterion.
"""

SCALE = """
=== SCORING SCALE (ternary, use ONLY 0, 0.5, or 1) ===
MARK — is the task solved?
  1   = solved correctly; confident it works as asked
  0.5 = minor strange aspects / minor issues, but broadly solved
  0   = not solved, or the work cannot be graded as a real solution
CONFIDENCE — reference-distance, INDEPENDENT of the mark:
  1   = clearly genuine work, well above the blank template and comparable to
        the gold approach; the mark can be trusted
  0.5 = only loosely comparable to gold / partial or unusual; mark is shaky
  0   = essentially the blank template, unrelated, or ungradeable; do NOT
        trust the mark — needs manual review
A correct-looking answer can still have LOW confidence if it is hard to tell it
apart from the blank skeleton or from an unrelated snippet.
"""

IMAGE_CLAUSE = """
=== IMAGE/PLOT TASK — BOOLEAN CONFIDENCE ===
This task produces a visual (plot/figure). Confidence MUST be 0 or 1 (never 0.5):
  1 = a relevant plot is clearly present and visibly comparable to the expected
      gold output
  0 = no usable plot, or you cannot verify it matches → manual review
Be aggressive: if in any doubt about the visual, set confidence 0.
"""

# ── Stage A/B: structure ──

STRUCTURE_SYSTEM = (
    """
You analyze a notebook SKELETON (task prompts; solutions removed) and report its
task structure. A task is any exercise/question, usually a markdown prompt
followed by code/answer cells.

Return:
{
  "context_cells": [<int>, ...],
  "tasks": [
    {
      "task_id": <int, from 1>,
      "description": "<one sentence>",
      "output_type": "text" | "plot" | "none",
      "task_cells": [<int>, ...],
      "solution_cells": [<int>, ...],
      "output_cells": [<int>, ...]
    }
  ]
}
"output_type" = "plot" if the task expects a chart/figure, "text" if it expects
printed/numeric output, "none" otherwise.
"""
    + _JSON_RULES
)

STRUCTURE_STUDENT_SYSTEM = STRUCTURE_SYSTEM.replace(
    "a notebook SKELETON (task prompts; solutions removed)",
    "a STUDENT submission notebook",
)

# ── Stage C: rubric synthesis ──

RUBRIC_SYSTEM = (
    """
You build a concrete grading rubric for ONE task, to be applied identically to
every student (the consistency anchor). You receive: the task prompt, the GOLD
solution for this task, the BLANK skeleton for this task, and graded EXEMPLARS
(student snippets already judged correct=1 or wrong=0).

Return:
{
  "task_id": <int>,
  "summary": "<what the task asks, one sentence>",
  "criteria_full": ["<concrete condition that earns mark 1>", ...],
  "criteria_partial": ["<what earns 0.5>", ...],
  "criteria_zero": ["<what earns 0>", ...],
  "confidence_full": "<what makes a grade trustworthy: clearly above blank, comparable to gold>",
  "confidence_low": "<what makes a grade untrustworthy: ~blank, unrelated, ungradeable>",
  "common_mistakes": ["<frequent error>", ...]
}
Criteria must be objective and checkable from code + output. Keep each list tight.
"""
    + _SHARED_ENV
    + _OUTPUT_TOLERANCE
    + _JSON_RULES
)

# ── Stage D/E: grading ──

GRADE_SYSTEM_BASE = (
    """
CRITICAL: FORMAT VIOLATION = AUTOMATIC FAILURE.
You grade ONE task for ONE student against the shared RUBRIC, using the GOLD
solution and BLANK skeleton as reference anchors. Apply the rubric verbatim and
identically for every student — do not invent new standards.

{effort}
"""
    + SCALE
    + """
Return:
{
  "task_id": <int>,
  "mark": 0 | 0.5 | 1,
  "confidence": 0 | 0.5 | 1,
  "interpretation": "<1-2 sentence assessment in Russian>",
  "issues": ["<issue in Russian>", ...],
  "approach": "<short tag of the student's approach, English>",
  "matched_criteria": ["<rubric criterion the student satisfied>", ...],
  "evidence_cell_ids": [<int cell ids you used>, ...],
  "output_type_seen": "text" | "plot" | "none" | "error"
}
"interpretation" and "issues" MUST be Russian. "issues" = [] if none.
"""
    + _SHARED_ENV
    + _OUTPUT_TOLERANCE
    + _JSON_RULES
)

REGRADE_SYSTEM_BASE = (
    """
CRITICAL: FORMAT VIOLATION = AUTOMATIC FAILURE.
You re-grade ONE task that was flagged (low confidence or a cohort outlier).
Re-read the student's work against the RUBRIC, GOLD and BLANK with extra care.
You are given the prior grade and the cohort context — correct it only if the
evidence warrants; otherwise confirm it. Grade strictly by the rubric.

{effort}
"""
    + SCALE
    + """
Return the SAME JSON object as the grader:
{
  "task_id": <int>, "mark": 0|0.5|1, "confidence": 0|0.5|1,
  "interpretation": "<Russian>", "issues": ["<Russian>", ...],
  "approach": "<English tag>", "matched_criteria": [...],
  "evidence_cell_ids": [<int>, ...], "output_type_seen": "text|plot|none|error"
}
"""
    + _SHARED_ENV
    + _OUTPUT_TOLERANCE
    + _JSON_RULES
)


def grade_system(effort_text: str, *, is_image: bool, regrade: bool = False) -> str:
    base = REGRADE_SYSTEM_BASE if regrade else GRADE_SYSTEM_BASE
    # NOTE: do not use str.format here — the templates contain literal { } from
    # the JSON schema examples, which str.format would parse as fields.
    text = base.replace("{effort}", effort_text)
    if is_image:
        text += IMAGE_CLAUSE
    return text


# ── user-content builders ──


def structure_user(skeleton_cells: list[dict]) -> str:
    return "Identify every task in this notebook skeleton.\n\n" + cells_to_text(
        skeleton_cells
    )


def student_structure_user(student_cells: list[dict]) -> str:
    return "Identify every task in this student notebook.\n\n" + cells_to_text(
        student_cells
    )


def rubric_user(
    spec_desc: str,
    gold_cells: list[dict],
    blank_cells: list[dict],
    pos_exemplars: list[str],
    neg_exemplars: list[str],
    shared_setup: list[dict] | None = None,
) -> str:
    parts = [
        f"=== TASK ===\n{spec_desc}\n",
        f"=== GOLD SOLUTION ===\n{cells_to_text(gold_cells) or '(none provided)'}\n",
        f"=== BLANK SKELETON ===\n{cells_to_text(blank_cells) or '(none)'}\n",
    ]
    if shared_setup:
        parts.append(
            "=== SHARED NOTEBOOK SETUP (imports already done here) ===\n"
            + cells_to_text(shared_setup)
            + "\n"
        )
    if pos_exemplars:
        parts.append(
            "=== CORRECT EXEMPLARS (mark 1) ===\n"
            + "\n---\n".join(pos_exemplars[:3])
            + "\n"
        )
    if neg_exemplars:
        parts.append(
            "=== WRONG EXEMPLARS (mark 0) ===\n"
            + "\n---\n".join(neg_exemplars[:3])
            + "\n"
        )
    return "\n".join(parts)


def grade_user(
    *,
    rubric: dict,
    context_cells: list[dict],
    gold_cells: list[dict],
    blank_cells: list[dict],
    student_cells: list[dict],
    img_kwargs: dict,
    student_setup_cells: list[dict] | None = None,
    prior: dict | None = None,
    cohort_note: str | None = None,
) -> list[dict]:
    content: list[dict] = []
    if context_cells:
        content.append(
            {
                "type": "text",
                "text": (
                    "=== SHARED CONTEXT (imports/setup for the whole notebook) "
                    f"===\n{cells_to_text(context_cells)}\n"
                ),
            }
        )
    content.append(
        {"type": "text", "text": f"=== RUBRIC ===\n{_render_rubric(rubric)}\n"}
    )
    content.append(
        {
            "type": "text",
            "text": f"=== GOLD SOLUTION ===\n{cells_to_text(gold_cells) or '(none)'}\n",
        }
    )
    if blank_cells:
        content.append(
            {
                "type": "text",
                "text": f"=== BLANK SKELETON ===\n{cells_to_text(blank_cells)}\n",
            }
        )
    if student_setup_cells:
        content.append(
            {
                "type": "text",
                "text": (
                    "=== THIS STUDENT'S SETUP (imports already done here — "
                    "do NOT penalize the task for these) ===\n"
                    f"{cells_to_text(student_setup_cells)}\n"
                ),
            }
        )
    content.append({"type": "text", "text": "=== STUDENT SOLUTION ===\n"})
    content.extend(cells_to_blocks(student_cells, **img_kwargs))
    if prior:
        content.append(
            {
                "type": "text",
                "text": (
                    f"\n=== PRIOR GRADE (under review) ===\nmark={prior.get('mark')}, "
                    f"confidence={prior.get('confidence')}, "
                    f"issues={prior.get('issues')}\n"
                ),
            }
        )
    if cohort_note:
        content.append(
            {"type": "text", "text": f"\n=== COHORT CONTEXT ===\n{cohort_note}\n"}
        )
    return content


def _render_rubric(rubric: dict) -> str:
    def block(title: str, key: str) -> str:
        items = rubric.get(key) or []
        body = "\n".join(f"  - {x}" for x in items) if items else "  (none)"
        return f"{title}:\n{body}"

    return "\n".join(
        [
            f"Summary: {rubric.get('summary', '?')}",
            block("Mark 1 (full)", "criteria_full"),
            block("Mark 0.5 (partial)", "criteria_partial"),
            block("Mark 0 (none)", "criteria_zero"),
            f"High confidence when: {rubric.get('confidence_full', '?')}",
            f"Low confidence when: {rubric.get('confidence_low', '?')}",
            block("Common mistakes", "common_mistakes"),
        ]
    )
