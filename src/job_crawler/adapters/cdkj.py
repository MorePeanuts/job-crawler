"""Verified 2027 CJET campus campaign with two static position sections."""

from typing import Protocol, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


def value(node: Tag, selector: str) -> str:
    child = node.select_one(selector)
    return child.get_text("\n", strip=True) if child else ""


class Cdkj(Adapter):
    name = "cdkj-2027-static"
    host = "campus.51job.com"
    path = "/cdkj26/job.html"
    scope_description = (
        "长电科技 2027 校招活动页芯火计划及普通应届生全部城市申请 ID；无公开发布日期"
    )

    async def harvest(self) -> None:
        html = await cast(PageSession, self.session).page.content()
        document = BeautifulSoup(html, "html.parser")
        check("2027届" in document.get_text(" ", strip=True), "长电科技页面不再是 2027 届")
        sections = document.select(".jobContent")
        check(len(sections) == 2, "长电科技岗位分区结构改变")
        all_links = document.select('.jobContent a.submit[href*="external/apply.aspx"]')
        check(bool(all_links), "长电科技活动页缺少岗位申请链接")
        scope = Scope(name="cdkj-2027-static", expected=len(all_links))
        scope.evidence.append(self.session.last_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()

        def append_links(
            group: Tag,
            title: str,
            duties: str,
            requirements: str,
            education: str,
            batch: str,
        ) -> None:
            links = group.select('a.submit[href*="external/apply.aspx"]')
            check(bool(title and requirements and links), "长电科技岗位分组缺少标题、要求或链接")
            for link in links:
                scope.listed += 1
                apply_url = str(link.get("href", ""))
                parsed = urlsplit(apply_url)
                query = parse_qs(parsed.query)
                job_ids = query.get("jobid", [])
                check(
                    parsed.scheme == "https"
                    and parsed.hostname == "xyz.51job.com"
                    and parsed.path == "/external/apply.aspx"
                    and query.get("ctmid") == ["6628681"]
                    and len(job_ids) == 1
                    and job_ids[0].isdigit(),
                    "长电科技申请链接或租户 ID 改变",
                )
                job_id = job_ids[0]
                check(job_id not in seen, "长电科技岗位申请 ID 重复")
                seen.add(job_id)
                location = link.get_text(" ", strip=True)
                check(bool(location), "长电科技城市申请链接缺少地点")
                scope.unique += 1
                job = self.job(
                    job_id,
                    title=title,
                    batch=batch,
                    category_raw=title,
                    location=location,
                    education=education,
                    duties=duties,
                    requirements=requirements,
                    source_url=f"https://{self.host}{self.path}",
                    apply_url=apply_url,
                    field_sources={
                        "duties": ".jobinfo:培养方向" if batch else ".jobinfo1:岗位要求",
                        "requirements": ".jobinfo:专业要求"
                        if batch
                        else ".jobinfo1:招聘专业+学历要求",
                        "education": ".jobinfo:专业要求" if batch else ".jobinfo1:学历要求",
                        "location": "a.submit 城市文字",
                        "published": "source_missing",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [self.session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1

        title = ""
        groups = 0
        for child in sections[0].find_all(recursive=False):
            if not isinstance(child, Tag):
                continue
            classes = child.get("class") or []
            if "jobtitle" in classes:
                title = value(child, ".jobname")
            elif "jobinfo" in classes:
                requirements = value(child, ".yq + .job1")
                directions = value(child, ".fxs")
                check(bool(directions), "长电科技芯火计划缺少培养方向")
                append_links(
                    child, title, f"培养方向：{directions}", requirements, "硕士及以上", "芯火计划"
                )
                groups += 1
                title = ""
        check(not title and groups > 0, "长电科技芯火计划标题与详情未配对")
        regular = sections[1].select(":scope > .jobs")
        check(bool(regular), "长电科技普通校招岗位为空")
        for group in regular:
            title = value(group, ".jobname1")
            info = group.select_one(".jobinfo1")
            check(isinstance(info, Tag), "长电科技普通岗位缺少详情")
            assert isinstance(info, Tag)
            pieces = info.select(".job1")
            check(len(pieces) >= 3, "长电科技普通岗位专业、学历或岗位要求缺失")
            major, education, duties = (piece.get_text("\n", strip=True) for piece in pieces[:3])
            append_links(
                info,
                title,
                duties,
                f"招聘专业：{major}\n学历要求：{education}",
                education,
                "",
            )
        check(scope.unique == scope.expected, "长电科技申请链接未全部解析")
        scope.terminal = True
