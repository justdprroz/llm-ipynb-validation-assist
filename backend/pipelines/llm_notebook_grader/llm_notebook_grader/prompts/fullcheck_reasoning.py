# reasoning control prompts for full notebook check step

restrictive = """
REASONING MODE: MINIMAL

Do not deliberate. For each task found in the notebook:
- Does the code address the task? Mark accordingly.
- Are there obvious errors in output? Note them.
- No line-by-line analysis. Pattern match against task requirements.
Produce output immediately. No internal justification needed.
"""

standard = """
REASONING MODE: STANDARD

You may briefly reason about each task's solution quality.
For each task: does the code correctly solve what the task asks?
Note obvious issues but do not over-analyze style or edge cases.
Keep reasoning proportional to solution complexity.
"""

verbose = """
REASONING MODE: DETAILED

You are permitted to reason thoroughly about each task's solution.
For each task consider:
1. Does the code correctly implement what is asked?
2. Are edge cases handled?
3. Is the output correct and complete?
4. Are there code quality issues worth noting?
5. Does the approach demonstrate understanding of the concept?

Deliberate as needed, but your final output must still be ONLY the JSON array.
All reasoning must happen internally. The output contains zero explanation.
"""

REASONING_MODES = {
    "restrictive": restrictive,
    "standard": standard,
    "verbose": verbose,
}
