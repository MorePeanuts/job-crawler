from datetime import datetime
from typing import Any

from job_crawler.adapters.greentown import GreentownCampus
from job_crawler.models import Source


def row(job_id: int) -> str:
    return f"""<tr><td><a href="/zpdetail/{job_id}">岗位{job_id}</a></td>
      <td>研发</td><td>校招生</td><td>浙江省-杭州市</td><td>2026-10-08</td></tr>"""


def listing(page: int, rows: str) -> str:
    return f"<html><body>共16条记录 当前第{page}/2页<table>{rows}</table></body></html>"


def detail_html(job_id: int) -> str:
    return f"""<html><body><div class="boxSupertitle"><span>岗位{job_id}</span></div>
      <ul><li class="ntitle">招聘类别：</li><li>校园招聘</li>
        <li class="ntitle">发布时间：</li><li>2026-10-08</li>
        <li class="ntitle">工作地点：</li><li>浙江省-杭州市</li></ul>
      <div class="xiangqingtext">
        <p class="title">工作职责：</p><p>负责开发</p>
        <p class="title">任职资格：</p><p>本科及以上</p>
      </div></body></html>"""


class Session:
    last_evidence = "fixture"

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("不应请求 JSON 接口")

    def __init__(self, second_id: int = 16):
        self.page = self
        self.second_id = second_id
        self.pages: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://gtgroup.zhiye.com/campus/"

    async def content(self) -> str:
        return listing(1, "".join(row(i) for i in range(1, 16)))

    async def request_html(
        self, url: str, *, form: dict[str, str] | None = None, detail: bool = False
    ) -> str:
        if "/zpdetail/" in url:
            return detail_html(int(url.rsplit("/", 1)[-1]))
        self.pages.append(url)
        return listing(2, row(self.second_id))


def source() -> Source:
    return Source(
        source_id="COM0166",
        company_id="COM0166",
        company="绿城中国控股有限公司",
        url="https://gtgroup.zhiye.com/Campus",
    )


async def test_greentown_paginates_and_joins_details(now: datetime) -> None:
    session = Session()
    result = await GreentownCampus(source(), session, now).collect()
    assert not result.coverage_issues()
    assert result.scopes[0].unique == result.scopes[0].details == 16
    assert session.pages == ["https://gtgroup.zhiye.com/campus/?PageIndex=2"]
    assert result.jobs[-1].requirements == "本科及以上"


async def test_greentown_duplicate_page_is_incomplete(now: datetime) -> None:
    result = await GreentownCampus(source(), Session(second_id=15), now).collect()
    assert result.coverage_issues()
    assert not result.scopes[0].terminal
