default_prompt = """
You are given a list of notebook cells extracted from an ipynb file.
Each entry in the list is a dictionary with exactly the following keys:

- **id** – integer, unique identifier assigned by the extraction algorithm (must be preserved).
- **type** – one of the strings: `"markdown"`, `"code"`, `"output"`.
- **content** – the raw text of the cell (markdown text, code text, or output text).

The **output** cells may contain:
1. plain text from stdout,
2. `text/plain` from a display output,
3. `text/html` from a display output,
4. a base64‑encoded image preceded by an identifier tag.

Your job is **only** to classify contiguous groups of cells and produce a JSON array describing those groups.
Do not solve any programming tasks, do not generate explanations, and do not perform any additional processing beyond the required categorisation.

### Classification rules
1. **general** – a block of adjacent cells that are not directly gradable (e.g., lecture notes, import sections, instructor‑provided examples).
2. **task** – a block that is explicitly gradable. It must contain:
   - a **task description** cell (the lecturer's markdown cell that states the assignment),
   - the student's solution, which can include import cells, code cells, and corresponding output cells.
   The solution cells must be the minimal set that together constitute the answer to that task.
3. **other** – any cell or group of cells whose purpose is unclear. These may also be placed in "general" or "task" if you are reasonably confident; otherwise, put them in a single "other" block.

### Output format
CRITICAL: Your response must START with [ and END with ].
NO markdown code fences (```json or ```).
NO explanatory text before or after the JSON.
NO dots (...), dashes (---), or decorative symbols.
Your FIRST character must be [ and your LAST character must be ].

Each element of the array is an object with the following structure:

*For a general block*
```json
{
    "type": "general",
    "cells": [list of unique ids in ascending order]
}
```

*For a task block*
```json
{
    "type": "task",
    "task_id": integer (sequentially numbered starting at 0),
    "task_cell": id of the markdown cell that describes the task,
    "solution_cells": [list of unique ids of all cells that form the student's solution, sorted ascending]
}
```

*For an other block*
```json
{
    "type": "other",
    "cells": [list of unique ids]
}
```

The array must be ordered as the cells appear in the notebook (i.e., keep the original sequence of blocks).
Do **not** include any extra fields, comments, or explanatory text.
Output **only** the JSON array, formatted with standard double‑quoted strings and commas, and ensure it is syntactically valid.
"""

restrictive_prompt = """
You are given a list of notebook cells extracted from an ipynb file.
Each entry in the list is a dictionary with exactly the following keys:

- **id** – integer, unique identifier assigned by the extraction algorithm (must be preserved).
- **type** – one of the strings: `"markdown"`, `"code"`, `"output"`.
- **content** – the raw text of the cell (markdown text, code text, or output text).

The **output** cells may contain:
1. plain text from stdout,
2. `text/plain` from a display output,
3. `text/html` from a display output,
4. a base64‑encoded image preceded by an identifier tag.

Classify contiguous groups of cells. Do not solve tasks, do not explain.

### Reasoning constraints
- Do NOT analyze cell content in detail
- Do NOT justify classification choices
- Do NOT enumerate possibilities or alternatives
- Do NOT verify correctness of student code
- Do NOT explain what each cell does
- If reasoning is needed, ask ONLY: "Does this cell directly answer that cell, and does that cell directly ask for this cell?"
- Critical: correctly pair markdown task descriptions with their corresponding code solutions
- Use pattern matching: markdown with question → task_cell, following code → solution_cells
- Make immediate decisions, no deliberation

### Classification rules
1. **general** – a block of adjacent cells that are not directly gradable (e.g., lecture notes, import sections, instructor‑provided examples).
2. **task** – a block that is explicitly gradable. It must contain:
   - a **task description** cell (the lecturer's markdown cell that states the assignment),
   - the student's solution, which can include import cells, code cells, and corresponding output cells.
   The solution cells must be the minimal set that together constitute the answer to that task.
3. **other** – any cell or group of cells whose purpose is unclear. These may also be placed in "general" or "task" if you are reasonably confident; otherwise, put them in a single "other" block.

### Output
CRITICAL OUTPUT FORMAT:
- Your FIRST character MUST be [
- Your LAST character MUST be ]
- NO markdown fences (```json or ```)
- NO text before the array
- NO text after the array
- NO dots, dashes, decorative symbols
- NO commentary or explanations

Elements: {"type":"general","cells":[ids]} or {"type":"task","task_id":N,"task_cell":id,"solution_cells":[ids]} or {"type":"other","cells":[ids]}.
task_id sequential from 0. Keep notebook order. IDs ascending within each block.
"""

hardened_prompt = """
CRITICAL SYSTEM INSTRUCTION — FORMAT VIOLATION = AUTOMATIC FAILURE

You are given a list of notebook cells extracted from an ipynb file.
Each entry is a dictionary with exactly these keys:
- id — integer, unique, assigned by extraction algorithm. MUST be preserved exactly.
- type — one of: "markdown", "code", "output".
- content — raw text of the cell.

Output cells may contain: plain text (stdout), text/plain, text/html, or base64 image with tag.

=== YOUR SOLE TASK ===

Classify contiguous groups of cells into blocks. Produce a JSON array. Nothing else.

=== BLOCK TYPES — READ CAREFULLY ===

GENERAL block:
  Adjacent cells that are NOT directly gradeable.
  These include: homework title/header, general instructions, standalone import sections,
  lecturer-provided examples, setup code, notes, dataset loading, environment config.
  Key signal: no explicit question or assignment is posed. The cells serve as context,
  infrastructure, or preamble. If a markdown cell describes the homework but does NOT
  ask the student to do something specific and gradeable, it is general.

TASK block:
  A gradeable unit. This is the core of what matters.
  A task block MUST contain:
    - Exactly ONE task_cell: the markdown cell where the lecturer explicitly states an
      assignment, question, or problem the student must solve. Look for imperative verbs
      (create, find, compute, write, implement, solve, etc.) or numbered task indicators.
    - One or more solution_cells: the student's answer — code cells, their outputs, and
      possibly a small number of import/setup cells that are specific to this task only.
  The solution_cells must be the MINIMAL set forming the answer. Do not include cells
  that belong to other tasks or to general setup.
  A task may have multiple code cells if the student provided multiple solutions or
  the solution spans several steps.

OTHER block:
  Cells whose purpose is genuinely unclear. Use sparingly. If you can reasonably classify
  as general or include in a task, do so. Only use other as last resort.

=== OUTPUT FORMAT — ABSOLUTE COMPLIANCE REQUIRED ===

WARNING: Any deviation from this format will result in COMPLETE REJECTION of your response.
There is ZERO tolerance for format errors. Your output will be machine-parsed by json.loads().

CRITICAL: Your response FIRST character = [, LAST character = ]

You MUST return EXACTLY a JSON array. Requirements:
1. NO markdown fences (no ```json, no ```). Raw JSON only.
2. NO text before the array. NO text after the array.
3. NO dots (...), dashes (---), ellipsis, or decorative symbols.
4. NO comments, explanations, notes, or reasoning in the output.
5. NO trailing commas.
6. ALL strings use double quotes.
7. The array starts with [ and ends with ].
8. First character you output = [
9. Last character you output = ]

Each element is one of:

For general:  {"type": "general", "cells": [<ids ascending>]}
For task:     {"type": "task", "task_id": <int>, "task_cell": <id>, "solution_cells": [<ids ascending>]}
For other:    {"type": "other", "cells": [<ids ascending>]}

Rules:
- task_id is sequential starting from 0.
- Array order matches notebook cell order (blocks appear in the sequence cells appear).
- Every cell id from input must appear in exactly one block.
- IDs within cells/solution_cells lists must be sorted ascending.
- No extra fields. No missing fields.

PENALTY: If you output ANYTHING other than a valid JSON array matching this schema,
your entire response is worthless and will be discarded. Treat format compliance as
the highest priority — above all other considerations.

=== CORRECT OUTPUT EXAMPLE ===

[
  {"type": "general", "cells": [0, 1, 2]},
  {"type": "task", "task_id": 0, "task_cell": 3, "solution_cells": [4, 5]},
  {"type": "task", "task_id": 1, "task_cell": 6, "solution_cells": [7, 8, 9]}
]

Notice: Starts with [, ends with ], NO text before or after.
"""