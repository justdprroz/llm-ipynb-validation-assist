prompt_oss = """
### Prompt

You are given a **scraped, ordered list of Jupyter notebook cells**.
Each cell is represented as a row with **exactly one of the following types**:

* `md` — markdown text describing a task, explanation, or context
* `code` — Python source code
* `output` — execution output corresponding **only** to the immediately preceding `code` cell

The list preserves the original notebook order.

---

### Objective

Construct a **list of structured task objects**, where **each task represents one logical problem statement and its attempted solution**.

A task consists of:

* the relevant markdown describing the task,
* the code intended to solve it,
* the observed output of that code,
* an evaluation of how well the code + output solve the task.

---

### Task construction rules (strict)

1. **Markdown aggregation**

   * Consecutive `md` cells that describe the same problem **must be merged** into a single string.
   * Stop merging markdown when a `code` cell appears.
   * This merged text becomes `task`.

2. **Code aggregation**

   * All `code` cells that are part of solving the immediately preceding markdown task **must be merged**, preserving order.
   * If multiple code cells appear before the next markdown task, they all belong to the same task.
   * The merged code becomes `code`.

3. **Output association**

   * Each `output` cell belongs **only** to the immediately preceding `code` cell.
   * Merge all outputs corresponding to the task’s code cells, preserving order.
   * The merged outputs become `output`.

4. **Task boundaries**

   * A new task starts when new task-describing markdown appears.
   * Do NOT create tasks without markdown.
   * Do NOT merge across unrelated markdown sections.

---

### Grading rules

For each task, assign:

* `grade`: a numeric score from **0 to 10**

  * 10 = fully correct, complete, and aligned with the task
  * 7–9 = mostly correct, minor issues
  * 4–6 = partially correct, significant gaps
  * 1–3 = largely incorrect or ineffective
  * 0 = no meaningful solution or completely wrong

* `comment`: a concise, technical justification explaining **why** this grade was assigned
  (reference correctness, completeness, errors, mismatches between task and output)

Do **not** assume intent beyond what is explicitly shown in markdown, code, and output.

---

### Output format (mandatory)

Return **only** a JSON array.
Each entry **must strictly follow** this schema:

```json
{{
  "task": "_merged_markdown_tasks",
  "code": "_merged_code_cells",
  "output": "_what_code_output",
  "grade": _grade,
  "comment": "_comment"
}}
```

* No extra fields
* No explanations outside JSON
* Preserve original text and code verbatim (no rewriting or cleanup)

---

### Constraints

* Do not invent tasks, code, or outputs.
* Do not fix or modify code.
* Do not infer missing outputs.
* If code does not produce output, set `output` to an empty string.
* If grading is ambiguous, explain the ambiguity in `comment` but still assign a grade.

---

### Data

{0}
"""