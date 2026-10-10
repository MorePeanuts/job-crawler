from pathlib import Path

from job_crawler.cli import main


def test_cli_checks_unknown_source_and_valid_config() -> None:
    assert main(["check"]) == 0
    assert main(["check", "--source", "MISSING"]) == 1


def test_cli_blocked_outputs_empty_template(tmp_path: Path) -> None:
    output = tmp_path / "blocked"
    code = main(
        [
            "run",
            "--source",
            "COM0001",
            "--output",
            str(output),
            "--state",
            str(tmp_path / "state.db"),
        ]
    )
    assert code == 2
    assert (output / "jobs.xlsx").is_file()


def test_import_does_not_overwrite_without_explicit_flag(tmp_path: Path) -> None:
    output = tmp_path / "sources.csv"
    args = ["sources", "import", "sites/sources.csv", "--file", str(output)]
    assert main(args) == 0
    assert main(args) == 1
