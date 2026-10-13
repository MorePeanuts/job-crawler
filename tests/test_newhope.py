from datetime import datetime
from typing import Any

from job_crawler.adapters.newhope import NewHopeCampus
from job_crawler.models import Source


def html(count: int = 1) -> str:
    return f"""<html><body><ul><li><h2>
      <span class="pl25">技术岗(J1)</span><span>研发</span><span>3</span>
      <span>四川省...</span><span>2026-09-15</span><span>详情</span></h2>
      <div class="zwlbb"><div class="zwlbbt"><span>工作地点：<b>四川省,云南省</b></span></div>
      <div class="zwlbbm"><h3>【岗位职责】</h3><p>负责研发</p>
      <h3>【任职要求】</h3><p>本科及以上</p></div>
      <a jobadid="123" href="javascript:void(0)">立即申请</a></div></li></ul>
      共{count}条记录</body></html>"""


class Session:
    last_evidence = "fixture"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    def __init__(self, count: int = 1):
        self.page = self
        self.count = count

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://newhope.zhiye.com/xzzw"

    async def content(self) -> str:
        return html(self.count)


def source() -> Source:
    return Source(
        source_id="COM0118",
        company_id="COM0118",
        company="新希望控股集团有限公司",
        url="https://newhope.zhiye.com/campus",
    )


async def test_newhope_inline_details(now: datetime) -> None:
    result = await NewHopeCampus(source(), Session(), now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].expected == result.scopes[0].details == 1
    assert result.jobs[0].location == "四川省,云南省"
    assert result.jobs[0].requirements == "本科及以上"
    assert result.jobs[0].deadline == ""


async def test_newhope_count_mismatch_is_incomplete(now: datetime) -> None:
    result = await NewHopeCampus(source(), Session(2), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
