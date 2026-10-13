"""TCL 2027 campus catalog embedded in its public recruitment portal."""

import json
import math
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Issue, Scope
from job_crawler.transport import CrawlError

LIST_PATH = "/Ajax/campus_search.html"
DETAIL_PATH = "/wecruit/positionInfo/listPositionDetail/"
DETAIL_HOST = "wecruit.hotjob.cn"
DETAIL_SUITE = "SU64893571bef57c16d356b99e"


class DetailRequester(Protocol):
    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]: ...


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page

    async def observed(self, needle: str) -> dict[str, Any]: ...


def parse_list_page(response: dict[str, Any]) -> tuple[int, list[dict[str, str]]]:
    """Read observed campus cards and their public TCL/Hotjob detail links."""
    check(response.get("title") == "success", "TCL 职位列表业务失败")
    total = int(response.get("total_counts", 0))
    soup = BeautifulSoup(str(response.get("content", "")), "html.parser")
    cards = soup.select(".itembox .item.proInfoConList")
    rows: list[dict[str, str]] = []
    for card in cards:
        head = card.select_one(".head[data-postid]")
        name = card.select_one(".head .name")
        tags = card.select(".head .tag span")
        apply = card.select_one("a.tool-btn[href]")
        check(head is not None and name is not None and apply is not None, "TCL 岗位卡片字段缺失")
        assert head is not None and name is not None and apply is not None
        post_id = str(head.get("data-postid", ""))
        recruit_type = str(head.get("data-recruittype", ""))
        href = str(apply.get("href", ""))
        parsed = urlsplit(href)
        query = parse_qs(parsed.query)
        check(bool(post_id) and recruit_type == "1", "TCL 目录混入非校招或缺少岗位 ID")
        check(
            parsed.scheme == "https"
            and parsed.hostname == DETAIL_HOST
            and parsed.path == f"/{DETAIL_SUITE}/pb/posDetail.html"
            and query.get("postId") == [post_id]
            and query.get("postType") == ["campus"],
            "TCL 岗位详情链接和目录 ID 不一致",
        )
        values = [tag.get_text(" ", strip=True) for tag in tags]
        check(len(values) >= 4, "TCL 岗位标签字段缺失")
        rows.append(
            {
                "id": post_id,
                "title": name.get_text(" ", strip=True),
                "unit": values[0],
                "location": values[1],
                "category": values[2],
                "headcount": values[3],
                "apply_url": href,
            }
        )
    check(bool(rows) or total == 0, "TCL 岗位页未返回卡片，但总数非零")
    return total, rows


class TCLCampus(Adapter):
    name = "tcl-campus"
    host = "zhaopin.tcl.com"
    path = "/campus/recruiting.html?keyType=1"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = (
        "TCL 官方 2027 全球校园招聘项目 type=1 全目录及其公开 Hotjob 详情；含招聘子单位"
    )

    async def harvest(self) -> None:
        observed = await self.session.observed(LIST_PATH)
        observed_url = urlsplit(observed["url"])
        check(
            observed_url.hostname == self.host and observed_url.path == LIST_PATH,
            "TCL 职位列表接口地址改变",
        )
        first_page = int(parse_qs(urlsplit(observed["url"]).query).get("page", ["0"])[0])
        check(first_page == 1, "TCL 首次观察不是第一页")
        form = parse_qs(observed.get("post_data", ""), keep_blank_values=True)
        check(
            set(form) == {"keyType", "cate_id", "keys", "job_xm[]"}
            and form.get("keyType") == ["1"]
            and form.get("cate_id") == ["100"]
            and form.get("keys") == [""]
            and len(form.get("job_xm[]", [])) == 1,
            "TCL 职位请求包含未知筛选或非校招项目",
        )
        payload = json.loads(observed["body"])
        expected, first_rows = parse_list_page(payload)
        scope = Scope(name="tcl-2027-campus-all", expected=expected)
        self.result.scopes.append(scope)
        pages = math.ceil(expected / len(first_rows)) if first_rows else 1
        all_rows: list[dict[str, str]] = []
        seen: set[str] = set()
        requester = cast(DetailRequester, self.session)
        page_obj = cast(PageSession, self.session).page
        for page_number in range(1, pages + 1):
            if page_number == 1:
                current_expected, rows = expected, first_rows
                evidence = self.session.last_evidence
            else:
                await page_obj.evaluate(
                    "async () => new Promise((resolve, reject) => {"
                    "const old = document.querySelector('.proInfoConList .head[data-postid]')?.dataset.postid;"
                    "const root = document.querySelector('#job_content');"
                    "if (!root || typeof job_search !== 'function') return reject(new Error('TCL 分页函数不可用'));"
                    "const timer = setTimeout(() => { observer.disconnect(); reject(new Error('TCL 分页超时')); }, 30000);"
                    "const observer = new MutationObserver(() => {"
                    "const current = root.querySelector('.proInfoConList .head[data-postid]')?.dataset.postid;"
                    "if (current && current !== old) { clearTimeout(timer); observer.disconnect(); resolve(current); }"
                    "}); observer.observe(root, {childList: true, subtree: true});"
                    f"job_search({page_number});"
                    "})"
                )
                result = await self.session.observed(LIST_PATH)
                check(
                    int(parse_qs(urlsplit(result["url"]).query).get("page", ["0"])[0])
                    == page_number,
                    "TCL 页面发出的分页请求页码错误",
                )
                evidence = self.session.last_evidence
                current_expected, rows = parse_list_page(json.loads(result["body"]))
            check(current_expected == expected, "TCL 分页期间目录总数变化")
            scope.evidence.append(evidence)
            for row in rows:
                scope.listed += 1
                key = row["id"]
                check(key not in seen, "TCL 职位目录出现重复页或岗位 ID")
                seen.add(key)
                scope.unique += 1
                row["list_evidence"] = evidence
                all_rows.append(row)
        check(scope.unique == expected, "TCL 校招唯一岗位数与总数不符")

        detail_api = ""
        observed_detail: dict[str, Any] | None = None
        detail_job_id = ""
        for row in all_rows:
            key = row["id"]
            try:
                if not detail_api:
                    await self.session.open(row["apply_url"], ready_endpoints=(DETAIL_PATH,))
                    detail = await self.session.observed(DETAIL_PATH)
                    check(DETAIL_SUITE in detail["url"], "TCL 岗位详情属于其他招聘租户")
                    detail_api = detail["url"]
                    observed_detail = json.loads(detail["body"])
                    detail_job_id = key
                    detail_evidence = self.session.last_evidence
                else:
                    observed_detail = None
                    detail_evidence = ""
                detail = (
                    observed_detail
                    if observed_detail is not None and detail_job_id == key
                    else await requester.request(
                        detail_api,
                        form={"postId": key, "recruitType": "1"},
                        detail=True,
                    )
                )
                data = detail.get("data")
                check(isinstance(data, dict), "TCL 职位详情结构无效")
                assert isinstance(data, dict)
                check(str(data.get("postId")) == key, "TCL 详情与目录岗位 ID 不一致")
                check(str(data.get("recruitType")) == "1", "TCL 岗位详情不是校招")
                duties = text(data.get("workContent"))
                requirements = text(data.get("serviceCondition"))
                if not duties or not requirements:
                    self.result.warnings.append(
                        Issue(
                            code="field_missing",
                            message="TCL 职位详情未提供完整职责或任职要求",
                            source_id=self.source.source_id,
                            job_key=key,
                            url=row["apply_url"],
                        )
                    )
                job = self.job(
                    key,
                    title=text(data.get("postName") or row["title"]),
                    unit=text(data.get("orgName") or row["unit"]),
                    location=text(data.get("workPlaceStr") or row["location"]),
                    education=text(data.get("education") or data.get("educationStr")),
                    category_raw=text(data.get("postTypeName") or row["category"]),
                    duties=duties,
                    requirements=requirements,
                    published=text(data.get("publishFirstDate") or data.get("publishDate")),
                    deadline=text(data.get("endDate")),
                    source_url=row["apply_url"],
                    apply_url=row["apply_url"],
                    field_sources={
                        "title": "TCL Ajax campus_search .head .name / Hotjob listPositionDetail.postName",
                        "unit": "Hotjob listPositionDetail.orgName",
                        "duties": "Hotjob listPositionDetail.workContent",
                        "requirements": "Hotjob listPositionDetail.serviceCondition",
                        "education": "Hotjob listPositionDetail.education",
                        "published": "Hotjob listPositionDetail.publishFirstDate"
                        if data.get("publishFirstDate")
                        else "Hotjob listPositionDetail.publishDate",
                        "deadline": "Hotjob listPositionDetail.endDate",
                        "location": "Hotjob listPositionDetail.workPlaceStr / TCL campus card",
                    },
                )
                job.visible = bool(data.get("canDelivery", True))
                job.evidence = [row["list_evidence"], detail_evidence or self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, key)
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    raise
        if not detail_api:
            check(expected == 0, "TCL 岗位目录未能读取任何详情")
        scope.terminal = True
