import json
from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.chd import (
    CATEGORIES,
    ChdCampus,
    Header,
    Notice,
    common_requirements,
    validate_notice,
    young_demands,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

BODY = "一、公司简介\n企业介绍。\n**二、招聘要求**\n本科及以上应届毕业生，专业符合要求。\n三、招聘程序\n报名和面试。"
TABLE = """
附表：中国华电青年骏才需求
|序号|需求单位|单位所在地|需求专业|
|:---:|:---:|:---:|:---:|
|1|山东公司|山东济南|能动类、电子信息类/计算机类|
|2|四川公司|四川成都|电子信息类/计算机类、数学类/统计学类|
"""


def notice(category: int) -> Notice:
    pk = category + 1
    return Notice.model_validate(
        {
            "pk": pk,
            "name": "2027年度招聘",
            "corp_pk": 100,
            "corp_ext_name": "中国华电集团有限公司",
            "zp_class_item_pk": category,
            "zp_class_item_ext_name": CATEGORIES[category],
            "begin_date": "2026-09-14 20:00:00",
            "end_date": "2026-10-18 23:59:20",
            "notice_status": 10,
            "off_status": 0,
            "content": BODY + (TABLE if category == 10010 else ""),
            "noticeFileList": [],
            "zpJobVOList": [
                {
                    "pk": category + 99,
                    "notice_pk": pk,
                    "name": "电气类",
                    "corp_pk": 100,
                    "corp_ext_name": "中国华电集团有限公司",
                    "job_status": 0,
                    "job_pro_requirements": "电气工程等专业",
                    "job_edu_requirements": "本科及以上",
                    "work_place": "北京市",
                }
            ],
        }
    )


def test_common_conditions_exclude_company_intro_and_application_procedure() -> None:
    assert common_requirements(BODY) == "本科及以上应届毕业生，专业符合要求。"
    assert common_requirements(BODY.replace("招聘要求", "招聘条件")) == common_requirements(BODY)
    with pytest.raises(CrawlError, match="条件缺失"):
        common_requirements("只有企业介绍")


def test_young_table_preserves_one_demand_per_unit() -> None:
    rows = young_demands(TABLE)
    assert len(rows) == 2 and rows[0].majors == "能动类、电子信息类/计算机类"
    assert rows[0].unit_location == "山东济南"


@pytest.mark.parametrize("change", ["heading", "duplicate", "sequence", "missing"])
def test_young_table_fails_on_unverified_structure(change: str) -> None:
    body = TABLE
    if change == "heading":
        body = body.replace("单位所在地", "工作地点")
    elif change == "duplicate":
        body = body.replace("四川公司", "山东公司")
    elif change == "sequence":
        body = body.replace("|2|", "|3|")
    else:
        body = BODY
    with pytest.raises(CrawlError):
        young_demands(body)


@pytest.mark.parametrize(
    "change", ["notice", "company", "post_duplicate", "status", "attachment", "image"]
)
def test_notice_identity_and_new_content_require_review(change: str) -> None:
    data = notice(10000)
    header = Header.model_validate(data.model_dump())
    if change == "notice":
        data.zpJobVOList[0].notice_pk += 1
    elif change == "company":
        data.zpJobVOList[0].corp_pk += 1
    elif change == "post_duplicate":
        data.zpJobVOList *= 2
    elif change == "status":
        data.zpJobVOList[0].job_status = 3
    elif change == "attachment":
        data.noticeFileList = [{"file": "positions.xlsx"}]
    else:
        data.content += '<img src="positions.png">'
    with pytest.raises(CrawlError):
        validate_notice(header, data)


class Replay:
    last_evidence = "fixture"

    def __init__(self, *, broken: bool = False, expired: bool = False):
        self.page = self
        self.current = ""
        self.reads: list[str] = []
        self.data = {key: notice(key) for key in CATEGORIES}
        self.broken = broken
        if expired:
            self.data[10000].end_date = "2026-01-01"

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.current = url

    async def content(self) -> str:
        return "中国华电集团有限公司"

    async def observed_path(self, path: str) -> dict[str, str]:
        if path.endswith("ZPClassItemIndex.json"):
            body = [{"pk": k, "name": v, "b_website_show": True} for k, v in CATEGORIES.items()]
        else:
            category = int(path.split("/")[-2])
            body = [Header.model_validate(self.data[category].model_dump()).model_dump()]
        return {"body": json.dumps(body, ensure_ascii=False)}

    async def request(self, url: str, *, detail: bool = False) -> dict[str, object]:
        self.reads.append(url)
        category = int(url.split("/")[-2])
        data = self.data[category].model_copy(deep=True)
        if self.broken and category == 10000:
            data.zpJobVOList[0].notice_pk = 9
        return data.model_dump()


def adapter(replay: Replay, now: datetime) -> ChdCampus:
    return ChdCampus(
        Source(
            source_id="COM0083",
            company_id="COM0083",
            company="中国华电集团有限公司",
            url="https://rencaishichang.chd.com.cn/",
        ),
        cast(Session, replay),
        now,
    )


@pytest.mark.asyncio
async def test_both_categories_expand_and_do_not_duplicate_young_portal_entries(
    now: datetime,
) -> None:
    result = await adapter(Replay(), now).collect()
    assert result.coverage_issues() == [] and len(result.jobs) == 3
    campus, *young = result.jobs
    assert campus.title == "电气类" and campus.education == "本科及以上"
    assert all(j.published == "" and j.duties == "" for j in result.jobs)
    assert all(j.location == j.address == "" for j in young)
    assert [j.unit for j in young] == ["山东公司", "四川公司"]
    assert "单位所在地（非岗位工作地点）：山东济南" in young[0].requirements
    assert len({j.source_key for j in result.jobs}) == 3


@pytest.mark.asyncio
async def test_failure_in_one_category_preserves_other_units(now: datetime) -> None:
    result = await adapter(Replay(broken=True), now).collect()
    assert result.coverage_issues() and len(result.jobs) == 2
    assert {j.unit for j in result.jobs} == {"山东公司", "四川公司"}


@pytest.mark.asyncio
async def test_expired_notice_is_accounted_without_fetching_detail(now: datetime) -> None:
    replay = Replay(expired=True)
    result = await adapter(replay, now).collect()
    assert result.coverage_issues() == [] and len(replay.reads) == 1
    assert result.scopes[0].skipped_expired == 1
