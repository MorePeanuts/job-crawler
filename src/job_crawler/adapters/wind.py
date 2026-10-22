"""Wind's server-rendered public 2027 campus project."""

import json
from typing import Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


class Wind2027(Adapter):
    name = "wind-2027"
    host = "www.wind.com.cn"
    path = "/mobile/JoinUS/RecruitDetail/zh.html?entry=school"
    scope_description = "万得官网服务端 2027年校园招聘项目全目录；排除社招和实习项目"

    async def harvest(self) -> None:
        html = await cast(PageSession, self.session).page.content()
        soup = BeautifulSoup(html, "html.parser")
        script = soup.select_one('script[id="__NEXT_DATA__"]')
        check(script is not None and bool(script.string), "万得页面缺少服务端岗位数据")
        assert script is not None and script.string is not None
        data = json.loads(script.string)
        locale = data["props"]["pageProps"]["locale"]
        notices = locale["notice"]
        check(
            any(
                item.get("title") == "2027年校园招聘" and item.get("id") == "school"
                for item in notices
            ),
            "万得校招项目入口改变",
        )
        rows = locale["channelPositions"]
        check(isinstance(rows, list) and bool(rows), "万得服务端岗位目录为空或改变")
        scope = Scope(name="wind-2027-ssr", expected=len(rows))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in rows:
            check(isinstance(row, dict), "万得岗位不是对象")
            key = str(row["ChannelPositionID"])
            check(key.isdigit() and key not in seen, "万得岗位 ID 重复或无效")
            seen.add(key)
            scope.listed += 1
            scope.unique += 1
            projects = row.get("Projects") or []
            check(isinstance(projects, list), "万得岗位项目字段改变")
            project_names = {text(project.get("Name")) for project in projects}
            if "2027年校园招聘" not in project_names:
                scope.skipped_out_of_scope += 1
                continue
            check(project_names == {"2027年校园招聘"}, "万得 2027 校招岗位混入其他项目")
            check(row.get("PositionTypeText") == "校招", "万得 2027 项目招聘性质改变")
            check(
                row.get("InUse") is True and row.get("ExpireFlag") is False,
                "万得 2027 项目含已关闭岗位",
            )
            check(
                any(item.get("Name") == "Wind官网" for item in (row.get("Source") or [])),
                "万得岗位未面向官网公开",
            )
            title = text(row.get("ChannelPositionName"))
            duties = text(row.get("ChannelPositionDesc"))
            requirements = text(row.get("ChannelPositionRequirement"))
            check(bool(title and duties and requirements), "万得 2027 岗位标题或正文缺失")
            places = row.get("WorkPlace") or []
            check(isinstance(places, list), "万得岗位地点结构改变")
            self.result.jobs.append(
                self.job(
                    key,
                    title=title,
                    source_url=(
                        f"https://{self.host}/mobile/JoinUS/PositionDetail/zh.html"
                        f"?ChannelPositionID={key}"
                    ),
                    location="、".join(dict.fromkeys(text(item.get("Name")) for item in places)),
                    category_raw=text(row.get("PositionClassName")),
                    batch="2027年校园招聘",
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("PublishDate")),
                    deadline=text(row.get("ExpireDate")),
                    field_sources={
                        "duties": "__NEXT_DATA__.locale.channelPositions[].ChannelPositionDesc",
                        "requirements": "__NEXT_DATA__.locale.channelPositions[].ChannelPositionRequirement",
                        "published": "__NEXT_DATA__.locale.channelPositions[].PublishDate",
                        "location": "__NEXT_DATA__.locale.channelPositions[].WorkPlace",
                    },
                )
            )
            scope.details += 1
        scope.evidence.append(self.session.last_evidence)
        scope.terminal = True
