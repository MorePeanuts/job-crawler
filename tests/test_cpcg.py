from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.cpcg import CpcgCampus
from job_crawler.models import Source


def card(title: str, body: str = "<p>全日制本科，能接受外派工作</p>") -> str:
    return f'<div class="xyzp-item"><div class="xyzp-item-title"><h1>{title}</h1><div class="xyzp-item-info"><p>学历：本科及以上</p><p>专业：土木工程、工程管理</p></div></div><div class="xyzp-item-bottom" style="display:none">{body}</div></div>'


class Replay:
    last_evidence = "fixture"

    def __init__(self, html: str):
        self.html = html
        self.page = self

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == f"https://{CpcgCampus.host}{CpcgCampus.path}"

    async def content(self) -> str:
        return self.html

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static cards need no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static cards need no API")


def source() -> Source:
    return Source(
        source_id="COM0046",
        company_id="COM0046",
        company="太平洋建设集团有限公司",
        url=f"https://{CpcgCampus.host}{CpcgCampus.path}",
    )


async def test_hidden_requirements_and_unsplit_categories(now: datetime) -> None:
    html = (
        "太平洋建设 版权所有 Campus Recruiting" + card("工程类") + card("职能类") + card("市场类")
    )
    result = await CpcgCampus(source(), Replay(html), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 3
    job = result.jobs[0]
    assert "能接受外派工作" in job.requirements and "土木工程" in job.requirements
    assert job.education == "本科及以上"
    assert not any([job.published, job.deadline, job.location, job.duties])


@pytest.mark.parametrize(
    "cards",
    [
        "",
        card("工程类") + card("工程类"),
        card("工程类", ""),
        card("工程类") + '<div class="pagination">2</div>',
    ],
)
async def test_missing_duplicate_or_incomplete_source_is_explicit(
    now: datetime, cards: str
) -> None:
    result = await CpcgCampus(
        source(), Replay("太平洋建设 版权所有 CAMPUS RECRUITING" + cards), now
    ).collect()
    assert result.coverage_issues()
