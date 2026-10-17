from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.gem import GemCampus
from job_crawler.models import Source


def html() -> str:
    rows = "".join(
        f"<tr><td>{i}</td><td>类别{i}</td><td>材料、化学、机械</td></tr>" for i in range(1, 13)
    )
    return f"""<title>格林美2027届校园宣讲会</title><span>发布时间：2026-10-17</span>
    <div class="wp_articlecontent"><p>宣讲时间：10月20日</p><p>格林美 深交所 www.gem.com.cn</p>
    <p>1、招聘对象：2027年应届毕业生</p>
    <table><tr><td>序号</td><td>大类</td><td>细分</td></tr>{rows}</table>
    <p>本科：11万-16万</p><p>四、工作地点</p><p>聚焦国内外8个地点：广东深圳/湖北荆门/湖北武汉/江苏无锡/江苏泰州/福建宁德/印度尼西亚</p>
    <p>七、招聘时间</p><p>202 6年9月-2027年8月</p><p>八、联系方式</p><p>招聘邮箱:gem_hr@gem.com.cn</p></div>"""


class Replay:
    last_evidence = "fixture"

    def __init__(self, document: str):
        self.html = document
        self.page = self

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == f"https://{GemCampus.host}{GemCampus.path}"

    async def content(self) -> str:
        return self.html

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static circular needs no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static circular needs no API")


def source() -> Source:
    return Source(
        source_id="COM0392",
        company_id="COM0392",
        company="格林美股份有限公司",
        url=f"https://{GemCampus.host}{GemCampus.path}",
    )


async def test_all_categories_date_and_missing_fields(now: datetime) -> None:
    now = now.replace(year=2026, month=10, day=18)
    result = await GemCampus(source(), Replay(html()), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 12
    assert result.scopes[0].expected == result.scopes[0].details == 12
    job = result.jobs[0]
    assert job.published == "2026-10-17"
    assert "材料、化学、机械" in job.requirements
    assert "2026年9月-2027年8月" in job.requirements
    assert len(job.location.split("/")) == 7
    assert not any([job.duties, job.education, job.deadline])
    assert result.warnings[0].code == "source_location_count_mismatch"


@pytest.mark.parametrize(
    "before,after",
    [
        ("2027届校园宣讲会", "2026届校园宣讲会"),
        ("gem_hr@gem.com.cn", "other@example.com"),
        ("<td>12</td>", "<td>13</td>"),
        ("<td>类别12</td>", "<td>类别1</td>"),
        ("<td>材料、化学、机械</td>", "<td></td>"),
        ("</table>", '</table><img src="new.png">'),
        ("</table>", '</table><a href="jobs.xlsx">附件</a>'),
        ("2027年8月", "2027年9月"),
    ],
)
async def test_changed_or_incomplete_circular_fails(now: datetime, before: str, after: str) -> None:
    now = now.replace(year=2026, month=10, day=18)
    result = await GemCampus(source(), Replay(html().replace(before, after)), now).collect()
    assert result.coverage_issues()


async def test_old_circular_does_not_stay_current(now: datetime) -> None:
    now = now.replace(year=2027, month=9, day=1)
    result = await GemCampus(source(), Replay(html()), now).collect()
    assert result.coverage_issues() and not result.jobs
