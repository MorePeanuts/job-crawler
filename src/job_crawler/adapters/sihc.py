"""Shenzhen Investment's public Iucai company directory and rendered details."""

import json
from math import ceil
from typing import cast

from pydantic import BaseModel, Field

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Job, Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

COMPANY = "dc2d34aa-6023-49ce-9031-3ee098a2de74"
COMPANY_NAME = "深圳市投资控股有限公司"
FIELDS = (
    "recruitId companyId CR_COMPANY_ID jobTitle displayName companyName jobType jobTypeDsc "
    "requireEduDsc workCityDsc address lastUpdateDt endDate pubState "
    "recruitType jobResp jobReq"
).split()
PICK = f"const keys={json.dumps(FIELDS)}; const pick=x=>Object.fromEntries(keys.filter(k=>k in x).map(k=>[k,x[k]]));"
CATALOG_JS = (
    """() => {
let c=document.querySelector('.el-pagination')?.__vueParentComponent;
while(c&&!c.setupState?.jobPage)c=c.parent;
const d=c?.setupState;
if(!d||d.jobLoading||d.dataLoading||!Array.isArray(d.jobList))return null;
"""
    + PICK
    + """
return {page:d.jobPage,companyId:d.companyId,companyName:d.companyData.displayName,
rows:d.jobList.map(pick),
visibleIds:[...document.querySelectorAll('.job_box a[href]')].map(a=>new URLSearchParams(a.hash.split('?')[1]).get('recruitId')),
terminal:document.querySelector('.el-pagination .btn-next')?.disabled===true};
}"""
)
DETAIL_JS = (
    """() => {
const c=document.querySelector('.job_content_l')?.__vueParentComponent;
const d=c?.setupState?.recruitData;
if(!d?.recruitId||c.setupState.loading)return null;
"""
    + PICK
    + """
return {row:pick(d),title:document.querySelector('.job_title')?.innerText,
unit:document.querySelector('.company_title')?.innerText};
}"""
)


class Record(BaseModel):
    recruitId: str
    companyId: str
    CR_COMPANY_ID: str = ""
    jobTitle: str
    displayName: str
    jobType: str
    jobTypeDsc: str
    requireEduDsc: str = ""
    workCityDsc: str = ""
    address: str = ""
    lastUpdateDt: str = ""
    endDate: str = ""
    pubState: int
    recruitType: str = ""
    jobResp: str = ""
    jobReq: str = ""


class Pagination(BaseModel):
    pageIndex: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class Catalog(BaseModel):
    page: Pagination
    companyId: str
    companyName: str
    rows: list[Record]
    visibleIds: list[str]
    terminal: bool


class Detail(BaseModel):
    row: Record
    title: str
    unit: str


async def read_detail(session: BrowserSession, expected_id: str) -> Detail:
    current = await session.page.evaluate(DETAIL_JS)
    if current and current.get("row", {}).get("recruitId") != expected_id:
        # This SPA only loads details on mount. A hash change between job IDs
        # keeps the previous component alive; a normal reload remounts it.
        session.consume_request()
        await session.page.reload(wait_until="domcontentloaded", timeout=60000)
    await session.page.wait_for_function(
        "key => {const d=(" + DETAIL_JS + ")();return d?.row.recruitId===key;}",
        arg=expected_id,
        timeout=30000,
    )
    return Detail.model_validate(await session.page.evaluate(DETAIL_JS))


def validate_catalog(data: Catalog, page: int, total: int | None) -> None:
    check(data.companyId == COMPANY and data.companyName == COMPANY_NAME, "深投控企业身份改变")
    check(data.page.pageIndex == page, "深投控页码错位")
    check(total is None or data.page.total == total, "深投控分页总数变化")
    expected = min(data.page.pageSize, max(0, data.page.total - (page - 1) * data.page.pageSize))
    check(len(data.rows) == expected, "深投控当前页条数不闭合")
    ids = [r.recruitId for r in data.rows]
    check(ids == data.visibleIds and len(set(ids)) == len(ids), "深投控页面卡片与数据不一致或重复")
    check(
        data.terminal == (page >= max(1, ceil(data.page.total / data.page.pageSize))),
        "深投控末页按钮与总数不一致",
    )
    check(
        all(r.companyId == COMPANY and r.CR_COMPANY_ID for r in data.rows), "深投控目录企业范围改变"
    )


def validate_detail(data: Detail, listing: Record) -> None:
    row = data.row
    check(row.recruitId == listing.recruitId, "深投控详情ID不一致")
    check(row.companyId == listing.CR_COMPANY_ID, "深投控用人单位ID不一致")
    check(row.jobTitle == listing.jobTitle == data.title.strip(), "深投控岗位标题不一致")
    check(row.displayName == listing.displayName == data.unit.strip(), "深投控用人单位名称不一致")
    check(row.recruitType in {"1", "2", "3"}, "深投控招聘类型未知")
    check(row.jobType in {"01", "02", "03", "04"}, "深投控聘用类型未知")
    check(row.pubState in {0, 1, -1, -2, -3}, "深投控发布状态未知")


class SihcCampus(Adapter):
    name = "sihc-iucai-campus"
    host = "jyjpc.iucai.com.cn"
    path = f"/#/companyDetail?companyId={COMPANY}"
    scope_description = "深圳投控官方菁英聚鹏城企业筛选下完整分页目录，详情类型2校招且正式全职"

    def make_job(self, row: Record) -> Job:
        duties, requirements = split_sections(text(row.jobResp))
        explicit = text(row.jobReq)
        if explicit and explicit != "无":
            requirements = "\n".join(dict.fromkeys(s for s in (requirements, explicit) if s))
        return self.job(
            row.recruitId,
            title=row.jobTitle,
            unit=row.displayName,
            work_type="校招",
            source_url=f"https://{self.host}/#/jobDetail?recruitId={row.recruitId}",
            duties=duties,
            requirements=requirements,
            education=row.requireEduDsc,
            location=row.workCityDsc,
            address=row.workCityDsc + row.address if row.address else "",
            deadline=row.endDate,
            visible=row.pubState == 1,
            closed=row.pubState in {-1, -2, -3},
            field_sources={
                "duties": "public-page.recruitData.jobResp",
                "requirements": "public-page.recruitData.jobResp/jobReq",
                "deadline": "public-page.recruitData.endDate",
                "published": "source_missing:页面仅显示更新时间，不作为发布日期",
            },
        )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        # Validate the same public enumeration dictionary loaded by the website.
        observed = await session.observed_path("/json/dict.json")
        dictionary = json.loads(observed["body"])
        for key, expected in {
            "RECRUIT_TYPE": {"1": "社招", "2": "校招", "3": "不限"},
            "JOB_TYPE": {"01": "全职", "02": "兼职", "03": "实习", "04": "见习"},
        }.items():
            check(
                {r["id"]: r["dictName"] for r in dictionary[key]} == expected, "深投控类型字典变化"
            )
        scope = Scope(name="sihc-company-campus", evidence=[session.last_evidence])
        self.result.scopes.append(scope)
        session.consume_request()
        await session.page.get_by_text("招聘职位", exact=True).click(timeout=30000)
        catalog: list[tuple[Record, str]] = []
        seen: set[str] = set()
        for page in range(1, 1001):
            await session.page.wait_for_function(CATALOG_JS, timeout=30000)
            data = Catalog.model_validate(await session.page.evaluate(CATALOG_JS))
            validate_catalog(data, page, scope.expected)
            scope.expected = data.page.total
            evidence = session.snapshot(f"catalog-{page}", await session.page.content())
            write_json(session.output / f"catalog-{page}.json", data.model_dump())
            scope.evidence.append(evidence)
            rows = self.add_page(
                scope, [row.model_dump() for row in data.rows], seen, lambda row: row["recruitId"]
            )
            catalog.extend((Record.model_validate(row), evidence) for row in rows)
            if data.terminal:
                scope.terminal = True
                break
            session.consume_request()
            await session.page.locator(".el-pagination .btn-next").click(timeout=30000)
            await session.page.wait_for_function(
                "page => document.querySelector('.el-pager .is-active')?.textContent.trim()===String(page)",
                arg=page + 1,
                timeout=30000,
            )
        check(scope.terminal, "深投控超过分页上限")
        for listing, evidence in catalog:
            try:
                # The catalog omits campus/social type, so always obtain a detail
                # before deciding whether this is a campus job.
                entity = f"job:{listing.recruitId}"
                resolved = self.before_detail(
                    entity, listing.model_dump(), scope, evidence=evidence
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                url = f"https://{self.host}/#/jobDetail?recruitId={listing.recruitId}"
                await session.open(url)
                detail = await read_detail(session, listing.recruitId)
                validate_detail(detail, listing)
                detail_evidence = session.snapshot("job-detail", await session.page.content())
                write_json(session.output / f"detail-{listing.recruitId}.json", detail.model_dump())
                row = detail.row
                if row.recruitType != "2" or row.jobType != "01":
                    scope.skipped_out_of_scope += 1
                    continue
                job = self.make_job(row)
                job.evidence = [evidence, detail_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(entity, listing.model_dump(), [job])
            except Exception as exc:
                self.error(exc, listing.recruitId)
