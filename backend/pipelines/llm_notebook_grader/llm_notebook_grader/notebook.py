from dataclasses import dataclass, field

type ParsedHomework = list[str]


@dataclass
class ExtractedTask:
    id: int
    task: list[str] = field(default_factory=list)
    solution: list[str] = field(default_factory=list)


def form_tasks(*, parsed_homework: ParsedHomework, tasks_lookup: dict) -> list[ExtractedTask]:
    cell_lut: dict[int, list[str]] = dict()
    for cell in parsed_homework:
        cell_id, cell_content = cell.split(":", 1)
        cell_id = int(cell_id)
        if cell_id not in cell_lut:
            cell_lut[cell_id] = []
        cell_lut[cell_id].append(cell_content)

    # print(cell_lut)

    tasks: list[ExtractedTask] = []

    for entry in tasks_lookup:
        if entry["type"] != "task":
            continue

        task = ExtractedTask(
            id = int(entry["task_id"])
        )
        task.task.extend(cell_lut[entry["task_cell"]])

        for cell_id in entry["solution_cells"]:
            task.solution.extend(cell_lut[cell_id])

        tasks.append(task)

    return tasks
