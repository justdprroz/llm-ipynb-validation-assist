"""Per-student human-readable report (Russian, like sibling pipelines)."""

from __future__ import annotations

_CONF_LABEL = {1.0: "уверенно", 0.5: "под вопросом", 0.0: "требует проверки"}


def build_report(student_id: str, grades: list[dict]) -> str:
    if grades:
        final = sum(g["mark"] for g in grades) / len(grades) * 10
    else:
        final = 0.0

    lines = [f"Привет {student_id}!", ""]

    feedback = []
    for g in sorted(grades, key=lambda x: str(x["task_id"])):
        if g["mark"] >= 1.0 and not g.get("manual_review"):
            continue
        conf = _CONF_LABEL.get(g.get("confidence", 0.0), "?")
        issues = "; ".join(g.get("issues") or []) or g.get("interpretation", "")
        tag = " [на проверку]" if g.get("manual_review") else ""
        feedback.append(f"Задача {g['task_id']} — {g['mark']} ({conf}){tag}: {issues}")

    if feedback:
        lines += ["Обратная связь:", ""] + feedback + [""]

    review = [str(g["task_id"]) for g in grades if g.get("manual_review")]
    if review:
        lines.append(
            f"Низкая уверенность, проверьте вручную: задачи {', '.join(review)}"
        )
        lines.append("")

    lines.append("Спасибо за проделанную работу!")
    lines.append("")
    lines.append(f"Итого: {final:.1f} / 10")
    return "\n".join(lines)
