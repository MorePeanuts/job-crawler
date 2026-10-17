"""ASUS mainland campus portals with an explicit legacy empty-state boundary."""

from typing import cast

from bs4 import BeautifulSoup

from job_crawler.adapters.platforms import check
from job_crawler.adapters.zhiye import Zhiye
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class AsusMainlandCampus(Zhiye):
    name = "asus-mainland-campus"
    host = "asustek.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "华硕大陆电脑及苏州研发双门户校园目录；其他地区独立系统不在此范围"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check("华硕科技（苏州）有限公司" in await session.page.content(), "华硕苏州门户身份变化")
        try:
            await super().harvest()
        except Exception as exc:
            self.error(exc, "suzhou-campus")
        scope = Scope(name="asus-computer-legacy-campus")
        self.result.scopes.append(scope)
        await session.open("https://asus.zhiye.com/Campus")
        doc = BeautifulSoup(await session.page.content(), "html.parser")
        body = doc.get_text(" ", strip=True)
        check("华硕电脑" in body and "校园招聘" in body, "华硕电脑旧门户身份变化")
        tables = doc.select(".joblist .jobsTable")
        check(len(tables) == 1, "华硕电脑旧门户目录表格变化")
        rows = tables[0].select("tr")
        check(
            len(rows) == 2
            and "职位名称" in rows[0].get_text()
            and rows[1].get_text(strip=True) == "无任何在招职位"
            and not rows[1].select("a[href]"),
            "华硕电脑旧门户不再明确为空，需要验证非零目录契约",
        )
        pagers = doc.select(".pager")
        check(
            len(pagers) == 1 and not pagers[0].get_text(strip=True) and not pagers[0].select("a"),
            "华硕电脑旧门户出现分页",
        )
        scope.expected = 0
        scope.terminal = True
        scope.evidence.append(session.last_evidence)
