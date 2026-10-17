from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.guotai_haitong import GuotaiHaitongCampus
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, failure: str = ""):
        self.page = self
        self.failure = failure
        self.pages: list[int] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("public HTML")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("public HTML")

    async def evaluate(self, script: str) -> dict[str, str]:
        return {
            "url": "https://hr.gtht.com/recruitment/main/recruit2",
            "kind": "2,4",
            "company": "headquarter" if self.failure == "filter" else "",
        }

    def html(self, page: int) -> str:
        count = 32 if page == 2 and self.failure == "count" else 31
        ids = list(range((page - 1) * 30, min(page * 30, 31)))
        if page == 2 and self.failure == "duplicate":
            ids = [0]
        if page == 2 and self.failure == "empty":
            ids = []
        cards = []
        for key in ids:
            description = (
                ""
                if key == 0 and self.failure == "body"
                else "<p>【工作职责】</p><p>市场研究与客户服务</p><p>【任职要求】</p><p>金融本科</p>"
            )
            fields = "".join(
                f'<li class="list-li"><span class="con">{s}</span></li>'
                for s in [f"管培生{key}", "分公司", "本科及以上", "10", "上海，北京"]
            )
            cards.append(
                f'<ul>{fields}<li><a data-job_id="{key}">立即申请</a></li><li class="job-description-li" style="display:none"><h4>岗位描述</h4>{description}</li></ul>'
            )
        return (
            '国泰海通证券股份有限公司<div class="job-list-con">'
            + "".join(cards)
            + f'</div><script>var dataTotal={count};var current="{page}";var config={{pageSize:30}};</script>'
        )

    async def content(self) -> str:
        return self.html(1)

    async def request_html(
        self, url: str, *, form: dict[str, str], validate_html: bool = True
    ) -> str:
        assert not validate_html  # The actual public response omits the html document wrapper.
        assert form["company[]"] == "" and form["systemjobtype"] == "2,4" and form["n"] == "1"
        page = int(form["p"])
        self.pages.append(page)
        return self.html(page)


def source() -> Source:
    return Source(
        source_id="COM0199",
        company_id="COM0199",
        company="国泰海通证券股份有限公司",
        url="https://hr.gtht.com/recruitment/main/sy",
    )


async def test_complete_paging_folded_body_and_missing_dates(now: datetime) -> None:
    replay = Replay()
    result = await GuotaiHaitongCampus(source(), replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 31 and replay.pages == [2]
    job = result.jobs[0]
    assert job.duties == "市场研究与客户服务" and job.requirements == "金融本科"
    assert (
        job.unit == "分公司"
        and job.location == "上海，北京"
        and not job.deadline
        and not job.published
    )


@pytest.mark.parametrize("failure", ["count", "duplicate", "empty", "filter", "body"])
async def test_malformed_catalog_is_not_complete(now: datetime, failure: str) -> None:
    result = await GuotaiHaitongCampus(source(), Replay(failure), now).collect()
    assert result.coverage_issues()
    if failure != "filter":
        assert result.jobs
