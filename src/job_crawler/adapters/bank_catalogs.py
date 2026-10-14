"""Public bank graduate catalogs; no resume submission or login."""

import asyncio
import json
import re
from typing import cast
from urllib.parse import parse_qs

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.adapters.smic import HtmlSession
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


class CzbankCampus(Adapter):
    name = "czbank-campus"
    host = "zp.czbank.com.cn"
    path = "/zpWebMobile/loginController/checkPage.mvc?pageType=1"
    scope_description = "浙商银行公开校园岗位全国无机构筛选目录；按实际仍展示且未截止筛选"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        browser = cast(BrowserSession, self.session)
        html = await session.page.content()
        pages_match = re.search(r"var maxnum = '(\d+)'", html)
        check(pages_match is not None, "浙商银行缺少总页数")
        assert pages_match is not None
        pages = int(pages_match[1])
        check(0 < pages <= 500, "浙商银行页数无效")
        for number in range(2, pages + 1):
            browser.consume_request()
            await browser.page.evaluate("() => window.scrollTo(0,document.body.scrollHeight)")
            for _ in range(60):
                count = await browser.page.locator('a[href^="javaScript:jobDetails"]').count()
                if count > (number - 1) * 10:
                    break
                await asyncio.sleep(0.3)
            else:
                raise ValueError("浙商银行滚动分页未新增岗位")
            await browser.page.evaluate("() => window.scrollTo(0,0)")
        html = await browser.page.content()
        browser.snapshot("campus-full", html)
        soup = BeautifulSoup(html, "html.parser")
        check("没有更多职位了" in soup.get_text(), "浙商银行目录缺少结束状态")
        anchors = soup.select('a[href^="javaScript:jobDetails"]')
        check((pages - 1) * 10 < len(anchors) <= pages * 10, "浙商银行全目录数量不符合页数")
        scope = Scope(name="czbank-campus-national", expected=len(anchors))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        rows = []
        for a in anchors:
            match = re.fullmatch(r"javaScript:jobDetails\('([^']+)','1'\)", str(a["href"]))
            check(match is not None, "浙商银行岗位类别或链接改变")
            assert match

            def field(selector: str, a: Tag = a) -> str:
                item = a.select_one(selector)
                check(item is not None, f"浙商银行缺少{selector}")
                assert item
                return item.get_text(" ", strip=True)

            check("校园招聘" in a.get_text(), "浙商银行目录混入其他类型")
            rows.append(
                {
                    "id": match[1],
                    "title": field(".potitle"),
                    "deadline": field(".date"),
                    "education": field("h3.so > span:last-child"),
                    "location": field(".map"),
                    "unit": field(".bank"),
                }
            )
        for row in self.add_page(scope, rows, seen, lambda r: r["id"]):
            url = f"https://{self.host}/zpWebMobile/zpPostController/jobDetailPage.mvc?postId={row['id']}&zpType=1"
            listing = self.job(
                row["id"], **{k: v for k, v in row.items() if k != "id"}, source_url=url
            )
            resolved = self.before_detail(f"job:{row['id']}", row, scope, listing)
            if resolved is not None:
                self.result.jobs.extend(resolved)
                continue
            try:
                html = await browser.request_html(url, detail=True, encoding="gb18030")
                detail = BeautifulSoup(html, "html.parser")
                check(row["title"] in detail.get_text(), "浙商银行详情标题不符")
                blocks = detail.select(".duty")
                check(bool(blocks), "浙商银行缺少详情正文")
                requirements = []
                duties = []
                for block in blocks:
                    label = block.select_one(".dutytitle")
                    check(label is not None, "浙商银行正文标题缺失")
                    assert label
                    heading = label.get_text(strip=True)
                    label.decompose()
                    value = block.get_text("\n", strip=True)
                    (
                        requirements
                        if any(x in heading for x in ["要求", "条件", "资格"])
                        else duties
                    ).append(value)
                listing.duties = "\n".join(duties)
                listing.requirements = "\n".join(requirements)
                listing.evidence.append(self.session.last_evidence)
                listing.field_sources = {
                    "requirements": "详情基本要求",
                    "deadline": "当前招聘公告简历接收截止时间及目录日期",
                    "published": "source_missing",
                }
                self.result.jobs.append(listing)
                scope.details += 1
                self.remember(f"job:{row['id']}", row, [listing])
            except Exception as exc:
                self.error(exc, row["id"])
        scope.terminal = True


class HrbbCampus(Adapter):
    name = "hrbb-campus"
    host = "wisehr.hrbb.com.cn"
    path = "/pages/jobs/index.html"
    ready_endpoints = ("/resume/list",)
    scope_description = "哈尔滨银行官方2027校园招聘主门户全部58类岗位；哈银消费金融独立门户单独列明，不冒充本门户覆盖"

    async def harvest(self) -> None:
        observed = await self.session.observed("/resume/list")
        check(
            parse_qs(observed["post_data"], keep_blank_values=True)
            == {"resumetype": ["2"], "searchKey": [""], "rid": [""]},
            "哈尔滨银行目录类别或筛选改变",
        )
        data = json.loads(observed["body"])
        check(
            data.get("state") == "success" and data.get("retcode") == "000000", "哈尔滨银行业务失败"
        )
        rows = data["Data"]
        check(bool(rows), "哈尔滨银行校园目录为空")
        session = cast(HtmlSession, self.session)
        soup = BeautifulSoup(await session.page.content(), "html.parser")
        check("2027校园招聘" in soup.get_text(), "哈尔滨银行校园项目变化")
        scope = Scope(name="hrbb-campus-main", expected=len(rows))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in self.add_page(scope, rows, seen, lambda r: str(r["id"])):
            check(
                str(row["recruitType"]) == "2" and row["worktypename"] == "全职",
                "哈尔滨银行类别不符",
            )
            check(
                bool(row["jobInfo"]) and row["name"] in soup.get_text(),
                "哈尔滨银行岗位正文或页面标题缺失",
            )
            duties, requirements = sections(
                text(row["jobInfo"])
                .replace("【基本条件】", "【基本要求】")
                .replace("【岗位职责】", "【工作职责】")
            )
            self.result.jobs.append(
                self.job(
                    str(row["id"]),
                    title=text(row["name"]),
                    source_url=f"https://{self.host}{self.path}",
                    education="",
                    location=text(row["address"]),
                    unit=text(row["resumeDept"]),
                    duties=duties,
                    requirements=requirements,
                    published=text(row["publicTime"]),
                    field_sources={
                        "duties": "resume/list.jobInfo",
                        "requirements": "resume/list.jobInfo:条件",
                        "published": "publicTime",
                        "deadline": "source_missing",
                    },
                )
            )
            scope.details += 1
        scope.terminal = True


TENANTS = (CzbankCampus, HrbbCampus)
