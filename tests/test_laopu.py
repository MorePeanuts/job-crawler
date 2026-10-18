import copy
import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.laopu import (
    ANNOUNCEMENT,
    CATALOG,
    COMPANY,
    EMPLOYER,
    LaopuCampus,
    Role,
    announcement,
    catalog_page,
    detail,
    employer,
    page_data,
    reconcile,
)
from job_crawler.filtering import select
from job_crawler.models import Job, Scope, Source
from job_crawler.transport import CrawlError, Session

NAMES = ["商品采购员", "仓管员", "质检员", "招聘经理助理", "电商客服员", "品牌店客服员"]


def wrap(data: dict[str, Any]) -> str:
    return "<script>window.PAGE_DATA = " + json.dumps(data, ensure_ascii=False) + ";</script>"


def profile() -> dict[str, Any]:
    return {
        "company_info": {"company_id": 117167, "company_name": COMPANY},
        "recruitment_list": [{"business_type": "宣讲会", "id": "716780"}],
        "recruitment_info": "",
    }


def rows() -> list[dict[str, Any]]:
    return [
        {
            "publish_id": i,
            "job_name": name,
            "city_name": city,
            "degree_require": degree,
            "create_time": "2023-1-1",
        }
        for i, name, city, degree in [
            (1, "商品采购员", "岳阳市", "本科及以上"),
            (2, "仓管员", "全国", "本科及以上"),
            (3, "质检员", "岳阳市", "本科及以上"),
            (4, "电商客服员", "岳阳市", "本科及以上"),
            (5, "品牌店客服员", "全国", "大专及以上"),
            (6, "品牌店客服员", "北京市", "本科及以上"),
        ]
    ]


def career() -> dict[str, Any]:
    parts = ["<p>老铺黄金 HK6181</p>", "<p>二、招聘岗位及薪资标准</p>"]
    for name in NAMES:
        loc = "" if name == "品牌店客服员" else "（工作地点：岳阳）"
        parts += [
            f"<p>【{name}】{loc}</p>",
            "<p>试用期月薪7000</p>",
            "<p>工作职责：</p>",
            "<p>做好岗位工作。</p>",
            "<p>任职要求：</p>",
            "<p>本科及以上学历。</p>",
        ]
    parts += [
        "<p>三、福利</p>",
        "<p>四、联系方式</p>",
        '<p><a href="/company-home">www.lphj.com</a></p>',
    ]
    return {
        "job_end_time": "2099-01-01",
        "career": {
            "company_id": 117167,
            "company_name": COMPANY,
            "career_talk_id": 716780,
            "docs": [],
            "practices": [],
            "remark": "".join(parts),
            "jobs": [rows()[i] for i in [1, 2, 3, 4]],
            "meet_time": "2026-09-15",
            "career_state": "已结束",
        },
    }


def posting(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job": {
            **row,
            "company_id": 117167,
            "company_name": COMPANY,
            "job_status": "招聘中",
            "publish_time": "2026年9月7日",
            "end_time": "2027年1月1日",
            "is_practice": 0,
            "work_address": None,
            "company_address": "北京市某总部大楼",
            "job_descript": "<p>岗位职责：</p><p>做好岗位工作。</p>",
            "job_require": "<p>任职要求：</p><p>本科及以上学历。</p>",
        }
    }


def test_catalog_and_announcement_union_preserves_same_title_different_ids() -> None:
    roles, cards = announcement(career())
    extra = reconcile(rows(), roles, cards)
    assert len(roles) == 6 and len(cards) == 4 and [r.name for r in extra] == ["招聘经理助理"]
    assert len({r["publish_id"] for r in rows()}) + len(extra) == 7
    assert sum(r["job_name"] == "品牌店客服员" for r in rows()) == 2
    assert "7000" not in extra[0].duties
    assert page_data(wrap(profile())) == profile()
    employer(profile())


@pytest.mark.parametrize("change", ["identity", "latest", "inline", "missing"])
def test_company_identity_and_latest_scope(change: str) -> None:
    p = profile()
    if change == "identity":
        p["company_info"]["company_id"] = 1
    elif change == "latest":
        p["recruitment_list"].insert(0, {"business_type": "宣讲会", "id": "999999"})
    elif change == "inline":
        p["recruitment_info"] = "额外招聘简章"
    else:
        p.pop("recruitment_list")
    with pytest.raises(CrawlError):
        employer(p)


@pytest.mark.parametrize(
    "html",
    [
        "<html>首页</html>",
        "<script>window.PAGE_DATA=[];</script>",
        wrap(profile()) + wrap(profile()),
    ],
)
def test_page_shell_and_duplicate_json_do_not_mean_zero(html: str) -> None:
    with pytest.raises(CrawlError):
        page_data(html)


@pytest.mark.parametrize(
    "change", ["attachment", "practice", "role", "card", "identity", "boundary"]
)
def test_announcement_scope_changes_fail(change: str) -> None:
    c = career()
    if change == "attachment":
        c["career"]["remark"] = c["career"]["remark"].replace(
            "<p>任职要求：</p>", '<p><img src="jobs.png">任职要求：</p>', 1
        )
    elif change == "practice":
        c["career"]["practices"] = [{"id": 2}]
    elif change == "role":
        c["career"]["remark"] = c["career"]["remark"].replace("【招聘经理助理】", "【新增角色】")
    elif change == "card":
        c["career"]["jobs"][0]["publish_id"] = 88
    elif change == "identity":
        c["career"]["company_id"] = 99
    else:
        c["career"]["remark"] = c["career"]["remark"].replace("三、福利", "三、其他")
    with pytest.raises(CrawlError):
        roles, cards = announcement(c)
        reconcile(rows(), roles, cards)


def test_dates_type_address_and_location_are_not_replaced_by_announcement() -> None:
    role = Role("仓管员", "岳阳", "职责", "要求")
    values = detail(posting(rows()[1]), rows()[1], role)
    assert values["published"] == "2026年9月7日" and values["deadline"] == "2027年1月1日"
    assert values["address"] == "" and values["location"] == "全国；校招简章：岳阳"
    values = detail(posting(rows()[0]), rows()[0], Role("商品采购员", "岳阳", "", ""))
    assert values["location"] == "岳阳市"
    p = posting(rows()[0])
    p["job"]["is_practice"] = 1
    p["job"]["job_status"] = "已过期"
    fields = detail(p, rows()[0], Role("商品采购员", "岳阳", "", ""))
    assert fields["work_type"] == "实习" and fields["closed"] and not fields["visible"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("company_id", 1),
        ("publish_id", 999),
        ("job_name", "错岗"),
        ("job_status", "未知"),
        ("end_time", "待定"),
        ("city_name", "深圳市"),
        ("job_descript", '<img src="more.png">'),
    ],
)
def test_details_cannot_silently_change_identity_or_fields(field: str, value: object) -> None:
    p = posting(rows()[0])
    p["job"][field] = value
    with pytest.raises(CrawlError):
        detail(p, rows()[0], Role("商品采购员", "岳阳", "", ""))


class Replay:
    last_evidence = "initial"

    def __init__(self) -> None:
        self.page = self
        self.url = ANNOUNCEMENT
        self.all_rows = rows()
        self.page_calls = []
        self.bad_id = ""
        self.mode = ""

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.url = url
        self.last_evidence = url

    async def content(self) -> str:
        if self.url == ANNOUNCEMENT:
            return wrap(career())
        key = parse_qs(urlsplit(self.url).query)["id"][0]
        row = next(r for r in self.all_rows if str(r["publish_id"]) == key)
        d = posting(row)
        if key == self.bad_id:
            d["job"]["company_id"] = 1
        return wrap(d)

    async def request_html(self, url: str) -> str:
        assert url == EMPLOYER
        self.last_evidence = url
        return wrap(profile())

    async def request(self, url: str) -> dict[str, Any]:
        assert url.startswith(CATALOG + "?company_id=117167&")
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        self.page_calls.append(page)
        self.last_evidence = f"catalog-page-{page}"
        data = self.all_rows[(page - 1) * 10 : page * 10]
        if self.mode == "repeat" and page > 1:
            data = self.all_rows[:10]
        if self.mode == "short" and page == 1:
            data = data[:3]
        total = len(self.all_rows) + (1 if self.mode == "change" and page > 1 else 0)
        return {"code": 1, "data": {"total": str(total), "items": copy.deepcopy(data)}}


def source() -> Source:
    return Source(source_id="COM0481", company_id="COM0481", company=COMPANY, url=ANNOUNCEMENT)


async def test_complete_union_and_missing_inline_dates(now: datetime) -> None:
    replay = Replay()
    result = await LaopuCampus(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 7
    assert [(s.expected, s.details) for s in result.scopes] == [(6, 6), (6, 6), (1, 1)]
    inline = next(j for j in result.jobs if j.source_key.startswith("career:"))
    assert inline.published == inline.deadline == inline.address == ""
    assert inline.evidence == [ANNOUNCEMENT] and select(inline, "all", now).reason == "eligible"
    assert len([j for j in result.jobs if j.title == "品牌店客服员"]) == 2


async def test_multiple_pages_and_per_page_evidence(now: datetime) -> None:
    replay = Replay()
    replay.all_rows += [{**rows()[0], "publish_id": 100 + i} for i in range(7)]
    result = await LaopuCampus(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues() and replay.page_calls == [1, 2]
    assert result.scopes[0].details == 13 and len(result.jobs) == 14
    assert next(j for j in result.jobs if j.source_key == "106").evidence[0] == "catalog-page-2"


@pytest.mark.parametrize("mode", ["repeat", "short", "change"])
async def test_incomplete_pages_fail(mode: str, now: datetime) -> None:
    replay = Replay()
    replay.mode = mode
    replay.all_rows += [{**rows()[0], "publish_id": 100 + i} for i in range(7)]
    result = await LaopuCampus(source(), cast(Session, replay), now).collect()
    assert result.coverage_issues() and not result.jobs


async def test_partial_failure_retains_other_jobs(now: datetime) -> None:
    replay = Replay()
    replay.bad_id = "2"
    result = await LaopuCampus(source(), cast(Session, replay), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 6
    assert result.scopes[0].unique == 6 and result.scopes[0].details == 5


async def test_incremental_full_union_reuse(now: datetime, monkeypatch: pytest.MonkeyPatch) -> None:
    first = await LaopuCampus(source(), cast(Session, Replay()), now).collect()
    cached = {j.source_key: j for j in first.jobs}
    fingerprints = []

    def before(
        self: Adapter,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job]:
        fingerprints.append(listing)
        assert evidence == ("catalog-page-1" if not entity.startswith("career:") else ANNOUNCEMENT)
        scope.reused_details += 1
        return [cached[entity]]

    monkeypatch.setattr(Adapter, "before_detail", before)
    replay = Replay()
    result = await LaopuCampus(source(), cast(Session, replay), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 7 and replay.url == ANNOUNCEMENT
    assert result.scopes[0].reused_details == 6 and result.scopes[-1].reused_details == 1
    assert len(fingerprints) == 7


def test_api_errors_are_not_empty_success() -> None:
    with pytest.raises(CrawlError):
        catalog_page({"code": 0, "data": {"total": "0", "items": []}})
    with pytest.raises(CrawlError):
        catalog_page({"code": 1, "data": {"total": "未知", "items": []}})
