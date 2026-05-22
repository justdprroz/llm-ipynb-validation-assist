import json
import asyncio
from pathlib import Path

from llm_notebook_grader.selectors import select_submissions
from llm_notebook_grader.parse_cells import parse_ipynb
from llm_notebook_grader.data_layout import (
    get_submission_dir,
    get_next_revision,
    add_action_file,
    get_homework_dir,
    get_next_homework_revision,
    add_homework_action,
)
from llm_notebook_grader.task_extraction import extract_tasks_with_model
from llm_notebook_grader.task_checking import check_tasks_with_model, check_full_notebook_with_model, check_full_notebook_with_model_async
from llm_notebook_grader.validation import validate_cross_student
from llm_notebook_grader.reporting import generate_report
from llm_notebook_grader.git_ops import git_commit, git_push


def action_parse(args, config):
    data_dir = Path(config.data_dir)

    submissions = select_submissions(
        data_dir,
        submission_hash=args.hash,
        course=args.course,
        student=args.student,
        homework=args.homework,
    )

    if not submissions:
        print("No submissions found")
        return

    print(f"Parsing {len(submissions)} submission(s)")

    for entry in submissions:
        course = entry["course"]
        hash_val = entry["hash"]

        submission_dir = get_submission_dir(data_dir, course, hash_val)

        if not submission_dir.exists():
            print(f"  Error: submission dir not found for {hash_val[:8]}")
            continue

        ipynb_file = submission_dir / "source.ipynb"

        if not ipynb_file.exists():
            print(f"  Error: source.ipynb not found for {hash_val[:8]}")
            continue

        parsed_cells = parse_ipynb(filepath=str(ipynb_file))

        revision = get_next_revision(submission_dir, "parse")
        output_filename = f"parse_{revision}.json"
        output_path = submission_dir / output_filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(parsed_cells, f, indent=2, ensure_ascii=False)

        add_action_file(submission_dir, "parse", output_filename)

        print(f"  {hash_val[:8]}... -> {output_filename}")

        if config.git:
            student = entry.get("student", "unknown")
            git_commit(
                Path(config.data_dir),
                f"parse: {student} with revision {revision}"
            )

    if config.git:
        git_push(Path(config.data_dir))

    print("Parse complete")


def action_extract(args, config):
    data_dir = Path(config.data_dir)

    if not config.profile:
        print("Error: profile required for extract action")
        return

    submissions = select_submissions(
        data_dir,
        submission_hash=args.hash,
        course=args.course,
        student=args.student,
        homework=args.homework,
    )

    if not submissions:
        print("No submissions found")
        return

    print(f"Extracting tasks for {len(submissions)} submission(s)")

    for entry in submissions:
        course = entry["course"]
        hash_val = entry["hash"]

        
        submission_dir = get_submission_dir(data_dir, course, hash_val)

        if not submission_dir.exists():
            print(f"  Error: submission dir not found for {hash_val[:8]}")
            continue

        print(f"== Parsing {hash_val[:8]}")

        reasoning = args.reasoning if args.reasoning else config.reasoning

        success, revision = extract_tasks_with_model(
            submission_dir=submission_dir,
            provider=config.provider,
            model=config.model,
            api_key=config.api_key,
            yc_folder=config.yc_folder,
            reasoning=reasoning,
            profile=config.profile,
            debug=config.debug,
        )

        if success:
            print(f"  {hash_val[:8]}... -> extracted")

            if config.git:
                student = entry.get("student", "unknown")
                reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
                git_commit(
                    Path(config.data_dir),
                    f"extract: {student} using {config.provider}/{config.profile}/{reasoning_short} with revision {revision}"
                )
        else:
            print(f"  {hash_val[:8]}... -> failed")

    if config.git:
        git_push(Path(config.data_dir))

    print("Extract complete")


async def _check_submission_async(entry, config, args, data_dir):
    course = entry["course"]
    hash_val = entry["hash"]

    submission_dir = get_submission_dir(data_dir, course, hash_val)

    if not submission_dir.exists():
        print(f"  Error: submission dir not found for {hash_val[:8]}")
        return None

    print(f"== Checking {hash_val[:8]}")

    reasoning = args.reasoning if args.reasoning else config.reasoning

    success, revision = await check_full_notebook_with_model_async(
        submission_dir=submission_dir,
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        yc_folder=config.yc_folder,
        reasoning=reasoning,
        profile=config.profile,
        debug=config.debug,
        retry=config.retry,
    )

    return {
        "entry": entry,
        "success": success,
        "revision": revision,
        "reasoning": reasoning,
        "hash_val": hash_val,
    }


def action_check(args, config):
    data_dir = Path(config.data_dir)

    if not config.profile:
        print("Error: profile required for check action")
        return

    submissions = select_submissions(
        data_dir,
        submission_hash=args.hash,
        course=args.course,
        student=args.student,
        homework=args.homework,
    )

    if not submissions:
        print("No submissions found")
        return

    print(f"Checking tasks for {len(submissions)} submission(s)")

    full_notebook = getattr(args, "full_notebook", False)

    if full_notebook and len(submissions) > 1:
        async def run_parallel():
            tasks = [
                _check_submission_async(entry, config, args, data_dir)
                for entry in submissions
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run_parallel())

        for result in results:
            if result is None:
                continue

            success = result["success"]
            revision = result["revision"]
            hash_val = result["hash_val"]
            entry = result["entry"]
            reasoning = result["reasoning"]

            if success:
                print(f"  {hash_val[:8]}... -> full-checked")

                if config.git:
                    student = entry.get("student", "unknown")
                    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
                    git_commit(
                        Path(config.data_dir),
                        f"full-check: {student} using {config.provider}/{config.profile}/{reasoning_short} with revision {revision}"
                    )
            else:
                print(f"  {hash_val[:8]}... -> failed")
    else:
        for entry in submissions:
            course = entry["course"]
            hash_val = entry["hash"]

            submission_dir = get_submission_dir(data_dir, course, hash_val)

            if not submission_dir.exists():
                print(f"  Error: submission dir not found for {hash_val[:8]}")
                continue

            print(f"== Checking {hash_val[:8]}")

            reasoning = args.reasoning if args.reasoning else config.reasoning

            if full_notebook:
                success, revision = check_full_notebook_with_model(
                    submission_dir=submission_dir,
                    provider=config.provider,
                    model=config.model,
                    api_key=config.api_key,
                    yc_folder=config.yc_folder,
                    reasoning=reasoning,
                    profile=config.profile,
                    debug=config.debug,
                    retry=config.retry,
                )
            else:
                success, revision = check_tasks_with_model(
                    submission_dir=submission_dir,
                    provider=config.provider,
                    model=config.model,
                    api_key=config.api_key,
                    yc_folder=config.yc_folder,
                    reasoning=reasoning,
                    profile=config.profile,
                    debug=config.debug,
                    retry=config.retry,
                )

            if success:
                mode = "full-check" if full_notebook else "check"
                print(f"  {hash_val[:8]}... -> {mode}ed")

                if config.git:
                    student = entry.get("student", "unknown")
                    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
                    git_commit(
                        Path(config.data_dir),
                        f"{mode}: {student} using {config.provider}/{config.profile}/{reasoning_short} with revision {revision}"
                    )
            else:
                print(f"  {hash_val[:8]}... -> failed")

    if config.git:
        git_push(Path(config.data_dir))

    print("Check complete")


async def _fix_single_task(
    validation_file: Path,
    task_id: int,
    data_dir: Path,
    config,
    args,
):
    with open(validation_file, "r", encoding="utf-8") as f:
        validation_data = json.load(f)

    metadata = validation_data.get("validation_metadata", {})
    student_hashes = metadata.get("student_hashes", [])

    if not student_hashes:
        print("Error: no student hashes found in validation file")
        return False

    print(f"Fixing task {task_id} for {len(student_hashes)} students")

    submissions = []
    for hash_val in student_hashes:
        for course_dir in data_dir.iterdir():
            if not course_dir.is_dir():
                continue

            submissions_dir = course_dir / "submissions"
            if not submissions_dir.exists():
                continue

            student_dir = submissions_dir / hash_val
            if student_dir.exists():
                submissions.append({
                    "hash": hash_val,
                    "course": course_dir.name,
                    "homework": metadata.get("homework", "unknown"),
                })
                break

    if not submissions:
        print("Error: could not locate student submissions")
        return False

    from llm_notebook_grader.validation import validate_cross_student

    reasoning = args.reasoning if args.reasoning else config.reasoning

    success, validation_result = await validate_cross_student(
        submissions=submissions,
        data_dir=data_dir,
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        yc_folder=config.yc_folder,
        reasoning=reasoning,
        profile=config.profile,
        debug=config.debug,
        single_task_id=task_id,
    )

    if not success:
        print("Fix validation failed")
        return False

    new_task_reviews = validation_result.get("task_reviews", [])
    if not new_task_reviews:
        print("Error: no task review returned")
        return False

    new_review = new_task_reviews[0]

    task_reviews = validation_data.get("task_reviews", [])
    updated = False
    for i, review in enumerate(task_reviews):
        if review.get("task_id") == task_id:
            task_reviews[i] = new_review
            updated = True
            break

    if not updated:
        task_reviews.append(new_review)

    validation_data["task_reviews"] = task_reviews

    with open(validation_file, "w", encoding="utf-8") as f:
        json.dump(validation_data, f, indent=2, ensure_ascii=False)

    print(f"Updated task {task_id} in {validation_file}")
    return True


def action_validate(args, config):
    data_dir = Path(config.data_dir)

    if not config.profile:
        print("Error: profile required for validate action")
        return

    if hasattr(args, "fix") and args.fix:
        validation_file = Path(args.fix[0])
        try:
            task_id = int(args.fix[1])
        except ValueError:
            print(f"Error: task_id must be an integer, got '{args.fix[1]}'")
            return

        if not validation_file.exists():
            if validation_file.is_absolute():
                print(f"Error: validation file not found: {validation_file}")
                return

            found = False
            for course_dir in data_dir.iterdir():
                if not course_dir.is_dir():
                    continue
                for hw_dir in course_dir.iterdir():
                    if not hw_dir.is_dir():
                        continue
                    potential_file = hw_dir / validation_file.name
                    if potential_file.exists():
                        validation_file = potential_file
                        found = True
                        break
                if found:
                    break

            if not validation_file.exists():
                print(f"Error: validation file not found: {args.fix[0]}")
                print(f"Searched in homework directories under {data_dir}")
                return

        success = asyncio.run(
            _fix_single_task(validation_file, task_id, data_dir, config, args)
        )

        if success and config.git:
            git_commit(
                Path(config.data_dir),
                f"validate: fix task {task_id} in {validation_file.name}"
            )
            git_push(Path(config.data_dir))

        return

    submissions = select_submissions(
        data_dir,
        submission_hash=args.hash,
        course=args.course,
        student=args.student,
        homework=args.homework,
    )

    if not submissions:
        print("No submissions found")
        return

    if len(submissions) < 2:
        print("Error: validation requires at least 2 submissions")
        return

    course = submissions[0]["course"]
    homework = submissions[0].get("homework", "unknown")

    print(f"Validating {len(submissions)} submissions for {course}/{homework}")

    reasoning = args.reasoning if args.reasoning else config.reasoning

    success, validation_result = asyncio.run(
        validate_cross_student(
            submissions=submissions,
            data_dir=data_dir,
            provider=config.provider,
            model=config.model,
            api_key=config.api_key,
            yc_folder=config.yc_folder,
            reasoning=reasoning,
            profile=config.profile,
            debug=config.debug,
        )
    )

    if not success:
        print("Validation failed")
        return

    homework_dir = get_homework_dir(data_dir, course, homework)
    homework_dir.mkdir(parents=True, exist_ok=True)

    profile_id = config.profile
    revision = get_next_homework_revision(homework_dir, "validate", profile_id)

    output_filename = f"validate_{profile_id}_{revision}.json"
    output_path = homework_dir / output_filename

    validation_result["validation_metadata"]["homework"] = homework

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, indent=2, ensure_ascii=False)

    add_homework_action(homework_dir, "validate", output_filename)

    print(f"Validation saved to {output_path}")

    if config.git:
        git_commit(
            Path(config.data_dir),
            f"validate: {homework} using {config.provider}/{config.profile} with {len(submissions)} students"
        )
        git_push(Path(config.data_dir))

    print("Validate complete")


def action_report(args, config):
    data_dir = Path(config.data_dir)

    if not config.profile:
        print("Error: profile required for report action")
        return

    submissions = select_submissions(
        data_dir,
        submission_hash=args.hash,
        course=args.course,
        student=args.student,
        homework=args.homework,
    )

    if not submissions:
        print("No submissions found")
        return

    print(f"Generating reports for {len(submissions)} submission(s)")

    for entry in submissions:
        course = entry["course"]
        hash_val = entry["hash"]
        homework = entry.get("homework", "unknown")

        submission_dir = get_submission_dir(data_dir, course, hash_val)

        if not submission_dir.exists():
            print(f"  Error: submission dir not found for {hash_val[:8]}")
            continue

        print(f"== Reporting {hash_val[:8]}")

        reasoning = args.reasoning if args.reasoning else config.reasoning

        success, revision = generate_report(
            submission_dir=submission_dir,
            course=course,
            homework=homework,
            data_dir=data_dir,
            provider=config.provider,
            model=config.model,
            api_key=config.api_key,
            yc_folder=config.yc_folder,
            reasoning=reasoning,
            profile=config.profile,
            debug=config.debug,
        )

        if success:
            print(f"  {hash_val[:8]}... -> reported")

            if config.git:
                student = entry.get("student", "unknown")
                reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
                git_commit(
                    Path(config.data_dir),
                    f"report: {student} using {config.provider}/{config.profile}/{reasoning_short} with revision {revision}"
                )
        else:
            print(f"  {hash_val[:8]}... -> failed")

    if config.git:
        git_push(Path(config.data_dir))

    print("Report complete")
