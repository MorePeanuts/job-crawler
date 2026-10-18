"""Huafa Industrial's classic campus catalogue and current group channel."""

import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import text
from job_crawler.adapters.classic_hotjob import ClassicHotjobCampus
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession, CrawlError

COMPANY = "珠海华发实业股份有限公司"
CAMPAIGN = "https://campus.51job.com/huafa/"
SUITE = "SU67b2e3bb1eb80555b7a457f7"
GROUP = f"https://wecruit.hotjob.cn/{SUITE}/pb/school.html"
GROUP_LIST = f"/wecruit/positionInfo/listPosition/{SUITE}"
GROUP_TERMS = f"/wecruit/positionInfo/listSearchTerm/{SUITE}"


class HuafaListedCampus(ClassicHotjobCampus):
    name = "huafa-listed-campus"
    host = "sc.hotjob.cn"
    path = "/wt/huafa/web/index/campus"
    endpoint = "/wt/huafa/web/json/position/list"
    ready_endpoints = (endpoint,)
    catalog_scope = "huafa-listed-classic-campus"
    scope_description = "华发股份独立校园目录全文及集团现行零目录；集团非零单位归属需另核验"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(
            row.get("orgName") == COMPANY and row.get("deptOrgName") == COMPANY,
            "华发校园出现未验证的招聘单位",
        )
        check(row.get("workType") in {"", "全职", "实习"}, "华发工作类型变化")
        for field in ["publishDate", "endDate"]:
            datetime.strptime(str(row.get(field)), "%Y-%m-%d")
        check(
            datetime.fromisoformat(str(row.get("publishDateTime"))).date().isoformat()
            == row["publishDate"],
            "华发发布时间与列表日期不一致",
        )
        check(row.get("isLongTermRelease") == 0, "华发长期发布截止语义需核对")
        check(
            bool(text(row.get("workContent"))) and bool(text(row.get("serviceCondition"))),
            "华发内联职责或资格缺失",
        )
        return True

    def _job(self, row: dict[str, Any], evidence: str) -> Job:
        identity = str(row["postId"])
        check(identity.isdigit() and row.get("importPost") == 0, "华发岗位身份或导入来源变化")
        job = self.job(
            identity,
            title=text(row["postName"]),
            unit=text(row["orgName"]),
            location=text(row["workPlace"]),
            education=text(row["education"]),
            category_raw=text(row["postType"]),
            duties=text(row["workContent"]),
            requirements=text(row["serviceCondition"]),
            published=text(row["publishDate"]),
            deadline=text(row["endDate"]),
            work_type="实习" if row["workType"] == "实习" or "实习" in row["postName"] else "校招",
            source_url=f"https://{self.host}/wt/huafa/web/index/webPositionN310!getOnePosition?"
            + urlencode(
                {
                    "postId": identity,
                    "recruitType": 1,
                    "brandCode": 1,
                    "importPost": 0,
                    "columnId": 1,
                }
            ),
            field_sources={
                "duties": "postList.workContent，公开详情交叉核对",
                "requirements": "postList.serviceCondition",
                "published": "postList.publishDate与页面发布时间一致；publishDateTime同日校验",
                "deadline": "postList.endDate，非长期发布isLongTermRelease0",
                "unit": "orgName与deptOrgName均为华发股份名录主体",
                "address": "source_missing:未提供工作详细地址",
                "work_type": "recruitType1校园目录；实习标题排除",
            },
        )
        job.evidence = [evidence]
        return job

    async def harvest(self) -> None:
        try:
            await super().harvest()
        except Exception as exc:
            self.error(exc, "classic-campus")
        browser = cast(BrowserSession, self.session)
        scope = Scope(name="huafa-current-group-campus")
        self.result.scopes.append(scope)
        try:
            await browser.open(CAMPAIGN)
            html = await browser.page.content()
            doc = BeautifulSoup(html, "html.parser")
            check(COMPANY in text(doc) and "600325" in text(doc), "华发集团活动页上市主体缺失")
            entries = {
                str(a.get("href"))
                for a in doc.select("a[href]")
                if "hotjob.cn" in str(a.get("href"))
            }
            check(entries == {GROUP}, "华发集团校园招聘入口变化")
            scope.evidence.append(browser.snapshot("huafa-group-campaign", html))
            await browser.open(GROUP, ready_endpoints=(GROUP_LIST, GROUP_TERMS))
            html = await browser.page.content()
            doc = BeautifulSoup(html, "html.parser")
            check("华发集团校园招聘" in text(doc.select_one("title")), "华发集团目录主体变化")
            scope.evidence.append(browser.snapshot("huafa-group-campus", html))
            terms = await browser.observed(GROUP_TERMS)
            check(
                urlsplit(terms["url"]).hostname == "wecruit.hotjob.cn", "华发集团条件接口域名变化"
            )
            term_data = json.loads(terms["body"])
            check(term_data.get("state") == "200", "华发集团条件业务失败")
            observed = await browser.observed(GROUP_LIST)
            check(
                urlsplit(observed["url"]).hostname == "wecruit.hotjob.cn",
                "华发集团列表接口域名变化",
            )
            form = parse_qs(observed.get("post_data") or "", keep_blank_values=True)
            expected = {
                "isFrompb": ["true"],
                "recruitType": ["1"],
                "pageSize": ["15"],
                "currentPage": ["1"],
            }
            check(form == expected, "华发集团目录带有局部筛选")
            response = await browser.request(
                observed["url"], form={k: v[0] for k, v in form.items()}
            )
            scope.evidence.append(browser.last_evidence)
            check(response.get("state") == "200", "华发集团列表业务失败")
            data = response["data"]
            page = data["pageForm"]
            if page.get("dataCount") or page.get("pageData"):
                raise CrawlError(
                    "unsupported_scope", "华发集团出现非零岗位，须核验上市主体单位树及跨渠道重复"
                )
            check(
                term_data.get("data") == {}
                and page
                == {"totalPage": 0, "pageSize": 0, "pageData": [], "currentPage": 0, "dataCount": 0}
                and data.get("positonNum") == 0,
                "华发集团不是已验证明确零目录",
            )
            check(
                "在招职位 0 个" in " ".join(doc.stripped_strings)
                and "抱歉，暂时没有您要找的职位~" in text(doc),
                "华发集团零计数与页面不一致",
            )
            scope.expected = 0
            scope.terminal = True
        except Exception as exc:
            self.error(exc, "current-group-campus")
