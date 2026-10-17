"""Guotai Haitong's public, server-rendered campus catalog and folded details."""

import re
from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


def page_metadata(document: BeautifulSoup) -> tuple[int, int, int]:
    scripts = "\n".join(node.get_text() for node in document.select("script:not([src])"))
    values: list[int] = []
    for key in ("dataTotal", "current", "pageSize"):
        matches = re.findall(rf'\b{key}\s*[:=]\s*["\']?(\d+)', scripts)
        check(len(matches) == 1, f"国泰海通分页元数据 {key} 不唯一")
        values.append(int(matches[0]))
    return values[0], values[1], values[2]


class GuotaiHaitongCampus(Adapter):
    name = "guotai-haitong-campus"
    host = "hr.gtht.com"
    path = "/recruitment/main/recruit2"
    scope_description = "国泰海通校园 systemjobtype=2,4 全部机构目录；同页完整折叠职责与要求"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        context = await session.page.evaluate("""() => ({
          url:filterUrl(),kind:systemjobtype,company:document.querySelector('#clickCompany').value
        })""")
        url = f"https://{self.host}{self.path}"
        check(context == {"url": url, "kind": "2,4", "company": ""}, "国泰海通校园目录有残留筛选")
        html = await session.page.content()
        check("国泰海通证券股份有限公司" in html, "国泰海通页面主体变化")
        scope = Scope(name="all-campus-institutions")
        self.result.scopes.append(scope)
        page = 1
        seen: set[str] = set()
        while True:
            document = BeautifulSoup(html, "html.parser")
            count, current, size = page_metadata(document)
            check(count >= 0 and current == page and size == 30, "国泰海通页码或页大小不一致")
            if scope.expected is None:
                scope.expected = count
            check(scope.expected == count, "国泰海通分页期间岗位总数变化")
            cards = document.select(".job-list-con > ul")
            check(
                len(cards) == min(30, max(count - (page - 1) * 30, 0)), "国泰海通当页岗位数不完整"
            )
            scope.evidence.append(session.last_evidence)
            for card in cards:
                scope.listed += 1
                try:
                    anchors = card.select("a[data-job_id]")
                    check(len(anchors) == 1, "国泰海通卡片岗位 ID 缺失或重复")
                    key = str(anchors[0]["data-job_id"])
                    check(key.isdigit() and key not in seen, "国泰海通岗位 ID 非法或跨页重复")
                    seen.add(key)
                    scope.unique += 1
                    fields = card.select("li.list-li > span.con")
                    check(len(fields) == 5, "国泰海通卡片字段布局变化")
                    title, unit, education, _, location = [
                        node.get_text(strip=True) for node in fields
                    ]
                    body = card.select_one(".job-description-li")
                    check(bool(title) and body is not None, "国泰海通岗位标题或折叠详情缺失")
                    assert body is not None
                    duties, requirements = split_sections(body.get_text("\n", strip=True))
                    check(bool(duties or requirements), "国泰海通岗位正文为空")
                    self.result.jobs.append(
                        self.job(
                            key,
                            title=title,
                            unit=unit,
                            education=education,
                            location=location,
                            source_url=url,
                            duties=duties,
                            requirements=requirements,
                            field_sources={
                                "duties": "完整岗位卡片的隐藏 job-description-li 正文",
                                "requirements": "完整岗位卡片的隐藏 job-description-li 正文",
                                "education": "校园目录学历要求",
                                "location": "校园目录工作地点，保留多城市原文",
                                "published": "source_missing",
                                "deadline": "source_missing",
                            },
                        )
                    )
                    scope.details += 1
                except Exception as exc:
                    self.error(exc)
            if page * size >= count:
                scope.terminal = True
                break
            page += 1
            html = await session.request_html(
                url,
                validate_html=False,  # Public pagination returns a catalog fragment, not a document.
                form={
                    "n": "1",
                    "company[]": "",
                    "systemjobtype": "2,4",
                    "p": str(page),
                },
            )
