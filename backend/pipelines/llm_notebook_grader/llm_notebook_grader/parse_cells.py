import json

type ParsedHomework = list[str]


def parse_ipynb(*, filepath: str) -> ParsedHomework:
    """Parse a Jupyter notebook file and return formatted cells."""
    with open(filepath, "r") as f:
        content: str = f.read()

    cells: list[dict] = json.loads(content)["cells"]

    parsed_cells: list[str] = []

    for cell_id, cell in enumerate(cells):
        cell_type: str = cell["cell_type"]
        cell_source: list[str] | None = cell.get("source", None)

        if cell_source is not None:
            cell_source: str = "".join(cell_source)

        if cell_type == "markdown":
            parsed_cells.append(f"{cell_id}: md: {cell_source}")

        if cell_type == "code":
            parsed_cells.append(f"{cell_id}: code: {cell_source}")

            outputs = cell["outputs"]

            if len(outputs) > 0:
                for raw_output in outputs:
                    output: list[str] | None = None
                    if raw_output["output_type"] == "stream":
                        if "text" in raw_output:
                            output = raw_output["text"]
                    elif raw_output["output_type"] == "display_data":
                        if "text/html" in raw_output["data"]:
                            output = raw_output["data"]["text/html"]
                        elif "text/plain" in raw_output["data"]:
                            output = raw_output["data"]["text/plain"]
                    elif raw_output["output_type"] == "execute_result":
                        if "text/plain" in raw_output.get("data", {}):
                            output = raw_output["data"]["text/plain"]
                        elif "text/html" in raw_output.get("data", {}):
                            output = raw_output["data"]["text/html"]

                    if output is not None:
                        output = "".join(output)
                        parsed_cells.append(f"{cell_id}: output: {output}")

    return parsed_cells


type RichCell = dict  # {cell_id, type, content} or {cell_id, type:"image", data, media_type}
type RichParsedHomework = list[RichCell]


def parse_ipynb_rich(*, filepath: str) -> RichParsedHomework:
    with open(filepath, "r") as f:
        content: str = f.read()

    cells: list[dict] = json.loads(content)["cells"]
    parsed: RichParsedHomework = []

    for cell_id, cell in enumerate(cells):
        cell_type: str = cell["cell_type"]
        cell_source: list[str] | None = cell.get("source", None)

        if cell_source is not None:
            cell_source: str = "".join(cell_source)

        if cell_type == "markdown":
            parsed.append({"cell_id": cell_id, "type": "md", "content": cell_source})

        if cell_type == "code":
            parsed.append({"cell_id": cell_id, "type": "code", "content": cell_source})

            for raw_output in cell.get("outputs", []):
                output_type = raw_output.get("output_type", "")
                data = raw_output.get("data", {})

                # extract images first
                if "image/png" in data:
                    parsed.append({
                        "cell_id": cell_id,
                        "type": "image",
                        "data": data["image/png"].strip(),
                        "media_type": "image/png",
                    })
                elif "image/jpeg" in data:
                    parsed.append({
                        "cell_id": cell_id,
                        "type": "image",
                        "data": data["image/jpeg"].strip(),
                        "media_type": "image/jpeg",
                    })

                # extract text output
                text_output: list[str] | None = None
                if output_type == "stream":
                    if "text" in raw_output:
                        text_output = raw_output["text"]
                elif output_type in ("display_data", "execute_result"):
                    if "text/html" in data:
                        text_output = data["text/html"]
                    elif "text/plain" in data:
                        text_output = data["text/plain"]

                if text_output is not None:
                    parsed.append({
                        "cell_id": cell_id,
                        "type": "output",
                        "content": "".join(text_output),
                    })

    return parsed
