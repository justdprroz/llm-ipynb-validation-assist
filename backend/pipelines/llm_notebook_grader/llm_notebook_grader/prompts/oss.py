task_separation_oss = """
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
   - a **task description** cell (the lecturer’s markdown cell that states the assignment),  
   - the student’s solution, which can include import cells, code cells, and corresponding output cells.  
   The solution cells must be the minimal set that together constitute the answer to that task.  
3. **other** – any cell or group of cells whose purpose is unclear. These may also be placed in “general” or “task” if you are reasonably confident; otherwise, put them in a single “other” block.

### Output format
Return **exactly** a JSON array. Each element of the array is an object with the following structure:

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
    "solution_cells": [list of unique ids of all cells that form the student’s solution, sorted ascending]
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