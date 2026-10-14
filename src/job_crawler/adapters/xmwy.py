"""Xiamen Tungsten's two legal-company campus units on its 51job microsite."""

import asyncio
import json
from datetime import date
from typing import Any, Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope

ROOT = "https://campus.51job.com/cxtc2027/job.html"
COMPANY = "厦门钨业股份有限公司"
TENANT = "8893084"
COMPANY_ID = "9882581"
UNITS = {"01": "总部", "05": "海沧分公司"}
OTHER_CODES = {"1601", "1701", "1605", "1705"}


class SDKPage(Protocol):
    async def content(self) -> str: ...

    async def evaluate(self, script: str, arg: object = None) -> Any: ...


class XiamenSession(Protocol):
    page: SDKPage
    last_evidence: str

    def snapshot(self, label: str, html: str) -> str: ...


def _date(value: object) -> str:
    check(isinstance(value, str) and len(value) >= 10, "厦钨公开发布日期缺失")
    assert isinstance(value, str)
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ValueError("厦钨公开日期格式变化") from exc


def _body(html: object) -> tuple[str, str]:
    check(isinstance(html, str) and bool(html.strip()), "厦钨岗位正文缺失")
    assert isinstance(html, str)
    body = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    return split_sections(body)


class XiamenTungsten2027(Adapter):
    name = "xmwy-2027"
    host = "campus.51job.com"
    path = "/cxtc2027/job.html"
    scope_description = "厦钨2027校园招聘；仅股份总部和海沧分公司准确岗位编码"

    async def harvest(self) -> None:
        session = cast(XiamenSession, self.session)
        html = await session.page.content()
        doc = BeautifulSoup(html, "html.parser")
        kinds = [x.get_text(strip=True) for x in doc.select(".kind-list .item")]
        tabs = [
            (x.get_text(strip=True), x.get("rel")) for x in doc.select(".company-list .clist .iem")
        ]
        check(
            kinds == ["厦钨股份", "钨钼产业", "新能源产业", "稀土产业", "电机产业", "矿业产业"]
            and tabs == [("总部", "01"), ("海沧分公司", "05")],
            "厦钨股份与子公司目录边界变化",
        )
        entry_evidence = session.snapshot("xmwy-legal-units", html)
        seen: set[str] = set()
        for code, unit in UNITS.items():
            scope = Scope(name=f"unit-{code}")
            scope.evidence.append(entry_evidence)
            self.result.scopes.append(scope)
            listing = await asyncio.wait_for(
                session.page.evaluate(
                    "code => new Promise(resolve => coapi.getJobList({ctmid:'8893084',poscode:code}, resolve))",
                    code,
                ),
                timeout=35,
            )
            check(
                isinstance(listing, dict) and listing.get("status") == "1", "厦钨公开岗位目录失败"
            )
            assert isinstance(listing, dict)
            result = listing.get("resultbody")
            check(isinstance(result, dict), "厦钨公开目录结构变化")
            assert isinstance(result, dict)
            rows = result.get("joblist")
            total = result.get("totalnum")
            check(
                isinstance(rows, list)
                and isinstance(total, str)
                and total.isdigit()
                and len(rows) == int(total),
                "厦钨岗位目录总数与列表不闭合",
            )
            assert isinstance(rows, list) and isinstance(total, str)
            scope.expected = int(total)
            list_evidence = session.snapshot(
                f"xmwy-list-{code}", json.dumps(listing, ensure_ascii=False)
            )
            scope.evidence.append(list_evidence)
            for row in rows:
                scope.listed += 1
                check(isinstance(row, dict), "厦钨目录岗位行结构变化")
                assert isinstance(row, dict)
                job_id = row.get("jobid")
                check(
                    isinstance(job_id, str) and job_id.isdigit() and job_id not in seen,
                    "厦钨岗位 ID 重复或缺失",
                )
                seen.add(job_id)
                scope.unique += 1
                check(
                    row.get("ctmid") == TENANT
                    and row.get("coid") == COMPANY_ID
                    and row.get("coname") == COMPANY,
                    "厦钨目录混入其他租户或法人",
                )
                job_code = row.get("poscode")
                if job_code != code:
                    check(job_code in OTHER_CODES, "厦钨目录出现未知单位编码")
                    scope.skipped_out_of_scope += 1
                    continue
                check(
                    row.get("term") == "全职" and row.get("workyearname") == "在校生/应届生",
                    "厦钨本级岗位非正式校招",
                )
                try:
                    detail = await asyncio.wait_for(
                        session.page.evaluate(
                            "id => new Promise(resolve => coapi.getJobDetail(id, resolve))",
                            job_id,
                        ),
                        timeout=35,
                    )
                    check(
                        isinstance(detail, dict) and detail.get("status") == "1",
                        "厦钨岗位详情失败",
                    )
                    assert isinstance(detail, dict)
                    item = detail.get("resultbody")
                    check(
                        isinstance(item, dict)
                        and item.get("jobid") == job_id
                        and item.get("jobname") == row.get("jobname")
                        and item.get("ctmid") == TENANT
                        and item.get("coid") == COMPANY_ID
                        and item.get("coname") == COMPANY
                        and item.get("poscode") == code
                        and item.get("term") == "全职"
                        and item.get("workyearname") == "在校生/应届生"
                        and _date(item.get("issuedate")) == _date(row.get("issuedate")),
                        "厦钨岗位详情身份、单位或发布日期不符",
                    )
                    assert isinstance(item, dict)
                    detail_evidence = session.snapshot(
                        f"xmwy-detail-{job_id}", json.dumps(detail, ensure_ascii=False)
                    )
                    duties, requirements = _body(item.get("jobinfo"))
                    job = self.job(
                        job_id,
                        title=text(item.get("jobname")),
                        unit=unit,
                        batch="2027届全球校园招聘",
                        category_raw=text(item.get("funtype")),
                        location=text(item.get("workareaname")),
                        address=text(item.get("address")),
                        education=text(item.get("degreefrom")),
                        duties=duties,
                        requirements=requirements,
                        published=_date(item.get("issuedate")),
                        source_url=ROOT + "?company=" + code,
                        apply_url=f"https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid={TENANT}",
                        field_sources={
                            "unit": "job.js clist rel + getJobDetail.poscode",
                            "duties": "coapi.getJobDetail.jobinfo 岗位职责",
                            "requirements": "coapi.getJobDetail.jobinfo 任职要求",
                            "education": "coapi.getJobDetail.degreefrom",
                            "location": "coapi.getJobDetail.workareaname",
                            "address": "coapi.getJobDetail.address",
                            "published": "coapi.getJobDetail.issuedate",
                            "apply_url": "getJobList.jobid + ctmid；未访问投递页",
                        },
                    )
                    job.evidence = [entry_evidence, list_evidence, detail_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, job_id)
            scope.terminal = True
