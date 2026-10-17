"""Pacific Construction's complete static campus category cards."""

from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class CpcgCampus(Adapter):
    name = "cpcg-campus"
    host = "www.cpcg.com.cn"
    path = "/index.php/rlzy/xyzp.html"
    scope_description = "太平洋建设官网校园招聘全部静态类别卡片及折叠任职要求；不拆造具体工种"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        document = BeautifulSoup(await session.page.content(), "html.parser")
        body = document.get_text(" ", strip=True)
        check(
            "太平洋建设 版权所有" in body and "CAMPUS RECRUITING" in body.upper(),
            "太平洋建设校园页身份变化",
        )
        check(not document.select(".pagination,.pager,[data-page]"), "太平洋建设出现未验证分页")
        cards = document.select(".xyzp-item")
        check(bool(cards), "太平洋建设校园类别缺失，不能作为零岗位")
        scope = Scope(name="cpcg-campus-categories", expected=len(cards), unit="招聘类别")
        scope.evidence.append(session.last_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for card in cards:
            scope.listed += 1
            try:
                title = text(card.select_one(".xyzp-item-title h1"))
                check(bool(title) and title not in seen, "太平洋建设类别标题缺失或重复")
                seen.add(title)
                scope.unique += 1
                info = [node.get_text(strip=True) for node in card.select(".xyzp-item-info p")]
                education = [
                    value.removeprefix("学历：") for value in info if value.startswith("学历：")
                ]
                major = [value for value in info if value.startswith("专业：")]
                requirements = [
                    node.get_text(strip=True) for node in card.select(".xyzp-item-bottom p")
                ]
                check(
                    len(education) == 1 and bool(major) and bool(requirements),
                    "太平洋建设任职要求或学历结构缺失",
                )
                job = self.job(
                    f"campus:{title}",
                    title=title,
                    source_url=f"https://{self.host}{self.path}",
                    education=education[0],
                    requirements="\n".join([*major, *requirements]),
                    field_sources={
                        "requirements": "校园类别卡片专业及完整折叠任职要求",
                        "education": "校园类别卡片学历",
                        "duties": "source_missing:未提供独立岗位职责",
                        "published": "source_missing",
                        "deadline": "source_missing",
                        "location": "source_missing:可外派不代表具体城市",
                    },
                )
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc)
        scope.terminal = True
