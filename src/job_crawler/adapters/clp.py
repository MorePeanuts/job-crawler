"""中电控股官网 2027 见习工程师项目及公开 Oracle 职位详情。"""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

PROGRAMME = "CLP Engineering Graduate Trainee Programme 2027"
APPLY_URL = "https://e.clp.com.hk/gt2027"
ORACLE = "iabhtj.fa.ocs.oraclecloud.com"
DETAIL_PATH = "/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
EMPLOYER_ID = 300000005637185


def programme_link(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    page = soup.get_text(" ", strip=True)
    check(
        "CLP Holdings Limited" in page
        and "Engineering Graduate Trainee Programme" in page
        and "6 December 2026" in page
        and "final-year student" in page,
        "中电控股2027项目身份、资格或截止日期改变",
    )
    links = [
        str(anchor.get("href", ""))
        for anchor in soup.select("a[href]")
        if anchor.get_text(" ", strip=True) == "Apply Now"
    ]
    check(bool(links) and set(links) == {APPLY_URL}, "中电控股见习工程师申请入口改变")
    return APPLY_URL


def detail(observed: dict[str, Any]) -> dict[str, Any]:
    url = urlsplit(str(observed.get("url") or ""))
    finder = parse_qs(url.query).get("finder", [""])[0]
    check(
        url.scheme == "https"
        and url.hostname == ORACLE
        and url.path == DETAIL_PATH
        and finder == 'ById;Id="1125",siteNumber=CX_1',
        "中电控股 Oracle 职位详情接口改变",
    )
    data = json.loads(str(observed.get("body") or ""))
    rows = data.get("items")
    check(
        data.get("count") == 1 and isinstance(rows, list) and len(rows) == 1, "中电控股详情计数改变"
    )
    row = rows[0]
    check(
        str(row.get("Id")) == "1125"
        and row.get("Title") == PROGRAMME
        and row.get("RequisitionType") == "Programme"
        and row.get("JobSchedule") == "Full time"
        and row.get("LegalEmployerId") == EMPLOYER_ID
        and row.get("PrimaryLocationCountry") == "HK"
        and row.get("ApplyWhenNotPostedFlag") is False,
        "中电控股公开岗位身份、主体或工作类型改变",
    )
    published = datetime.fromisoformat(str(row["ExternalPostedStartDate"]))
    deadline = datetime.fromisoformat(str(row["ExternalPostedEndDate"]))
    check(
        published.tzinfo is not None
        and deadline.tzinfo is not None
        and deadline.date().isoformat() == "2026-12-06"
        and deadline > published,
        "中电控股公开岗位日期与官网不一致",
    )
    return row


def job_sections(html: str) -> tuple[str, str]:
    body = text(html).replace("\xa0", " ")
    marker = "Who are we looking for?"
    check(marker in body, "中电控股岗位资格章节缺失")
    duties, qualifications = body.split(marker, 1)
    requirements = qualifications.split("Remarks:", 1)[0].strip()
    check(
        bool(duties.strip()) and "Bachelor's degree or above" in requirements,
        "中电控股岗位正文或学历改变",
    )
    return duties.strip(), requirements


class ClpGraduate2027(Adapter):
    name = "clp-graduate-2027"
    host = "www.clpgroup.com"
    path = "/en/careers/working-at-clp/graduate-trainee.html"
    scope_description = "中电控股官方2027见习工程师计划，正式大学毕业生岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "中电控股项目页未就绪")
        programme_evidence = self.session.last_evidence
        apply = programme_link(await session.page.content())
        await self.session.open(
            apply,
            ready_endpoints=(f"https://{ORACLE}{DETAIL_PATH}",),
        )
        check(
            urlsplit(session.page.url).hostname == ORACLE
            and urlsplit(session.page.url).path.endswith("/job/1125"),
            "中电控股官方申请入口未跳转当前项目岗位",
        )
        observed = await self.session.observed(DETAIL_PATH)
        row = detail(observed)
        detail_evidence = self.session.last_evidence
        duties, requirements = job_sections(str(row["ExternalDescriptionStr"]))
        scope = Scope(name="clp-engineering-graduate-2027", expected=1)
        scope.evidence.append(programme_evidence)
        self.result.scopes.append(scope)
        self.add_page(scope, [row], set(), lambda item: str(item["Id"]))
        listing = self.job(
            "1125",
            title=PROGRAMME,
            source_url=session.page.url,
            apply_url=apply,
            unit="CLP Holdings Limited",
            education="本科及以上",
            location=text(row["PrimaryLocation"]),
            category_raw=text(row.get("Category")),
            duties=duties,
            requirements=requirements,
            published=str(row["ExternalPostedStartDate"]),
            deadline=str(row["ExternalPostedEndDate"]),
            field_sources={
                "unit": "recruitingCEJobRequisitionDetails.LegalEmployerId=300000005637185",
                "education": "ExternalDescriptionStr: Bachelor's degree or above",
                "duties": "ExternalDescriptionStr: programme description",
                "requirements": "ExternalDescriptionStr: Who are we looking for?",
                "published": "ExternalPostedStartDate",
                "deadline": "ExternalPostedEndDate；官网 6 December 2026",
            },
        )
        listing.evidence = [programme_evidence, detail_evidence]
        reused = self.before_detail("job:1125", row, scope, listing, evidence=detail_evidence)
        if reused is not None:
            self.result.jobs.extend(reused)
        else:
            self.result.jobs.append(listing)
            scope.details += 1
            self.remember("job:1125", row, [listing])
        scope.terminal = True
