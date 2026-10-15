"""Industrial Bank's public graduate catalogue, including every bank branch."""

import asyncio
import json
from typing import Any, cast

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession, CrawlError


class Cib2027(Adapter):
    name = "cib-2027-campus"
    host = "job.cib.com.cn"
    path = "/portal/#/recruit/814456498578608128?recruitType=CR"
    scope_description = "兴业银行官网 2027 校招总行与全部分行；独立子公司明确排除"
    nonbank_units = {
        "兴业国际信托有限公司",
        "兴业金融租赁有限责任公司",
        "兴业消费金融股份公司",
        "兴银理财有限责任公司",
    }

    async def _response_for_page(
        self, session: BrowserSession, page: int, root_code: str | None
    ) -> dict[str, Any]:
        for _ in range(int(session.config.timeout * 5)):
            if session.pending:
                await asyncio.gather(*list(session.pending), return_exceptions=True)
            for candidate in reversed(session.responses):
                if "/ersApi/recruitposition/portalPage?" not in candidate["url"]:
                    continue
                try:
                    form = json.loads(candidate.get("post_data") or "")
                except ValueError:
                    continue
                if (
                    form.get("recruitType") == "CR"
                    and form.get("visibilityFlag") == "Y"
                    and form.get("positionStatus") == "P"
                    and form.get("firstBusinessUnit") == root_code
                    and form.get("pagination") == {"pageIndex": page, "pageSize": 40}
                ):
                    data = json.loads(candidate["body"])
                    check(data.get("code") == "0000", "兴业校招列表业务失败")
                    evidence = session.output / "cib-pages" / f"{root_code or 'all'}-{page:04}.json"
                    write_json(evidence, candidate)
                    session.last_evidence = str(evidence)
                    return cast(dict[str, Any], data)
            await asyncio.sleep(0.2)
        raise CrawlError("api_not_observed", f"兴业银行第 {page} 页校招接口未返回")

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "兴业银行校园招聘页面不存在")
        assert session.page is not None
        observed = await session.observed_path("/ersApi/recruitposition/queryOrgPositionNum")
        check(
            json.loads(observed.get("post_data") or "") == {"recruitType": "CR"},
            "兴业机构树不是校招范围",
        )
        organizations = json.loads(observed["body"])
        check(organizations.get("code") == "0000", "兴业机构树业务失败")
        units = {
            str(row["businessUnit"]): text(row["businessUnitDesc"]) for row in organizations["data"]
        }
        counts = {
            str(row["businessUnit"]): int(row["positionCount"]) for row in organizations["data"]
        }
        check(
            len(units) == len(organizations["data"]) and bool(units), "兴业机构编码重复或目录为空"
        )
        check(self.nonbank_units <= set(units.values()), "兴业独立子公司机构集合变化")
        unit_evidence = session.last_evidence
        session.consume_request()
        await session.page.locator(".ant-pagination-options-size-changer").click()
        await session.page.get_by_text("40 条/页", exact=True).click()
        all_response = await self._response_for_page(session, 1, None)
        total = int(all_response["data"]["total"])
        check(0 < total <= 4000 and sum(counts.values()) == total, "兴业机构数与无筛选目录不符")
        all_evidence = session.last_evidence
        global_seen: set[str] = set()
        for root_code, root_unit in units.items():
            expected = counts[root_code]
            if expected == 0:
                continue
            check(expected > 0, "兴业机构岗位数量异常")
            session.consume_request()
            await session.page.get_by_text(f"{root_unit}({expected})", exact=True).click()
            scope = Scope(name=f"unit:{root_code}", expected=expected)
            scope.evidence.extend([unit_evidence, all_evidence])
            self.result.scopes.append(scope)
            seen: set[str] = set()
            page = 1
            while True:
                response = await self._response_for_page(session, page, root_code)
                data = response["data"]
                check(int(data["total"]) == expected, "兴业机构翻页期间岗位数变化")
                rows = data["list"]
                check(
                    isinstance(rows, list) and len(rows) == min(40, expected - (page - 1) * 40),
                    "兴业机构页面容量与总数不符",
                )
                fresh = self.add_page(scope, rows, seen, lambda row: str(row["positionId"]))
                list_evidence = session.last_evidence
                for row in fresh:
                    key = str(row["positionId"])
                    check(key not in global_seen, "兴业岗位跨机构重复")
                    global_seen.add(key)
                    check(
                        row.get("recruitType") == "CR"
                        and row.get("visibilityFlag") == "Y"
                        and row.get("positionStatus") == "P",
                        "兴业校招列表混入其他招聘类型或未发布岗位",
                    )
                    check(
                        str(row.get("firstBusinessUnit")) == root_code
                        and text(row.get("firstBusinessUnitDesc")) == root_unit,
                        "兴业岗位与机构筛选不匹配",
                    )
                    unit = text(row.get("businessUnitDesc"))
                    check(bool(unit), "兴业岗位机构名称缺失")
                    if root_unit in self.nonbank_units:
                        scope.skipped_out_of_scope += 1
                        continue
                    check(bool(text(row.get("positionName"))), "兴业岗位名称缺失")
                    detail_url = f"https://{self.host}/portal/#/positionDetails/{key}"
                    job = self.job(
                        key,
                        title=text(row["positionName"]),
                        source_url=detail_url,
                        apply_url=detail_url,
                        unit=unit,
                        location=text(row.get("positionAddr")),
                        category_raw=text(row.get("positionType")),
                        duties=text(row.get("jobDuty")),
                        requirements=text(row.get("positionRequirment")),
                        published=text(row.get("publishTime")),
                        deadline=text(row.get("expiryDate")),
                        field_sources={
                            "unit": "portalPage.businessUnitDesc；firstBusinessUnit 与机构树核对",
                            "duties": "portalPage.data.list[].jobDuty；官网详情同步展示",
                            "requirements": "portalPage.data.list[].positionRequirment；官网详情同步展示",
                            "education": "source_code_only:educationRequirment",
                            "published": "portalPage.data.list[].publishTime",
                            "deadline": "portalPage.data.list[].expiryDate",
                        },
                    )
                    job.evidence = [unit_evidence, list_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                if scope.unique == expected:
                    scope.terminal = True
                    break
                page += 1
                check(page <= (expected + 39) // 40, "兴业机构目录超过声明页数")
                session.consume_request()
                await session.page.locator(".ant-pagination-next").click()
        check(len(global_seen) == total, "兴业分机构合计与总目录不符")
