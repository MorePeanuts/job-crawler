from datetime import datetime
from typing import Any

from job_crawler.adapters.cdkj import Cdkj
from job_crawler.models import Source


def html(*, second_id: str = "3", ctmid: str = "6628681") -> str:
    return f"""
    <p>2027届校园招聘</p>
    <div class="jobContent">
      <div class="jobtitle"><p class="jobname">研发设计</p></div>
      <div class="jobinfo">
        <div class="yq"></div><p class="job1">硕士及以上，微电子专业</p>
        <div class="fxs"><p>设计工程师</p></div>
        <a class="submit" href="https://xyz.51job.com/external/apply.aspx?jobid=1&ctmid=6628681">上海</a>
        <a class="submit" href="https://xyz.51job.com/external/apply.aspx?jobid=2&ctmid=6628681">江阴</a>
      </div>
    </div>
    <div class="jobContent">
      <div class="jobs"><p class="jobname1">制造工程师</p>
        <div class="jobinfo1">
          <p class="job1">机械专业</p><p class="job1">本科及以上</p>
          <p class="job1">负责工艺执行</p>
          <a class="submit" href="https://xyz.51job.com/external/apply.aspx?jobid={second_id}&ctmid={ctmid}">宿迁</a>
        </div>
      </div>
    </div>
    """


class Session:
    last_evidence = "fixture"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    def __init__(self, content: str):
        self.html = content
        self.page = self

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://campus.51job.com/cdkj26/job.html"

    async def content(self) -> str:
        return self.html


def source() -> Source:
    return Source(
        source_id="COM0381",
        company_id="COM0381",
        company="江苏长电科技股份有限公司",
        url="https://campus.51job.com/cdkj26/job.html",
    )


async def test_cdkj_counts_each_city_application(now: datetime) -> None:
    result = await Cdkj(source(), Session(html()), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 3
    assert {job.source_key for job in result.jobs} == {"1", "2", "3"}
    assert result.jobs[0].requirements == "硕士及以上，微电子专业"
    assert result.jobs[2].duties == "负责工艺执行"


async def test_cdkj_rejects_duplicate_or_wrong_tenant(now: datetime) -> None:
    for document in (html(second_id="2"), html(ctmid="other")):
        result = await Cdkj(source(), Session(document), now).collect()
        assert result.coverage_issues()
        assert result.scopes[0].terminal is False
