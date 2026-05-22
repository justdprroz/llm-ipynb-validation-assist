"""
Используется для перефразирования промптов для каждой модели
Промпт используется на английском языке для большего понимания моделями: gpt-oss, qwen3
"""
reprompt = """
Below will be a prompt from one of the steps of grading student homeworks.
You goal is to rewrite it preserving all grading and academic related parts like points, formalas and
general grading recommendation.
Do not try to change schemas of my prompt. Do not add anything that condtradicts raw initial instruction
I need you to ensure that prompt:
    1) is strict, optimized for prompting specifically you.
    2) enforces answers only using strict and syntaxically correct json described in prompt below
    3) is fully compatible with python multiline strings(no conflicting character sequences) (it will be put inside triple code)
    4) avoid structs and markdown for human readability - only llm will read it
    5) avoid strange symbols not used in UTF-8
    6) explicity asks model to think as less as needed, we need categorization, not problem solving
"""

"""
Промпт ниже используется для первого шага пайплайна проверки -
разбиение предобработанной тетрадки на логические блоки которые можно расценивать как одно, независимое
задание выполненное в рамках домашней работы которое может быть оценено
"""
task_separation = """
Below will be an optimized list of cells from ipynb source json.
This list was algorithmically aqquired from json.
This list has lines, where each entry is one of the following:
1) id: markdown: <markdown text of the cell>
2) id: code: <text of code from cell>
3) id: output: <output of the neared code cell above>

Where id is strictly provided by algorithm and should be preserved

Some additional meaning of fields:
output can be either:
1) plain text from regular stdout
2) text/plain from display output
3) text/html from display output
4) base64 of image with additional tag

Not all models can support VL, which is not needed at this point.

Your goal is to extract:
1) General homework idea and part/subpart
2) Specific tasks: md + code + output

Note that for task you should only extract cell sequence that is explicitly gradable and makes sense.
Some blocks of imports can be a part of task.
But consider that some cells are general and not task specific:
1) Notes
2) Imports
3) Lecturer provided examples

You separated results should form Json array where each entry is:
1) type: general or task or other
for general and other
2) sorted list of unique ids of corresponding adjacent cells forming entry
for task:
2) provide task_id
3) task_cell - reference to cell destribe task provided by lecturer
4) solution_cells - list of cells forming student solution(sorted + unique, like general cells)

In terms of json it should form:
[
    {
        "type": "general",
        "cells": [0, 1, 2, 3]
    },
    {
        "type": "task",
        "task_id": 0,
        "task_cell": 4,
        "solution_cells": [4, 5, 6]
    },
    ...
]

As some kind of fallback you can create single entry of type "other" with list of cells you are not sure about.
This unsure cells can also be included in general or task or can dangle in "other" block.
"""