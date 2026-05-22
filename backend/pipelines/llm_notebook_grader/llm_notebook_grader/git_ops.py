import subprocess
from pathlib import Path


def git_commit(data_dir: Path, message: str) -> bool:
    try:
        subprocess.run(
            ["git", "-C", str(data_dir), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(data_dir), "commit", "--no-gpg-sign", "-m", message],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_push(data_dir: Path) -> bool:
    try:
        subprocess.run(
            ["git", "-C", str(data_dir), "push"],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False
