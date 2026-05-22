from llm_notebook_grader.digest import digest
from llm_notebook_grader.args import load_config, merge_config, setup_argument_parser
from llm_notebook_grader.actions import action_parse, action_extract, action_check, action_validate, action_report
from llm_notebook_grader.instant import action_instant, action_adjust


def main() -> None:
    parser = setup_argument_parser()
    args = parser.parse_args()

    file_config = load_config(args.config)
    config = merge_config(file_config, args)

    if args.action == "digest":
        digest(config)
    elif args.action == "parse":
        action_parse(args, config)
    elif args.action == "extract":
        action_extract(args, config)
    elif args.action == "check":
        action_check(args, config)
    elif args.action == "validate":
        action_validate(args, config)
    elif args.action == "report":
        action_report(args, config)
    elif args.action == "instant":
        action_instant(args, config)
    elif args.action == "adjust":
        action_adjust(args, config)
