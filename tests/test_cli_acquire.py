from loto.cli import build_parser


def test_new_cli_commands_parse():
    args = build_parser().parse_args(
        ["data", "acquire", "--game", "loto7", "--output", "x", "--source-file", "a.csv"]
    )
    assert args.action == "acquire"
    args = build_parser().parse_args(
        ["experiment", "run-all", "--output", "x", "--source-file", "a.csv"]
    )
    assert args.action == "run-all"
