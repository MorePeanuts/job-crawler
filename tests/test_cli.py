from pathlib import Path

import pytest

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


def test_validation_error_does_not_echo_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "bad.toml"
    config.write_text('[llm]\napi_key="do-not-print-test-secret"\n')
    assert main(["check", "--config", str(config)]) == 1
    assert "do-not-print-test-secret" not in capsys.readouterr().err


def test_bundle_requires_input_and_valid_path_array(tmp_path: Path) -> None:
    assert main(["bundle", "--output", str(tmp_path / "empty")]) == 1
    path = tmp_path / "bad.json"
    path.write_text('{"not":"an array"}')
    assert main(["bundle", "--inputs-file", str(path), "--output", str(tmp_path / "bad")]) == 1
