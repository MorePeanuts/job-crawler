"""CMB's public graduate catalog; social jobs and internships are excluded."""

import json
from typing import Any, cast
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

TYPE = "96574F8D-C7ED-4772-AE7C-BAC896D190C1"
ROOT = "https://career.cmbchina.com"
API = ROOT + "/api/campusRecruitmentWebsite/job/"
LIST = API + "getList"
INFO = API + "recruiting-info/list?recruitmentTypeId=" + TYPE
FIELDS = (
    "publishGID",
    "jobDisplay",
    "branchCodeName",
    "locationName",
    "expiredOn",
    "longTermRecruitment",
)


def body(response: dict[str, Any]) -> dict[str, Any]:
    check(
        response.get("returnCode") == "SUC0000" and isinstance(response.get("body"), dict),
        "招商银行业务响应失败或结构变化",
    )
    return response["body"]


def request_payload(observed: dict[str, Any]) -> dict[str, Any]:
    check(observed["url"] == LIST, "招商银行应届目录接口变化")
    payload = json.loads(observed["post_data"])
    check(
        payload
        == {
            "orgIdList": [],
            "keywords": "",
            "locationIdList": [],
            "pageIndex": 1,
            "pageSize": 10,
            "recruitmentTypeId": TYPE,
            "jobTypeIdList": [],
        },
        "招商银行目录存在局部筛选或应届项目变化",
    )
    return payload


def listing_fields(row: dict[str, Any]) -> dict[str, str]:
    check(all(key in row for key in FIELDS), "招商银行岗位列表字段缺失")
    check(
        all(isinstance(row[k], str) and row[k] for k in FIELDS[:4])
        and isinstance(row["longTermRecruitment"], bool)
        and (row["expiredOn"] is None or isinstance(row["expiredOn"], str)),
        "招商银行岗位身份、地点或截止字段异常",
    )
    return {
        "title": row["jobDisplay"],
        "unit": row["branchCodeName"],
        "location": row["locationName"],
        "deadline": "" if row["longTermRecruitment"] else (row["expiredOn"] or ""),
    }


def detail_fields(row: dict[str, Any], detail: dict[str, Any]) -> dict[str, str]:
    check(detail.get("recruitmentTypeID") == TYPE, "招商银行详情并非目标应届项目")
    check(
        all(detail.get(k) == row[k] for k in FIELDS[1:])
        and detail.get("publishGID", row["publishGID"]) == row["publishGID"],
        "招商银行列表详情身份、机构、地点或截止不一致",
    )
    values = {}
    for target, key in [("duties", "jobResponsibility"), ("requirements", "jobRequirement")]:
        check(key in detail and isinstance(detail[key], (str, type(None))), "招商银行正文结构变化")
        document = BeautifulSoup(detail[key] or "", "html.parser")
        check(not document.select("img,a[href],iframe,object,embed"), "招商银行正文含未处理附件")
        values[target] = text(detail[key])
    check(bool(values["duties"] or values["requirements"]), "招商银行详情缺少有效正文")
    return values


class CmbCampus(Adapter):
    name = "cmb-campus"
    host = "career.cmbchina.com"
    path = "/positionlist/" + TYPE
    ready_endpoints = (LIST, INFO)
    scope_description = "招商银行官网梦想靠岸应届生完整机构及城市目录；不含实习、竞赛和社招"

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST)
        payload = request_payload(observed)
        response = json.loads(observed["body"])
        scope = Scope(name="cmb-graduate-all-organizations")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            data = body(response)
            expected = data.get("total")
            rows = data.get("data")
            check(
                type(expected) is int
                and expected >= 0
                and isinstance(rows, list)
                and all(isinstance(row, dict) for row in rows),
                "招商银行目录总数或列表结构异常",
            )
            assert isinstance(expected, int) and isinstance(rows, list)
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "招商银行翻页期间总数变化")
            check(len(rows) == min(10, expected - len(seen)), "招商银行分页行数与总数不符")
            list_evidence = self.session.last_evidence
            if expected == 0:
                info = await self.session.observed(INFO)
                check(info["url"] == INFO, "招商银行零目录机构范围异常")
                check(
                    body(json.loads(info["body"]))
                    == {"recruitingOrgList": [], "recruitingCityList": []},
                    "招商银行零目录与可招聘机构或城市冲突",
                )
                browser = cast(BrowserSession, self.session)
                html = await browser.page.content()
                check("未找到相关职位" in text(html), "招商银行零目录缺少页面证据")
                scope.evidence.extend([list_evidence, self.session.last_evidence])
            for row in self.add_page(scope, rows, seen, lambda item: item.get("publishGID", "")):
                key = row["publishGID"]
                try:
                    fields = listing_fields(row)
                    fingerprint = {k: row[k] for k in FIELDS}
                    url = ROOT + "/positionDetail/school?" + urlencode({"publishId": key})
                    listing = self.job(key, **fields, source_url=url, work_type="校招")
                    listing.evidence = [list_evidence]
                    listing.field_sources = {
                        "published": "source_missing:公开岗位未披露发布日期",
                        "deadline": "expiredOn；longTermRecruitment=true时无固定截止",
                        "location": "locationName",
                        "unit": "branchCodeName",
                        "duties": "jobResponsibility",
                        "requirements": "jobRequirement",
                    }
                    reused = self.before_detail(
                        "job:" + key, fingerprint, scope, listing, evidence=list_evidence
                    )
                    if reused is not None:
                        self.result.jobs.extend(reused)
                        continue
                    detail = await self.session.request(
                        API + "getDetail?" + urlencode({"publishId": key}), detail=True
                    )
                    listing.evidence.append(self.session.last_evidence)
                    if (
                        detail.get("returnCode") == "EZPREC0001"
                        and detail.get("errorMsg") == "该职位已过期, 请刷新后重试"
                        and detail.get("body") is None
                    ):
                        listing.visible = False
                        listing.detail_mode = "listing_only"
                        scope.skipped_closed += 1
                    else:
                        values = detail_fields(row, body(detail))
                        listing.duties = values["duties"]
                        listing.requirements = values["requirements"]
                        scope.details += 1
                    self.result.jobs.append(listing)
                    self.remember("job:" + key, fingerprint, [listing])
                except Exception as exc:
                    self.error(exc, key)
            if len(seen) == expected:
                scope.terminal = True
                break
            page += 1
            response = await self.session.request(LIST, payload={**payload, "pageIndex": page})
