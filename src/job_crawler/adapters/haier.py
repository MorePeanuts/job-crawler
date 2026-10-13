"""Haier's official graduate projects and linked HTML descriptions."""

from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.hotjob import FormRequester
from job_crawler.adapters.platforms import check
from job_crawler.adapters.smic import HtmlSession
from job_crawler.models import Scope


def parse_detail(html: str, expected_title: str) -> tuple[str, str, bool]:
    detail = BeautifulSoup(html, "html.parser")
    title = detail.select_one(".title_div .title")
    check(title is not None and title.get_text(strip=True) == expected_title, "海尔详情标题不一致")
    bodies = {}
    for heading in detail.select(".inner_details_box .demand_title"):
        label = heading.get_text(strip=True)
        if label not in {"岗位描述", "岗位要求"}:
            continue
        value = heading.find_next_sibling("div", class_="demand_box")
        check(value is not None, "海尔详情段落缺失")
        assert value
        bodies[label] = value.get_text("\n", strip=True)
    check("岗位描述" in bodies and "岗位要求" in bodies, "海尔职责或要求标题变化")
    company_blocks = detail.select("#department_box .department_text_item.primary_content")
    check(bool(company_blocks), "海尔岗位缺少招聘产业主体介绍")
    return (
        bodies["岗位描述"],
        bodies["岗位要求"],
        any("海尔智家股份有限公司" in b.get_text() for b in company_blocks),
    )


class HaierCampus(Adapter):
    name = "haier-campus"
    host = "maker.haier.net"
    path = "/client/campus/activityindex.html"
    endpoint = "/client/campus/getactivityresearchlist.html"
    ready_endpoints = (endpoint,)
    scope_description = "海尔集团全部应届项目中，详情招聘产业主体介绍明确为海尔智家的岗位；排除其他法人，逐条关联公开详情"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        requester = cast(FormRequester, self.session)
        soup = BeautifulSoup(await session.page.content(), "html.parser")
        projects = {
            str(e["value"]): str(e["title"]) for e in soup.select("input[type=radio][name=aid]")
        }
        check(bool(projects), "海尔缺少应届生项目枚举")
        observed = await self.session.observed(self.endpoint)
        params = parse_qs(observed["post_data"], keep_blank_values=True)
        check(
            set(params) == {"from", "page", "pagesize", "place", "keyword", "aid"}
            and params["from"] == ["jituan"],
            "海尔目录参数改变",
        )
        check(not params["place"][0] and not params["keyword"][0], "海尔带局部筛选")
        for project, name in projects.items():
            scope = Scope(name=f"haier-{project}-{name}")
            self.result.scopes.append(scope)
            seen: set[str] = set()
            page = 1
            while True:
                response = await requester.request(
                    observed["url"],
                    form={k: v[0] for k, v in params.items()}
                    | {"aid": project, "page": str(page), "pagesize": "10"},
                )
                check(response.get("status") == 1, "海尔列表业务失败")
                data = response["data"]
                activity = data["activity"]
                check(
                    activity["name"] == name
                    and activity["status"] == "1"
                    and activity["is_del"] == "0",
                    "海尔项目名称或状态不符",
                )
                count = int(data["count"])
                if scope.expected is None:
                    scope.expected = count
                check(count == scope.expected, "海尔项目总数变化")
                rows = self.add_page(scope, data["list"], seen, lambda r: str(r["id"]))
                check(len(rows) == min(10, max(0, count - (page - 1) * 10)), "海尔目录分页不完整")
                for row in rows:
                    key = f"{project}:{row['id']}"
                    url = urljoin(f"https://{self.host}", row["click_url"])
                    check(
                        urlsplit(url).hostname == self.host
                        and f"/id/{project}/" in url
                        and f"/rid/{row['id']}.html" in url,
                        "海尔详情链接关联错误",
                    )
                    listing = self.job(
                        key,
                        title=text(row["name"]),
                        location=text(row["addr"]),
                        category_raw=text(row["fun_name"]),
                        unit=text(row["department"]),
                        source_url=url,
                        batch=name,
                    )
                    resolved = self.before_detail("job:" + key, row, scope, listing)
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    try:
                        html = await session.request_html(url, detail=True)
                        duties, requirements, matches_company = parse_detail(html, listing.title)
                        if not matches_company:
                            listing.work_type = "非海尔智家主体"
                        listing.duties = duties
                        listing.requirements = requirements
                        listing.evidence.append(self.session.last_evidence)
                        listing.field_sources = {
                            "duties": "岗位描述",
                            "requirements": "岗位要求",
                            "location": "目录addr",
                            "published": "source_missing",
                            "deadline": "source_missing",
                        }
                        self.result.jobs.append(listing)
                        scope.details += 1
                        self.remember("job:" + key, row, [listing])
                    except Exception as exc:
                        self.error(exc, key)
                if scope.unique >= count:
                    scope.terminal = True
                    break
                page += 1
