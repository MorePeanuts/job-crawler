import json
from collections.abc import Awaitable
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.haidilao import (
    BRANDS,
    CATEGORIES,
    DETAIL,
    LABELS,
    MODULES,
    HaidilaoStoreTrainee,
    categories,
    data,
    project,
)
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session


def modules() -> list[dict[str, Any]]:
    content = {
        1: "<p>海底捞门店管培生项目，培养门店管理人才。</p>",
        2: "<p>1. 本科及以上学历，面向2027届应届生、2026届毕业一年内毕业生，可接受全国分配。</p>",
        3: "<p>福利说明</p>",
        4: "<p>管培生发展为正式店经理</p>",
        5: '<p>扫码投递<img src="/application-qr.png"></p>',
        6: None,
    }
    return [
        {
            "id": number + 20,
            "websiteStaffTypeConfigId": 6,
            "moduleType": number,
            "moduleName": name,
            "content": content[number],
            "isActive": 1,
            "isEnable": 1,
            "createTime": "2025-01-01",
            "updateTime": "2026-10-18",
        }
        for number, name in MODULES.items()
    ]


def category_rows() -> list[dict[str, Any]]:
    return [
        {"id": key, "staffTypeName": name, "brandId": "1567", "isActive": 1}
        for key, name in LABELS.items()
    ]


def page() -> str:
    return "".join(
        f'<div class="btnToggle" data-id="{key}">{value}</div>' for key, value in LABELS.items()
    )


def test_project_never_uses_employee_duties_or_configuration_dates() -> None:
    values = project(modules())
    assert values["duties"] == ""
    assert values["education"] == "本科及以上" and values["location"] == "全国"
    assert "2027届应届生" in values["requirements"]
    assert "published" not in values and "deadline" not in values
    changed = modules()
    changed[1]["content"] = (
        changed[1]["content"]
        .replace("本科及以上学历，", "")
        .replace("可接受全国分配", "地点另行确认")
    )
    assert project(changed)["education"] == project(changed)["location"] == ""


@pytest.mark.parametrize(
    "change", ["parent", "duplicate", "missing", "disabled", "scope", "attachment"]
)
def test_changed_modules_cannot_be_marked_complete(change: str) -> None:
    rows = modules()
    if change == "parent":
        rows[0]["websiteStaffTypeConfigId"] = 1
    elif change == "duplicate":
        rows[-1] = rows[0]
    elif change == "missing":
        rows.pop()
    elif change == "disabled":
        rows[1]["isEnable"] = 0
    elif change == "scope":
        rows[1]["content"] = "三年经验"
    else:
        rows[1]["content"] += '<img src="/requirements.png">'
    with pytest.raises(CrawlError):
        project(rows)


@pytest.mark.parametrize("change", ["brand", "extra", "dom", "inactive"])
def test_entire_category_directory_must_match_the_page(change: str) -> None:
    rows = category_rows()
    html = page()
    if change == "brand":
        rows[0]["brandId"] = "other"
    elif change == "extra":
        rows.append({"id": 9, "staffTypeName": "新项目", "brandId": "1567", "isActive": 1})
    elif change == "inactive":
        rows[-1]["isActive"] = 0
    else:
        html = html.replace("管培生", "博士项目")
    with pytest.raises(CrawlError):
        categories(rows, html)


def test_default_employee_response_and_business_failures_are_not_trainee_data() -> None:
    observed = {
        "url": DETAIL,
        "post_data": "configId=1",
        "body": json.dumps({"code": 200, "data": modules()}),
    }
    with pytest.raises(CrawlError):
        data(observed, DETAIL, {"configId": ["6"]})
    observed.update(post_data="configId=6", body=json.dumps({"code": 500, "data": []}))
    with pytest.raises(CrawlError):
        data(observed, DETAIL, {"configId": ["6"]})


class Waiting:
    async def __aenter__(self) -> "Waiting":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    @property
    def value(self) -> Awaitable["Waiting"]:
        async def response() -> Waiting:
            return self

        return response()

    status = 200

    async def finished(self) -> None:
        pass


class Replay:
    last_evidence = "catalog-evidence"

    def __init__(self) -> None:
        self.page = self
        self.config = SimpleNamespace(timeout=30)
        self.clicked = False

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://weihaizhaopin.wehichina.com/"

    async def observed(self, endpoint: str) -> dict[str, Any]:
        form = ""
        if endpoint == BRANDS:
            rows = [{"brandId": "1567", "brandName": "海底捞门店岗位"}]
        elif endpoint == CATEGORIES:
            rows = category_rows()
            form = "brandId=1567"
        else:
            assert endpoint == DETAIL and self.clicked
            rows = modules()
            form = "configId=6"
            self.last_evidence = "trainee-evidence"
        return {"url": endpoint, "post_data": form, "body": json.dumps({"code": 200, "data": rows})}

    async def content(self) -> str:
        return page()

    def consume_request(self) -> None:
        pass

    def expect_response(self, predicate: object, *, timeout: int) -> Waiting:
        return Waiting()

    def locator(self, selector: str) -> "Replay":
        assert selector == '.btnToggle[data-id="6"]'
        return self

    async def click(self) -> None:
        self.clicked = True


def source() -> Source:
    return Source(
        source_id="COM0348",
        company_id="COM0348",
        company="海底捞国际控股有限公司",
        url="https://weihaizhaopin.wehichina.com/",
    )


async def test_three_categories_one_project_and_missing_fields(now: datetime) -> None:
    replay = Replay()
    result = await HaidilaoStoreTrainee(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues() and replay.clicked
    scope = result.scopes[0]
    assert scope.expected == scope.listed == scope.unique == 3
    assert scope.skipped_out_of_scope == 2 and scope.details == 1
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "管培生" and job.source_key == "config:6"
    assert job.published == job.deadline == job.duties == job.address == ""
    assert job.evidence == ["catalog-evidence", "trainee-evidence"]
    assert result.warnings[0].code == "application_portal_unverified"


async def test_incremental_fingerprint_contains_modules_not_backoffice_names(
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
) -> None:
    def before(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job]:
        assert isinstance(listing, list) and len(listing) == 6
        assert all(
            "content" in row and "createTime" not in row and "updateByName" not in row
            for row in listing
        )
        scope.reused_details += 1
        return [self.job("config:6", title="管培生", source_url=self.source.url)]

    monkeypatch.setattr(Adapter, "before_detail", before)
    result = await HaidilaoStoreTrainee(source(), cast(Session, Replay()), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].reused_details == 1 and result.scopes[0].details == 0
