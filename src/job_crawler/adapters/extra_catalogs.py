"""Additional observed public recruitment catalogs with explicit source contracts."""

import asyncio
import json
import re
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession


class KingfaCampus(Adapter):
    name = "kingfa-campus"
    host = "career.kingfa.com"
    path = "/portal/list/index/id/459.html"
    endpoint = "/portal/list/getjobuslist.html"
    scope_description = "金发科技官方 Category=2 校园招聘全目录；完整正文与逐岗位广告ID关联"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        params = parse_qs(observed["post_data"], keep_blank_values=True)
        check(
            params.get("category_id") == ["459"] and params.get("jobad_category") == ["2"],
            "金发不是已验证校招目录",
        )
        check(
            set(params) <= {"category_id", "page_size", "jobad_category", "list_tpl", "page_num"},
            "金发目录带局部筛选",
        )
        session = cast(BrowserSession, self.session)
        scope = Scope(name="kingfa-campus-category-2")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            if page > 1:
                session.consume_request()
                await session.page.get_by_text("加载更多", exact=True).click(timeout=15000)
                for _ in range(60):
                    if session.pending:
                        await asyncio.gather(*list(session.pending), return_exceptions=True)
                    matches = [
                        r
                        for r in session.responses
                        if self.endpoint in r["url"]
                        and parse_qs(r.get("post_data") or "").get("page_num") == [str(page)]
                        and r["status"] == 200
                    ]
                    if matches:
                        observed = matches[-1]
                        break
                    await asyncio.sleep(0.5)
                else:
                    raise ValueError("金发加载更多没有返回当前页")
            data = json.loads(observed["body"])
            evidence = session.output / f"kingfa-page-{page:04}.json"
            write_json(evidence, observed)
            session.last_evidence = str(evidence)
            check(
                data.get("error") == 0 and str(data.get("category_id")) == "459",
                "金发列表业务失败或类别不符",
            )
            check(data.get("more_data") in {0, 1}, "金发缺少明确末页状态")
            soup = BeautifulSoup(data["data"], "html.parser")
            links = {}
            for anchor in soup.select('a[href*="/job_details/"]'):
                url = urljoin(f"https://{self.host}", str(anchor["href"]))
                ids = re.search(r"/job_id/(\d+)/cid/459/idtype/2/frist/(\d+)\.html", url)
                check(ids is not None, "金发岗位详情链接结构改变")
                assert ids is not None
                links[ids[2]] = (ids[1], url)
            rows = self.add_page(scope, data["job_list"], seen, lambda r: str(r["Id"]))
            check(len(rows) <= 20 and len(links) == len(rows), "金发HTML与目录岗位数不符")
            for row in rows:
                key = str(row["Id"])
                link = links.get(key)
                check(link is not None and link[0] == str(row["JobId"]), "金发岗位和广告身份不符")
                assert link is not None
                check(
                    row["Category"] == 2 and row["CategoryDescription"] == "校园招聘",
                    "金发包含非校招类型",
                )
                check(row.get("Status") == 1 and not row.get("IsDeleted"), "金发包含关闭岗位")
                check("Duty" in row and "Requirements" in row, "金发目录正文缺失")
                self.result.jobs.append(
                    self.job(
                        key,
                        title=text(row["JobTitle"]),
                        unit=text((row.get("DepartmentName") or {}).get("Description")),
                        source_url=link[1],
                        work_type="校招"
                        if row.get("KindDescription") == "全职"
                        else text(row.get("KindDescription")),
                        location=text(row.get("WorkingPlace")),
                        duties=text(row["Duty"]),
                        requirements=text(row["Requirements"]),
                        published=text(row.get("PublishDate")),
                        deadline=text(row.get("EndDate")),
                        category_raw=text(row.get("JobCategroyDescription")),
                        field_sources={
                            "duties": "job_list.Duty",
                            "requirements": "job_list.Requirements",
                            "published": "PublishDate",
                            "deadline": "EndDate",
                            "location": "WorkingPlace",
                        },
                    )
                )
                scope.details += 1
            if not data["more_data"]:
                scope.terminal = True
                break
            check(bool(rows), "金发more_data与空目录矛盾")
            page += 1


class ZhinkCampus(Adapter):
    name = "zhink-campus"
    host = "www.zhink.cc"
    path = "/index/human_resources/other_recruitment.html"
    endpoint = "/jeecg-boot/door/info/listPosition"
    ready_endpoints = (endpoint,)
    scope_description = "正凯官网 type=1 校园招聘全目录及旗下招聘单位；不含社会招聘"

    async def harvest(self) -> None:
        observed = await self.session.observed(self.endpoint)
        params = parse_qs(urlsplit(observed["url"]).query, keep_blank_values=True)
        check(
            params.get("tenantId") == ["1"] and params.get("type") == ["1"],
            "正凯租户或招聘类别不符",
        )
        for key in ("positionName", "workingPlace", "companyName"):
            check(not params.get(key, [""])[0], f"正凯含局部筛选 {key}")
        scope = Scope(name="zhink-campus-type-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                query(observed["url"], pageNo=page, pageSize=1000)
            )
            check(
                response.get("success") is True and response.get("code") == 200, "正凯目录业务失败"
            )
            data = response["result"]
            count = int(data["total"])
            check(
                int(data["current"]) == page and int(data["size"]) == 1000, "正凯页码或分页大小不符"
            )
            check(int(data["pages"]) == (count + 999) // 1000, "正凯总页数不符")
            if scope.expected is None:
                scope.expected = count
            check(count == scope.expected, "正凯目录总数变化")
            rows = self.add_page(scope, data["records"], seen, lambda r: str(r["id"]))
            for row in rows:
                check(
                    str(row["type"]) == "1"
                    and row.get("isShow") == "Y"
                    and row.get("delFlag") == 0,
                    "正凯目录含隐藏或非校招岗位",
                )
                check(
                    bool(row.get("positionName")) and "jobDesc" in row and "jobRequirement" in row,
                    "正凯职位正文缺失",
                )
                self.result.jobs.append(
                    self.job(
                        str(row["id"]),
                        title=text(row["positionName"]),
                        unit=text(row.get("companyName")),
                        education=text(row.get("education")),
                        location=text(row.get("workingPlace")),
                        duties=text(row["jobDesc"]),
                        requirements=text(row["jobRequirement"]),
                        category_raw=text(row.get("jobCategory")),
                        source_url=f"https://{self.host}{self.path}",
                        field_sources={
                            "duties": "listPosition.jobDesc",
                            "requirements": "listPosition.jobRequirement",
                            "education": "education",
                            "location": "workingPlace",
                            "published": "只有后台createTime/updateTime，源站发布时间未知",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
            if scope.unique >= count:
                scope.terminal = True
                break
            check(bool(rows), "正凯分页提前为空")
            page += 1


TENANTS = (KingfaCampus, ZhinkCampus)
