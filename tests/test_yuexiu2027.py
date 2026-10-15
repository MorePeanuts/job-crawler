"""Replay Yuexiu's three-program embedded campus directory."""

import json
from datetime import datetime
from typing import Any

from job_crawler.adapters.yuexiu2027 import YuexiuProperty2027, parse_jobs
from job_crawler.models import Source


def script(*, wrong_project: bool = False, truncated: bool = False) -> str:
    nodes = []
    for index in range(30 if truncated else 31):
        identity = min(index, 29)
        url = (
            "https://xiaoyuan.zhaopin.com/scrd/postprocess2?"
            f"pid={identity}&projectId={999 if wrong_project else 105954}"
            f"&jobNumber=NO{identity}"
        )
        parts = [
            "<span>岗位描述：</span>",
            "负责产品研发",
            "<span>岗位要求：</span>",
            "本科及以上",
            "<span>工作城市：</span>" if index % 2 else "<span>工作地点：</span>",
            "广州",
        ]
        nodes.append(
            f"content:{json.dumps(f'职位{identity}', ensure_ascii=False)},"
            f"jobs_url:{json.dumps(url)}" + "}),t(n,{class:"
            '"grace-inner-web-content-text-job-text",textList:['
            + ",".join(f"{{text:{json.dumps(part, ensure_ascii=False)}}}" for part in parts)
            + "]})"
        )
    return "毓秀生（开发）毓秀生（商业）毓秀生（物业）" + "".join(nodes)


class Page:
    async def content(self) -> str:
        return '<html><body>毓秀生<script src="../assets/yxywl-5496e58d.js"></script></body></html>'


class Replay:
    last_evidence = "yuexiu-asset.js"
    page = Page()

    def __init__(self, *, wrong_project: bool = False, truncated: bool = False):
        self.body = script(wrong_project=wrong_project, truncated=truncated)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://yxdc2027.zhaopin.com/yxywl/index.html"

    async def request_html(self, url: str, *, validate_html: bool = True) -> str:
        assert url == "https://yxdc2027.zhaopin.com/assets/yxywl-5496e58d.js"
        assert not validate_html
        return self.body

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(needle)

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError(url)


def source() -> Source:
    return Source(
        source_id="COM0220",
        company_id="COM0220",
        company="越秀地产股份有限公司",
        url="https://yxdc2027.zhaopin.com/yxywl/index.html",
    )


async def test_yuexiu_full_three_program_directory(now: datetime) -> None:
    replay = Replay()
    assert len(parse_jobs(replay.body)) == 31
    result = await YuexiuProperty2027(source(), replay, now).collect()
    assert not result.coverage_issues()
    assert len(result.jobs) == result.scopes[0].unique == result.scopes[0].details == 30
    assert result.scopes[0].expected == result.scopes[0].listed == 30
    assert len({job.source_key for job in result.jobs}) == 30
    assert all(job.published == job.deadline == job.unit == "" for job in result.jobs)
    assert all(job.duties and job.requirements and job.location for job in result.jobs)


async def test_yuexiu_changed_identity_marks_partial(now: datetime) -> None:
    result = await YuexiuProperty2027(source(), Replay(wrong_project=True), now).collect()
    assert result.coverage_issues()
    assert result.jobs == []


async def test_yuexiu_truncated_directory_marks_partial(now: datetime) -> None:
    result = await YuexiuProperty2027(source(), Replay(truncated=True), now).collect()
    assert result.coverage_issues()
    assert result.jobs == []
