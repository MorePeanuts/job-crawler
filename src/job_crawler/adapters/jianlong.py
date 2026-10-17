"""Jianlong's complete company switcher and public COAPI campus records."""

import asyncio
from typing import Any, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import text
from job_crawler.adapters.coapi51 import LIST_JS, Coapi
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


class JianlongCampus(Coapi):
    name = "coapi-jianlong-campus"
    host = "campus.51job.com"
    path = "/jljt2027/about2.html"
    ctmid = "9551405"
    scope_description = (
        "建龙集团2027校招页面全部招聘单位，逐单位COAPI完整目录及详情；不把专业介绍拆成岗位"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        await session.page.wait_for_selector(".tel_top[jobid]", timeout=30000)
        document = BeautifulSoup(await session.page.content(), "html.parser")
        units = [
            (str(n["coid"]), n.get_text(strip=True)) for n in document.select(".list .z li[coid]")
        ]
        check(
            bool(units) and len({item[0] for item in units}) == len(units), "建龙招聘单位为空或重复"
        )
        check(all(identity.isdigit() and name for identity, name in units), "建龙单位标识缺失")
        rendered = {str(n["jobid"]) for n in document.select(".tel_top[jobid]")}
        directory_evidence = session.last_evidence
        seen: set[str] = set()
        for index, (company_id, company_name) in enumerate(units):
            scope = Scope(name=f"company-{company_id}", evidence=[directory_evidence])
            self.result.scopes.append(scope)
            try:
                session.consume_request()
                await asyncio.sleep(session.config.delay)
                response = await session.page.evaluate(
                    LIST_JS,
                    {
                        "ctmid": self.ctmid,
                        "pagesize": 1000,
                        "sort": "coid",
                        "sequence": 1,
                        "coid": company_id,
                    },
                )
                check(str(response.get("status")) == "1", "建龙公司目录业务失败")
                body = response["resultbody"]
                count = int(body["totalnum"])
                rows = body["joblist"]
                check(0 <= count <= 1000 and len(rows) == count, "建龙目录存在缺失或未支持分页")
                check(
                    all(
                        str(row["coid"]) == company_id and str(row["ctmid"]) == self.ctmid
                        for row in rows
                    ),
                    "建龙目录单位错配",
                )
                if index == 0:
                    check(
                        {str(row["jobid"]) for row in rows} == rendered,
                        "建龙默认单位卡片与目录不符",
                    )
                evidence = session.output / f"jianlong-company-{company_id}.json"
                write_json(evidence, response)
                session.last_evidence = str(evidence)
                scope.expected = count
                check(
                    not ({str(row["jobid"]) for row in rows} & seen), "建龙跨公司目录出现重复岗位"
                )
                company_seen: set[str] = set()
                unique_rows = self.add_page(scope, rows, company_seen, lambda r: str(r["jobid"]))
                seen.update(company_seen)
                for row in unique_rows:
                    key = str(row["jobid"])
                    try:
                        check(text(row["coname"]) == company_name, "建龙公司名称与选项不一致")
                        check(row["term"] in {"全职", "实习"}, "建龙工作性质改变")
                        if row["term"] == "实习":
                            scope.skipped_out_of_scope += 1
                            continue
                        listing = self.listing_job(key, row)
                        cached = self.before_detail(
                            key, row, scope, listing, evidence=str(evidence)
                        )
                        if cached is not None:
                            self.result.jobs.extend(cached)
                            continue
                        detail, detail_evidence = await self.detail(key)
                        check(
                            str(detail["coid"]) == company_id
                            and text(detail["coname"]) == company_name
                            and text(detail["jobname"]) == text(row["jobname"]),
                            "建龙详情单位或标题错配",
                        )
                        job = self.complete_job(key, row, detail, detail_evidence, str(evidence))
                        self.result.jobs.append(job)
                        scope.details += 1
                        self.remember(key, row, [job])
                    except Exception as exc:
                        self.error(exc, key)
                scope.terminal = True
            except Exception as exc:
                self.error(exc, f"company:{company_id}")

    def complete_job(
        self,
        key: str,
        listed: dict[str, Any],
        detail: dict[str, Any],
        evidence: str,
        list_evidence: str,
    ) -> Job:
        job = super().complete_job(key, listed, detail, evidence, list_evidence)
        major = text(detail.get("major"))
        if major:
            job.requirements = "\n".join(filter(None, [job.requirements, "专业要求：" + major]))
        job.address = text(detail.get("address"))
        job.field_sources["requirements"] += " + major"
        job.field_sources["address"] = "coapi.getJobDetail.address"
        return job
