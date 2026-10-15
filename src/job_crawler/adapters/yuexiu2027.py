"""Yuexiu Property's public 2027 campus jobs embedded in its official site asset."""

import json
import re
from typing import Protocol, cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

JOB_NODE = re.compile(
    r'content:"((?:\\.|[^"\\])*)",jobs_url:"((?:\\.|[^"\\])*)"'
    r'\}\),t\(n,\{class:"grace-inner-web-content-text-job-text",textList:\[(.*?)\]\}\)',
    re.S,
)
TEXT_NODE = re.compile(r'text:"((?:\\.|[^"\\])*)"')
ASSET = re.compile(r"/assets/yxywl-[0-9a-f]+\.js$")


class HtmlPage(Protocol):
    async def content(self) -> str: ...


class AssetSession(Protocol):
    page: HtmlPage
    last_evidence: str

    async def request_html(self, url: str, *, validate_html: bool = True) -> str: ...


def parse_jobs(script: str) -> list[dict[str, str]]:
    jobs = []
    for match in JOB_NODE.finditer(script):
        title = json.loads('"' + match[1] + '"')
        apply_url = json.loads('"' + match[2] + '"')
        parts = [json.loads('"' + raw + '"') for raw in TEXT_NODE.findall(match[3])]
        check(len(parts) == 6, "越秀校园职位正文段数改变")
        headings = [
            BeautifulSoup(parts[index], "html.parser").get_text(" ", strip=True)
            for index in (0, 2, 4)
        ]
        check(
            "岗位描述" in headings[0]
            and "岗位要求" in headings[1]
            and headings[2] in {"工作城市：", "工作地点："},
            "越秀校园职位正文标题改变",
        )
        query = parse_qs(urlsplit(apply_url).query)
        check(
            urlsplit(apply_url).netloc == "xiaoyuan.zhaopin.com"
            and urlsplit(apply_url).path == "/scrd/postprocess2"
            and query.get("projectId") == ["105954"]
            and len(query.get("pid", [])) == 1
            and len(query.get("jobNumber", [])) == 1,
            "越秀校园职位投递身份改变",
        )
        jobs.append(
            {
                "id": query["pid"][0],
                "job_number": query["jobNumber"][0],
                "title": title,
                "apply_url": apply_url,
                "duties": BeautifulSoup(parts[1], "html.parser").get_text(" ", strip=True),
                "requirements": BeautifulSoup(parts[3], "html.parser").get_text(" ", strip=True),
                "location": BeautifulSoup(parts[5], "html.parser").get_text(" ", strip=True),
            }
        )
    return jobs


class YuexiuProperty2027(Adapter):
    name = "zhaopin-yuexiu-property-2027"
    host = "yxdc2027.zhaopin.com"
    path = "/yxywl/index.html"
    scope_description = "越秀地产 2027 毓秀生开发、商业、物业三个板块的 30 个唯一公开职位"

    async def harvest(self) -> None:
        session = cast(AssetSession, self.session)
        soup = BeautifulSoup(await session.page.content(), "html.parser")
        check("毓秀生" in soup.get_text(" ", strip=True), "越秀入口不是毓秀生招聘页面")
        assets = [
            str(tag.get("src", ""))
            for tag in soup.select("script[src]")
            if ASSET.search(str(tag.get("src", "")))
        ]
        check(len(assets) == 1, "越秀校园职位脚本缺失或重复")
        script = await session.request_html(
            urljoin(self.source.url, assets[0]), validate_html=False
        )
        check(
            all(name in script for name in ("毓秀生（开发）", "毓秀生（商业）", "毓秀生（物业）")),
            "越秀校园板块不完整",
        )
        rows = parse_jobs(script)
        check(len(rows) == 31, "越秀校园职位展示数量变化，需重验全目录")
        unique: dict[str, dict[str, str]] = {}
        for row in rows:
            previous = unique.get(row["id"])
            if previous:
                check(
                    row["job_number"] == previous["job_number"]
                    and row["apply_url"] == previous["apply_url"],
                    "越秀重复展示的岗位身份不一致",
                )
            else:
                unique[row["id"]] = row
        check(len(unique) == 30, "越秀校园唯一岗位数量变化")
        scope = Scope(name="yxywl-three-programs", expected=30)
        self.result.scopes.append(scope)
        evidence = session.last_evidence
        seen: set[str] = set()
        for row in self.add_page(scope, list(unique.values()), seen, lambda item: item["id"]):
            check(
                bool(row["title"] and row["duties"] and row["requirements"] and row["location"]),
                "越秀校园职位缺少标题、正文或城市",
            )
            job = self.job(
                row["id"],
                title=row["title"],
                duties=row["duties"],
                requirements=row["requirements"],
                location=row["location"],
                source_url=self.source.url,
                apply_url=row["apply_url"],
                field_sources={
                    "duties": "官方 2027 招聘脚本 textList[1]",
                    "requirements": "官方 2027 招聘脚本 textList[3]",
                    "location": "官方 2027 招聘脚本 textList[5]",
                    "published": "source_missing",
                    "deadline": "source_missing",
                    "unit": "source_missing",
                },
            )
            job.evidence = [evidence]
            self.result.jobs.append(job)
            scope.details += 1
            self.remember(f"job:{row['id']}", row, [job])
        scope.terminal = True
