"""Replay the public STEC tree and all 103 actual inline records."""

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.stec import CATALOG, TREE, StecCampus, recruitment_type
from job_crawler.models import Source
from job_crawler.transport import Session

FIX = Path(__file__).parent / "fixtures/stec"
TREE_DATA = json.loads((FIX / "tree.json").read_text())
CATALOGS = json.loads((FIX / "catalogs.json").read_text())


class Replay:
    last_evidence = "initial"

    def __init__(self, fault=""):
        self.fault = fault
        self.calls = []

    async def open(self, url, *, ready_endpoints=()):
        assert url == "https://zhaopin.stec.net/"

    async def observed(self, needle):
        return {"url": TREE, "post_data": '{"TypeCode":2}'}

    async def request(self, url, *, payload=None, detail=False):
        self.calls.append((url, payload))
        self.last_evidence = f"request-{len(self.calls)}"
        if url == TREE:
            d = copy.deepcopy(TREE_DATA)
            groups = d["Data"]["Type"]["Items"]
            if self.fault == "empty_tree":
                groups.clear()
            if self.fault == "empty_group":
                groups[0]["Items"].clear()
            if self.fault == "unit_duplicate":
                groups[1]["Items"].append(copy.deepcopy(groups[0]["Items"][0]))
            if self.fault == "new_public_branch":
                groups[0]["Items"][0]["Items"][0]["Text"] = "新增公开公司"
            return d
        assert url == CATALOG
        assert payload is not None
        assert payload["PageIndex"] == 0 and payload["PageSize"] == 1000
        assert payload["Category"] == ["2"] and payload["KeyWords"] == ""
        value = str(payload["ClassificationTwo"][0])
        d = copy.deepcopy(CATALOGS[value])
        if value == "15":
            row = d["Data"][0]
            if self.fault == "api":
                d["Code"] = 500
            if self.fault == "short":
                d["Data"].pop()
            if self.fault == "cap":
                d["Count"] = 1001
            if self.fault == "duplicate":
                d["Data"][-1] = copy.deepcopy(row)
            if self.fault == "unit":
                row["ClassificationTwo"] = "另一单位"
            if self.fault == "category":
                row["CategoryId"] = "1"
            if self.fault == "status":
                row["Status"] = 0
            if self.fault == "body":
                row["Require"] = ""
            if self.fault == "image":
                row["Require"] += '<img src="poster.png">'
            if self.fault == "date":
                row["PostDateInt"] += 86_400_000
            if self.fault == "deadline":
                row["EndTimeInt"] = 123
            if self.fault == "kind":
                row["Kind"] = "未知"
        if value == "12" and self.fault == "cross_duplicate":
            d["Data"][0]["Id"] = CATALOGS["15"]["Data"][0]["Id"]
        return d


def adapter(replay, now):
    return StecCampus(
        Source(
            source_id="COM0287",
            company_id="COM0287",
            company="上海隧道工程股份有限公司",
            url="https://zhaopin.stec.net/",
        ),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_all_units_and_mixed_roles(now):
    replay = Replay()
    result = await adapter(replay, now).collect()
    assert not result.issues and not result.coverage_issues()
    assert len(result.scopes) == 18
    assert sum(s.expected == 0 for s in result.scopes) == 6
    assert sum(s.unique for s in result.scopes) == 103
    assert len(result.jobs) == 103
    assert sum(j.work_type == "实习" for j in result.jobs) == 4
    assert sum(j.work_type == "社招" for j in result.jobs) == 10
    assert sum(j.work_type == "校招" for j in result.jobs) == 89
    assert all(
        j.deadline == "" and j.published and j.duties and j.requirements for j in result.jobs
    )
    assert all(j.company == "上海隧道工程股份有限公司" for j in result.jobs)
    assert len(replay.calls) == 19
    postdoc = next(j for j in result.jobs if "博士后" in j.title)
    assert postdoc.work_type == "校招"  # Explicitly accepts graduating PhDs; no invented five rows.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "empty_tree",
        "empty_group",
        "unit_duplicate",
        "new_public_branch",
        "api",
        "short",
        "cap",
        "duplicate",
        "unit",
        "category",
        "status",
        "body",
        "image",
        "date",
        "deadline",
        "kind",
        "cross_duplicate",
    ],
)
async def test_failures_do_not_become_complete_or_zero(now, fault):
    result = await adapter(Replay(fault), now).collect()
    assert result.issues
    if fault not in {"empty_tree", "empty_group", "unit_duplicate", "new_public_branch"}:
        assert result.jobs  # Other units survive isolated failure.
        assert result.coverage_issues()


@pytest.mark.parametrize(
    ("title", "requirements", "expected"),
    [
        ("设计(校招+社招)", "从事设计3年以上工作经验或工程师及以上职称优先", "校招"),
        ("设计(社招岗位)", "本科及以上", "社招"),
        ("项目经理", "8年以上相关专业咨询工作经验", "社招"),
        ("技术转移专员", "具备2年及以上创业孵化、项目管理或产学研协同相关实践经验", "社招"),
        ("研究员", "有3年以上研究经验者优先", "校招"),
        ("应届社招均可", "本科及以上", "校招"),
        ("设计师", "具有一定的监理行业工作经验，应届生也可", "校招"),
    ],
)
def test_scope_evidence(title, requirements, expected):
    assert (
        recruitment_type({"JobAdName": title, "Require": requirements, "Kind": "全职"}) == expected
    )
