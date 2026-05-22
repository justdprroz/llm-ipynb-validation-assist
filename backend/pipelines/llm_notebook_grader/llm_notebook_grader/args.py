import tomllib
import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    data_dir: str = ""
    digest_dir: str = ""
    profile: Optional[str] = None
    default_profile: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    yc_folder: Optional[str] = None
    reasoning: str = "standard"
    retry: int = 3
    git: bool = False
    debug: bool = False


def load_config(config_path: str) -> dict:
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def load_profile(file_config: dict, profile_name: str) -> dict:
    profiles = file_config.get("profiles", {})
    if profile_name not in profiles:
        raise ValueError(f"Profile '{profile_name}' not found in config")
    return profiles[profile_name].copy()


def merge_config(file_config: dict, args: argparse.Namespace) -> Config:
    config_dict = {}

    settings = file_config.get("settings", {})
    config_dict.update(settings)

    profile_name = args.profile if args.profile else settings.get("default_profile")

    if profile_name:
        profile_config = load_profile(file_config, profile_name)
        config_dict.update(profile_config)
        config_dict["profile"] = profile_name

    if hasattr(args, "debug") and args.debug:
        config_dict["debug"] = True

    if hasattr(args, "retry") and args.retry is not None:
        config_dict["retry"] = args.retry

    return Config(**{k: v for k, v in config_dict.items() if k in Config.__annotations__})


def setup_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM-Assisted Notebook Validation"
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to config file",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Profile name from config",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full prompts to stderr for debugging",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=None,
        help="Max retries per task on inference failure (default: 3)",
    )

    subparsers = parser.add_subparsers(dest="action", required=True)

    parser_digest = subparsers.add_parser("digest", help="Import files from digest directory")

    parser_parse = subparsers.add_parser("parse", help="Parse notebook cells")
    add_selector_args(parser_parse)

    parser_extract = subparsers.add_parser("extract", help="Extract tasks from notebook")
    add_selector_args(parser_extract)

    parser_check = subparsers.add_parser("check", help="Check tasks")
    add_selector_args(parser_check)
    parser_check.add_argument(
        "--full-notebook",
        action="store_true",
        default=False,
        help="Grade directly from parsed cells without extraction step",
    )

    parser_validate = subparsers.add_parser("validate", help="Validate checking results")
    add_selector_args(parser_validate)
    parser_validate.add_argument(
        "--fix",
        nargs=2,
        metavar=("FILE", "TASK_ID"),
        help="Fix single task: --fix <validation_file> <task_id>",
    )

    parser_report = subparsers.add_parser("report", help="Generate final report")
    add_selector_args(parser_report)

    parser_instant = subparsers.add_parser("instant", help="Grade notebooks against reference")
    parser_instant.add_argument(
        "--reference",
        type=str,
        required=True,
        help="Path to reference (10/10) notebook",
    )
    parser_instant.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input directory with student folders",
    )
    parser_instant.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output directory for per-student reports",
    )
    parser_instant.add_argument(
        "--effort",
        type=str,
        choices=["light", "normal", "strict"],
        default="normal",
        help="Grading strictness (light/normal/strict)",
    )

    parser_adjust = subparsers.add_parser("adjust", help="Adjust grading results with a correction prompt")
    parser_adjust.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output directory from instant run",
    )
    parser_adjust.add_argument(
        "--prompt",
        type=str,
        required=True,
        help="Correction instruction for re-grading",
    )
    parser_adjust.add_argument(
        "--task",
        type=str,
        default=None,
        help="Task ID(s) to adjust, comma-separated (default: all)",
    )
    parser_adjust.add_argument(
        "--student",
        type=str,
        default=None,
        help="Student name filter (substring match)",
    )

    return parser


def add_selector_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("hash", nargs="?", default=None, help="Submission hash")
    parser.add_argument("--course", type=str, default=None, help="Filter by course")
    parser.add_argument("--student", type=str, default=None, help="Filter by student")
    parser.add_argument("--homework", type=str, default=None, help="Filter by homework")
    parser.add_argument(
        "--reasoning",
        type=str,
        choices=["restrictive", "standard", "verbose"],
        default=None,
        help="Reasoning mode (restrictive/standard/verbose)",
    )
