"""Shougang's public campus catalog, restricted to the listed parent."""

from datetime import date
from typing import Any, Protocol, cast
from urllib.parse import urlencode

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://zp.shougang.com.cn"
COMPANY = "首钢集团有限公司"
ORG_API = ROOT + "/recruitFront/publish/orginfo?place=2"
LIST_API = ROOT + "/recruitFront/publish/publishjob"
PAGE_SIZE = 100


class ShougangSession(Protocol):
    last_evidence: str

    async def request(self, url: str, *, detail: bool = False) -> dict[str, Any]: ...


def _date(raw: object, field: str) -> str:
    check(isinstance(raw, str) and len(raw) >= 10, f"首钢{field}缺失")
    assert isinstance(raw, str)
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"首钢{field}格式变化") from exc


def _list_url(page: int) -> str:
    return (
        LIST_API
        + "?"
        + urlencode(
            {
                "place": "2",
                "page": str(page),
                "limit": str(PAGE_SIZE),
                "rmorg": "",
                "professional": "",
                "begindate": "",
                "postname": "",
                "workplace": "",
                "workplaceVal": "",
                "current": str(page),
                "pageSize": str(PAGE_SIZE),
                "total": "0",
            }
        )
    )


class ShougangCampus(Adapter):
    name = "shougang-campus-parent"
    host = "zp.shougang.com.cn"
    path = "/"
    scope_description = "首钢公开校园招聘全目录；仅精确标注首钢集团有限公司本级的岗位"
    ready_endpoints = ("/recruitFront/publish/publishjob?place=2",)

    async def harvest(self) -> None:
        session = cast(ShougangSession, self.session)
        organizations = await session.request(ORG_API)
        check(
            organizations.get("code") == "0"
            and isinstance(organizations.get("data"), list)
            and any(
                isinstance(row, dict) and row.get("pk_org") == COMPANY
                for row in organizations["data"]
            ),
            "首钢校招机构目录缺少集团本级",
        )
        org_evidence = session.last_evidence
        scope = Scope(name="campus-place-2")
        scope.evidence.append(org_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await session.request(_list_url(page))
            check(response.get("code") == "0", "首钢校招目录请求失败")
            rows = response.get("data")
            total = response.get("total")
            check(
                isinstance(rows, list)
                and isinstance(total, int)
                and total >= 0
                and len(rows) <= PAGE_SIZE,
                "首钢校招目录总数或分页结构变化",
            )
            assert isinstance(rows, list) and isinstance(total, int)
            if scope.expected is None:
                scope.expected = total
            check(total == scope.expected, "首钢校招目录总数在遍历中变化")
            list_evidence = session.last_evidence
            scope.evidence.append(list_evidence)
            for row in rows:
                check(isinstance(row, dict), "首钢校招岗位行结构变化")
                assert isinstance(row, dict)
                job_id = row.get("pk_publishjob")
                check(
                    isinstance(job_id, str) and bool(job_id) and job_id not in seen,
                    "首钢校招岗位 ID 缺失或重复",
                )
                seen.add(job_id)
                scope.listed += 1
                scope.unique += 1
                unit = row.get("rmorg")
                check(isinstance(unit, str) and bool(unit), "首钢校招岗位招聘主体缺失")
                if unit != COMPANY:
                    scope.skipped_out_of_scope += 1
                    continue
                deadline = _date(row.get("enddate"), "截止日期")
                if deadline < self.as_of.date().isoformat():
                    scope.skipped_expired += 1
                    continue
                published = _date(row.get("publishdate"), "发布日期")
                title = text(row.get("name"))
                check(bool(title), "首钢校招岗位标题缺失")
                job = self.job(
                    job_id,
                    title=title,
                    unit=COMPANY,
                    batch="校园招聘",
                    category_raw=text(row.get("professional")),
                    education=text(row.get("xlyqname")),
                    location=text(row.get("workplace")),
                    duties=text(row.get("responsibility") or row.get("description")),
                    requirements="\n".join(
                        value
                        for value in (
                            text(row.get("qualification")),
                            text(row.get("req_speciality")),
                        )
                        if value
                    ),
                    published=published,
                    deadline=deadline,
                    source_url=self.source.url,
                    field_sources={
                        "unit": "publishjob.rmorg；orginfo.pk_org 核对集团本级",
                        "title": "publishjob.name",
                        "category_raw": "publishjob.professional",
                        "education": "publishjob.xlyqname",
                        "location": "publishjob.workplace",
                        "duties": "publishjob.responsibility / description；缺失留空",
                        "requirements": "publishjob.qualification / req_speciality；缺失留空",
                        "published": "publishjob.publishdate",
                        "deadline": "publishjob.enddate",
                    },
                )
                job.evidence = [org_evidence, list_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            check(scope.unique <= total, "首钢校招目录行数超出总数")
            if scope.unique == total:
                scope.terminal = True
                break
            check(len(rows) == PAGE_SIZE, "首钢校招目录未到末页却少于整页")
            page += 1
