import hashlib
import shutil
from pathlib import Path

from llm_notebook_grader.selectors import load_main_db, save_main_db
from llm_notebook_grader.data_layout import (
    get_submission_dir,
    save_submission_db,
    create_symlink_safe,
)


def calculate_file_hash(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def digest(config) -> None:
    digest_dir = Path(config.digest_dir)
    data_dir = Path(config.data_dir)

    if not digest_dir.exists():
        print(f"Error: digest directory not found: {digest_dir}")
        return

    print(f"Digesting from: {digest_dir}")
    print(f"Data directory: {data_dir}")

    main_db = load_main_db(data_dir)
    processed_count = 0

    for course_dir in digest_dir.iterdir():
        if not course_dir.is_dir():
            continue

        course_name = course_dir.name
        print(f"\nCourse: {course_name}")

        for homework_dir in course_dir.iterdir():
            if not homework_dir.is_dir():
                continue

            homework_number = homework_dir.name
            print(f"  Homework: {homework_number}")

            for file_path in homework_dir.iterdir():
                if file_path.is_dir() or not file_path.suffix == ".ipynb":
                    continue

                file_hash = calculate_file_hash(file_path)

                if file_hash in main_db:
                    print(f"    Skip {file_path.name} (exists)")
                    continue

                student_name = file_path.stem

                submission_dir = get_submission_dir(data_dir, course_name, file_hash)
                submission_dir.mkdir(parents=True, exist_ok=True)

                dest_path = submission_dir / "source.ipynb"
                shutil.move(str(file_path), str(dest_path))

                main_db[file_hash] = {
                    "course": course_name,
                    "student": student_name,
                    "homework": homework_number,
                }

                submission_db = {
                    "student_name": student_name,
                    "homework_number": homework_number,
                    "course": course_name,
                    "source": ["source.ipynb"],
                    "actions": {},
                }
                save_submission_db(submission_dir, submission_db)

                student_dir = data_dir / course_name / student_name
                hw_link = student_dir / homework_number
                create_symlink_safe(submission_dir, hw_link)

                hw_dir = data_dir / course_name / homework_number
                student_link = hw_dir / student_name
                create_symlink_safe(submission_dir, student_link)

                print(f"    {student_name}.ipynb -> {file_hash[:8]}")
                processed_count += 1

            if homework_dir.exists() and not any(homework_dir.iterdir()):
                homework_dir.rmdir()
                print(f"    Removed empty homework directory")

        if course_dir.exists() and not any(course_dir.iterdir()):
            course_dir.rmdir()
            print(f"  Removed empty course directory")

    save_main_db(data_dir, main_db)
    print(f"\nDigest complete: {processed_count} file(s) processed")
