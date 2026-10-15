from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.zjjt import Zjjt2027, notices_from_article
from job_crawler.models import Source


def article(numbers: range, *, trainee: bool = False) -> str:
    rows = []
    for number in numbers:
        planned = 45 if trainee else 1
        rows.append(
            f"<tr><td>{number}</td><td>浙江省交通投资集团有限公司单位{number}</td>"
            f"<td>{planned}</td></tr><tr><td>"
            f"<a href='https://dhr.cncico.com:18443/noticeDetail/{1000 + number}'>"
            "PC端链接</a>"
            f"<a href='https://dhr.cncico.com/#/notice/detail?id={2000 + number}'>"
            "移动端链接</a></td></tr>"
        )
    return "<html><body>浙江省交通投资集团有限公司2027届校园招聘" + (
        "<table>" + "".join(rows) + "</table></body></html>"
    )


class Session:
    last_evidence = "fixture"

    def __init__(self, *, wrong_identity: bool = False):
        self.wrong_identity = wrong_identity
        self.opened: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        self.opened.append(url)

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError(f"unexpected observed request: {needle}")

    async def request_html(
        self,
        url: str,
        *,
        form: dict[str, str] | None = None,
        detail: bool = False,
        encoding: str = "utf-8",
        validate_html: bool = True,
    ) -> str:
        return (
            article(range(23, 24), trainee=True) if url.endswith("82696") else article(range(1, 23))
        )

    async def request(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        detail: bool = False,
        credentials: str = "include",
    ) -> dict[str, Any]:
        assert credentials == "omit"
        parts = urlsplit(url)
        params = parse_qs(parts.query)
        number = int(next(iter(params.values()))[0]) - 2000
        job_id = str(3000 + number)
        if parts.path.endswith("/detail"):
            return {
                "code": 200,
                "success": True,
                "data": {
                    "id": str(2000 + number),
                    "needsId": str(1000 + number),
                    "status": 2,
                    "isDeleted": 0,
                    "announceTitle": f"浙江省交通投资集团有限公司2027届{'管理培训生招聘' if number == 23 else '校园招聘'}公告",
                    "publishDate": "2026-09-10",
                    "announceContent": f"<a href='https://dhr.cncico.com:18443/postDetail/{job_id}'>应届生</a>",
                },
            }
        assert parts.path.endswith("/get-needs-detail")
        return {
            "code": 200,
            "success": True,
            "data": [
                {
                    "id": "wrong" if self.wrong_identity and number == 2 else job_id,
                    "needsId": str(1000 + number),
                    "status": 1,
                    "isDeleted": 0,
                    "recruitModeName": "面向集团内外部招聘" if number == 2 else "面向集团外部招聘",
                    "recruitNum": 45 if number == 23 else 1,
                    "postName": "应届生",
                    "postResponsibility": "负责集团项目",
                    "postQualification": "本科及以上学历",
                    "memberName": "集团总部" if number == 23 else "浙江交投",
                    "reportOrgName": f"单位{number}",
                    "workLocation": "浙江省杭州市",
                }
            ],
        }


def source() -> Source:
    return Source(
        source_id="COM0075",
        company_id="COM0075",
        company="浙江省交通投资集团有限公司",
        url="https://jt.hzshyy.com/content/82659",
    )


async def test_zjjt_all_notices_and_same_title_jobs_are_distinct(now: datetime) -> None:
    session = Session()
    result = await Zjjt2027(source(), session, now).collect()
    assert not result.coverage_issues()
    assert len(result.scopes) == len(result.jobs) == 23
    assert all(
        scope.expected == scope.listed == scope.unique == scope.details == 1
        for scope in result.scopes
    )
    assert len({job.source_key for job in result.jobs}) == 23
    assert all(job.title == "应届生" and job.published == "2026-09-10" for job in result.jobs)
    assert all("单位" in job.unit for job in result.jobs)
    assert session.opened[-1].startswith("https://dhr.cncico.com/")


async def test_zjjt_changed_job_identity_keeps_other_notices(now: datetime) -> None:
    result = await Zjjt2027(source(), Session(wrong_identity=True), now).collect()
    assert result.coverage_issues()
    assert len(result.jobs) == 22
    assert result.scopes[1].terminal is False
    assert all(scope.terminal for scope in result.scopes[:1] + result.scopes[2:])


def test_zjjt_article_rejects_missing_unit_branch() -> None:
    try:
        notices_from_article(article(range(1, 2)), 22)
    except Exception as exc:
        assert "数量变化" in str(exc)
    else:
        raise AssertionError("missing 21 units must fail")
