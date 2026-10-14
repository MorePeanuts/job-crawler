import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from job_crawler.models import Job
from job_crawler.storage import write_json

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


@pytest.mark.parametrize("wrong_identity", [False, True])
def test_history_repair_requires_same_id_and_preserves_other_fields(
    tmp_path: Path, job: Job, wrong_identity: bool
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    raw = "【岗位职责】\n开发【系统】\n【任职要求】\n本科"
    job.duties = "【岗位职责】\n开发【系统】\n【"
    job.requirements = "】\n本科"
    evidence = tmp_path / "evidence.json"
    job.evidence = [str(evidence)]
    write_json(
        evidence,
        {
            "data": {
                "job": {"jobNumber": "wrong" if wrong_identity else job.source_key, "detail": raw}
            }
        },
    )
    write_json(source / "jobs.json", [job.model_dump(mode="json")])
    write_json(source / "delivered.json", [job.model_dump(mode="json")])
    write_json(
        source / "manifest.json",
        {
            "run_id": "original",
            "as_of": "2026-10-12T12:00:00+08:00",
            "bindings": {job.source_id: {"adapter": "zhaopin-unicom"}},
        },
    )
    process = subprocess.run(
        [sys.executable, "scripts/repair_description_snapshot.py", str(source), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    if wrong_identity:
        assert process.returncode != 0
        assert "Missing/ambiguous same-ID evidence" in process.stderr
        assert not output.exists()
        return
    assert process.returncode == 0, process.stderr
    result = json.loads((output / "delivered.json").read_text())[0]
    assert result == {
        **job.model_dump(mode="json"),
        "duties": "开发【系统】",
        "requirements": "本科",
    }


@pytest.mark.parametrize("invalid_patch", [False, True])
def test_workbook_patch_preserves_native_parts_and_shared_strings(
    tmp_path: Path, invalid_patch: bool
) -> None:
    source = tmp_path / "source.xlsx"
    authored = tmp_path / "authored.xlsx"
    output = tmp_path / "fixed.xlsx"
    patch = tmp_path / "patch.json"
    new = "开发【系统】\r\n测试"
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/sharedStrings.xml", f'<sst xmlns="{NS}"><si><t>【岗位职责】开发</t></si></sst>'
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{NS}"><sheetData>'
            '<row r="2"><c r="H2" s="6"/><c r="I2" s="6" t="s"><v>0</v></c>'
            '<c r="J2" s="6"/></row></sheetData><extLst/></worksheet>',
        )
        archive.writestr("xl/styles.xml", b"native-styles-unchanged")
        archive.writestr("xl/worksheets/sheet2.xml", b"native-validation-unchanged")
    with ZipFile(authored, "w", ZIP_DEFLATED) as archive:
        value = escape(new.replace("\r\n", "\n"))
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{NS}"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>I2</t></is></c>'
            f'<c r="B1" t="inlineStr"><is><t>{value}</t></is></c></row>'
            "</sheetData></worksheet>",
        )
    write_json(
        patch,
        [
            {
                "cell": "I2",
                "old": "wrong" if invalid_patch else "【岗位职责】开发",
                "new": new,
                "key": "source:job",
            }
        ],
    )
    process = subprocess.run(
        [
            sys.executable,
            "scripts/apply_description_workbook.py",
            str(source),
            str(patch),
            str(output),
            "--authored",
            str(authored),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if invalid_patch:
        assert process.returncode != 0
        assert "Original value mismatch" in process.stderr
        assert not output.exists()
        return
    assert process.returncode == 0, process.stderr
    with ZipFile(source) as original, ZipFile(output) as fixed:
        assert original.testzip() is None
        assert fixed.testzip() is None
        for name in original.namelist():
            if name != "xl/worksheets/sheet1.xml":
                assert fixed.read(name) == original.read(name)
        root = ET.fromstring(fixed.read("xl/worksheets/sheet1.xml"))
        cell = root.find(f'.//{{{NS}}}c[@r="I2"]')
        assert cell is not None and cell.get("s") == "6"
        assert cell.findtext(f"{{{NS}}}is/{{{NS}}}t") == new
