"""Bank of Communications public campus catalog and detail API."""

import json
from typing import Any, cast
from urllib.parse import parse_qs

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


def envelope(body: dict[str, Any]) -> str:
    return json.dumps(
        {"REQ_HEAD": {"TRAN_PROCESS": "", "TRAN_ID": ""}, "REQ_BODY": body}, ensure_ascii=False
    )


class BankComm(Adapter):
    name = "bankcomm-campus"
    host = "job.bankcomm.com"
    path = "/index.do#/school/main"
    ready_endpoints = ("/querySocietyRecruitInfo.do",)
    scope_description = "交通银行官网 engageType=1 校园招聘公开全目录，逐条公开详情"

    async def harvest(self) -> None:
        observed = await self.session.observed("/querySocietyRecruitInfo.do")
        form = parse_qs(observed["post_data"])
        check(set(form) == {"REQ_MESSAGE"}, "交通银行目录表单改变")
        message = json.loads(form["REQ_MESSAGE"][0])
        business = message["REQ_BODY"]["params"]["businessPara"]
        check(
            business == {"workPlace": "", "pubName": "", "positionId": "", "engageType": 1},
            "交通银行校招目录含筛选或招聘类型改变",
        )
        page_info = message["REQ_BODY"]["params"]["pagePara"]
        check(int(page_info["pageNum"]) == 1, "交通银行目录不是第一页")
        size = int(page_info["pageSize"])
        check(0 < size <= 100, "交通银行分页大小无效")
        scope = Scope(name="campus-engageType-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        session = cast(BrowserSession, self.session)
        while True:
            body = {
                "params": {
                    "businessPara": business,
                    "pagePara": {"pageNum": page, "pageSize": size},
                },
                "unnessaryLogin": False,
            }
            response = await session.request(observed["url"], form={"REQ_MESSAGE": envelope(body)})
            check(response["RSP_HEAD"]["TRAN_SUCCESS"] == "1", "交通银行目录业务失败")
            results = response["RSP_BODY"]["results"]
            expected = int(results["total"])
            check(expected >= 0, "交通银行目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "交通银行分页期间总数变化")
            rows = self.add_page(
                scope, results["policyList"], seen, lambda row: str(row["positionId"])
            )
            list_evidence = session.last_evidence
            for row in rows:
                key = str(row["positionId"])
                check(str(row["engageType"]) == "1", "交通银行目录混入社会招聘")
                url = f"https://{self.host}/index.do#/school/recruitmentInfo/?positionId={key}"
                listing = self.job(
                    key,
                    title=text(row["pubName"]),
                    source_url=url,
                    apply_url=url,
                    unit=text(row.get("bankName") or row.get("deptName")),
                    batch=text(row.get("projectName")),
                    location=text(row.get("workPlace")),
                    published=text(row.get("createTime")),
                    deadline=text(
                        row.get("piWebEndDate") or row.get("piEndDate") or row.get("endDate")
                    ),
                )
                listing.evidence = [list_evidence]
                if select(listing, "all", self.as_of).reason == "expired":
                    listing.detail_mode = "listing_only"
                    self.result.jobs.append(listing)
                    scope.skipped_expired += 1
                    continue
                resolved = self.before_detail(
                    f"job:{key}", row, scope, listing, evidence=list_evidence
                )
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                detail_body = {"params": {"positionId": key}, "unnessaryLogin": False}
                response = await session.request(
                    f"https://{self.host}/api/GTMS.GTMS-PORTAL.V-1.0/queryPositionDetail.do",
                    form={"REQ_MESSAGE": envelope(detail_body)},
                    detail=True,
                )
                check(response["RSP_HEAD"]["TRAN_SUCCESS"] == "1", "交通银行详情业务失败")
                detail = response["RSP_BODY"]["results"]
                check(detail["pubName"] == row["pubName"], "交通银行详情与目录标题不一致")
                check(bool(detail.get("responsibility")), "交通银行详情职责缺失")
                listing.duties = text(detail["responsibility"])
                listing.requirements = text(detail.get("require"))
                listing.location = text(detail.get("workPlace"))
                listing.unit = text(detail.get("bankName") or detail.get("deptName"))
                listing.evidence = [list_evidence, session.last_evidence]
                listing.field_sources = {
                    "duties": "queryPositionDetail.results.responsibility",
                    "requirements": "queryPositionDetail.results.require",
                    "published": "querySocietyRecruitInfo.results.policyList[].createTime",
                    "deadline": "querySocietyRecruitInfo.results.policyList[].endDate",
                }
                self.result.jobs.append(listing)
                scope.details += 1
                self.remember(f"job:{key}", row, [listing])
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "交通银行分页提前为空")
            page += 1
