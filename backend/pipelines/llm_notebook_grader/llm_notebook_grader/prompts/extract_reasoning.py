# reasoning control prompts for extraction step
# prepended to main task prompt as system-level reasoning instructions

restrictive = """
REASONING MODE: MINIMAL

Do not deliberate. Do not analyze cell content beyond surface-level pattern matching.
Apply these patterns directly:
- Markdown with numbered item / imperative verb / question mark -> task_cell candidate
- Code/output cells immediately following a task_cell -> solution_cells
- Everything before first task, standalone imports, headers, notes -> general
- When uncertain, default to general over other.
Produce output immediately. No internal justification needed.
"""

standard = """
REASONING MODE: STANDARD

You may briefly reason about ambiguous cell boundaries.
For each group of cells, determine whether it constitutes a task or general block.
Focus on: does the markdown cell explicitly ask the student to produce something gradeable?
If yes, the following code/output cells form the solution.
Do not over-analyze code correctness or output validity — only classify structure.
Keep reasoning proportional to ambiguity. Clear cases need no deliberation.
"""

verbose = """
REASONING MODE: DETAILED

You are permitted to reason thoroughly about cell classification.
For each potential task boundary, consider:
1. Does the markdown cell contain an explicit assignment or question?
2. Which subsequent code cells are direct responses vs. shared infrastructure?
3. Where does one task end and the next begin?
4. Are there import cells that belong to a specific task vs. general setup?
5. Could any ambiguous cells reasonably be classified differently?

Deliberate as needed, but remember: your final output must still be ONLY the JSON array.
All reasoning must happen internally. The output contains zero explanation.
"""

REASONING_MODES = {
    "restrictive": restrictive,
    "standard": standard,
    "verbose": verbose,
}
