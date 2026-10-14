"""Chengdu Rural Commercial Bank's seven-card public campus catalog."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.cdrcb import FORM_ID, PROJECT_ID, ROOT, Cdrcb2027
from job_crawler.models import Source


class Page:
    def __init__(self, replay: "Replay"):
        self.replay = replay

    async def content(self) -> str:
        return self.replay.pages[self.replay.url]


class Replay:
    last_evidence = "entry.json"

    def __init__(self) -> None:
        self.url = ROOT + "/jobs/index.html"
        self.page = Page(self)
        self.pages = {
            self.url: (
                "<title>成都农商银行2027校园招聘</title><p>国内普通高等院校的2027年应届毕业生</p>"
            ),
            ROOT + "/liuc/index.html": (
                "<title>成都农商银行2027校园招聘</title><p>报名截止时间为2026年10月25日</p>"
            ),
        }
        titles = ["总行管理培训生", "总行金融科技岗", "储备培训生"] + [
            f"分支行岗位{i}" for i in range(4, 8)
        ]
        rows = []
        for index, title in enumerate(titles, 1):
            degree = "硕士研究生及以上" if index == 1 else "本科及以上"
            rows.append(
                {
                    "status": 1,
                    "projectId": PROJECT_ID,
                    "formId": FORM_ID,
                    "sortno": index,
                    "contentId": f"content-{index}",
                    "jsonContent": {
                        "title": f"{index}.{title}(10人)",
                        "url": (
                            "https://xiaoyuan.zhaopin.com/job/"
                            f"CC183402610J{index:010d}?jobSourceType=2"
                        ),
                        "content": (
                            f"<h4>招聘条件</h4><p>{degree}学历</p>"
                            "<h4>培养目标</h4><p>了解银行业务</p>"
                        ),
                    },
                }
            )
        self.response: dict[str, Any] = {
            "post_data": json.dumps(
                {
                    "projectId": PROJECT_ID,
                    "formId": FORM_ID,
                    "pageNo": 1,
                    "pageSize": 10,
                    "keywords": "",
                    "gidField": "",
                }
            ),
            "body": json.dumps(
                {
                    "code": 200,
                    "data": {"page": 1, "size": 10, "totalPage": 1, "total": 7, "list": rows},
                }
            ),
        }

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        if url not in self.pages:
            raise ValueError("页面读取失败")
        self.url = url
        self.last_evidence = url.rsplit("/", 1)[-1] + ".json"

    async def observed_path(self, path: str) -> dict[str, Any]:
        assert path == "/api/content/get-list"
        self.last_evidence = "api.json"
        return self.response

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected broad API lookup: {needle}")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(f"unexpected API request: {url}")

    def snapshot(self, label: str, html: str) -> str:
        assert html
        self.last_evidence = label + ".json"
        return self.last_evidence


def source() -> Source:
    return Source(
        source_id="COM0402",
        company_id="COM0402",
        company="成都农村商业银行股份有限公司",
        url=ROOT + "/jobs/index.html",
    )


async def test_cdrcb_complete_seven_categories_with_source_dates(now: datetime) -> None:
    replay = Replay()
    result = await Cdrcb2027(source(), replay, now).collect()
    assert result.coverage_issues() == []
    assert len(result.jobs) == 7
    assert result.scopes[0].expected == result.scopes[0].unique == result.scopes[0].details == 7
    assert result.scopes[0].terminal
    assert result.jobs[0].education == "硕士"
    assert result.jobs[1].education == "本科"
    assert all(job.published == job.duties == "" for job in result.jobs)
    assert all(job.deadline == "2026-10-25" for job in result.jobs)
    assert len({job.source_key for job in result.jobs}) == 7


async def test_cdrcb_rejects_changed_page_count_and_filtered_request(now: datetime) -> None:
    replay = Replay()
    response = json.loads(replay.response["body"])
    response["data"]["totalPage"] = 2
    replay.response["body"] = json.dumps(response)
    result = await Cdrcb2027(source(), replay, now).collect()
    assert result.coverage_issues()
    assert not result.jobs

    replay = Replay()
    payload = json.loads(replay.response["post_data"])
    payload["keywords"] = "科技"
    replay.response["post_data"] = json.dumps(payload)
    filtered = await Cdrcb2027(source(), replay, now).collect()
    assert filtered.coverage_issues()


async def test_cdrcb_rejects_duplicate_or_cross_tenant_identity(now: datetime) -> None:
    replay = Replay()
    response = json.loads(replay.response["body"])
    response["data"]["list"][1]["jsonContent"]["url"] = response["data"]["list"][0]["jsonContent"][
        "url"
    ]
    replay.response["body"] = json.dumps(response)
    duplicate = await Cdrcb2027(source(), replay, now).collect()
    assert duplicate.coverage_issues()
    assert len(duplicate.jobs) == 6

    replay = Replay()
    response = json.loads(replay.response["body"])
    response["data"]["list"][3]["jsonContent"]["url"] = (
        "https://xiaoyuan.zhaopin.com/job/CC999999999J123456?jobSourceType=2"
    )
    replay.response["body"] = json.dumps(response)
    wrong = await Cdrcb2027(source(), replay, now).collect()
    assert wrong.coverage_issues()
    assert len(wrong.jobs) == 6


async def test_cdrcb_deadline_change_blocks_catalog(now: datetime) -> None:
    replay = Replay()
    replay.pages[ROOT + "/liuc/index.html"] = replay.pages[ROOT + "/liuc/index.html"].replace(
        "2026年10月25日", "2026年10月15日"
    )
    result = await Cdrcb2027(source(), replay, now).collect()
    assert result.coverage_issues()
    assert not result.jobs
