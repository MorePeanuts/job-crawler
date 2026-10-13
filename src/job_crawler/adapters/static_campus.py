"""Verified official HTML graduate catalogs, preserving missing source fields."""

import re
from typing import cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.adapters.smic import HtmlSession
from job_crawler.models import Scope


class SystCampus(Adapter):
    name = "syst-campus"
    host = "www.syst.com.cn"
    path = "/cn/zwztc/index_77.aspx"
    scope_description = (
        "生益科技官网校园职位直通车全部岗位卡；不包含宣讲行程；官网未给职责则保留待补全"
    )

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        soup = BeautifulSoup(await session.page.content(), "html.parser")
        check("campus recruitment" in soup.get_text().lower(), "生益非校园入口")
        cards = soup.select(".scItem")
        check(bool(cards), "生益职位目录为空或改版")
        scope = Scope(name="syst-campus-cards", expected=len(cards))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        rows = []
        for card in cards:
            button = card.select_one("[jobid]")
            check(button is not None, "生益岗位ID缺失")
            assert button

            def field(cls: str, card: Tag = card) -> str:
                node = card.select_one("dl.job ." + cls)
                check(node is not None, f"生益字段缺失{cls}")
                assert node
                return node.get_text(" ", strip=True)

            rows.append(
                {
                    "id": str(button["jobid"]),
                    "title": field("name"),
                    "education": field("edu"),
                    "location": field("add"),
                    "major": field("major"),
                }
            )
        for row in self.add_page(scope, rows, seen, lambda r: r["id"]):
            self.result.jobs.append(
                self.job(
                    row["id"],
                    title=row["title"],
                    education=row["education"],
                    location=row["location"],
                    requirements="专业：" + row["major"],
                    source_url=f"https://{self.host}{self.path}#scItemID{row['id']}",
                    field_sources={
                        "education": "校园岗位卡.edu",
                        "requirements": "校园岗位卡.major",
                        "duties": "source_missing",
                        "published": "source_missing",
                        "deadline": "source_missing",
                    },
                )
            )
            scope.details += 1
        scope.terminal = True


class TiannengCampus(Adapter):
    name = "tianneng-campus"
    host = "www.tianneng.com"
    path = "/career/campus-recruitment"
    scope_description = "天能官网校园招聘所有分页和完整公开岗位卡；无正文时保留源站已知学历/专业；外部投递系统不可用另记"

    async def harvest(self) -> None:
        session = cast(HtmlSession, self.session)
        first = await session.page.content()
        soup = BeautifulSoup(first, "html.parser")
        page_numbers = {
            int(m[1])
            for a in soup.select("a[href]")
            if (m := re.fullmatch(r"/career/campus-recruitment_(\d+)", str(a["href"])))
        }
        check(bool(page_numbers), "天能缺少已验证分页结构")
        pages = max(page_numbers)
        check(page_numbers == set(range(2, pages + 1)), "天能分页不连续")
        scope = Scope(name="tianneng-campus-html")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for page in range(1, pages + 1):
            url = f"https://{self.host}{self.path}" + (f"_{page}" if page > 1 else "")
            if page > 1:
                soup = BeautifulSoup(await session.request_html(url), "html.parser")
            cards = soup.select("li.join_inof_item")
            check(bool(cards), "天能分页提前为空")
            rows = []
            for card in cards:
                fields = card.select("ul.join_core_table_tr > li")
                check(len(fields) == 6, "天能目录列改变")
                a = card.select_one('a[href*="tzId="]')
                check(a is not None, "天能岗位投递标识缺失")
                assert a
                link = str(a["href"])
                keys = parse_qs(urlsplit(link).query)
                check(len(keys.get("tzId", [])) == 1, "天能岗位ID无效")
                meta = {}
                for item in card.select(".join_base_name"):
                    label = item.select_one(".std_title5")
                    value = item.select_one(".std_text1")
                    assert label and value
                    meta[label.get_text(strip=True).rstrip("：:")] = value.get_text(" ", strip=True)
                bodies = {}
                for item in card.select(".join_inof_active_item"):
                    label = item.select_one("h4")
                    value = item.select_one(".std_text18")
                    assert label and value
                    bodies[label.get_text(strip=True).rstrip("：:")] = value.get_text(
                        "\n", strip=True
                    )
                rows.append(
                    {
                        "id": keys["tzId"][0],
                        "title": fields[0].get_text(strip=True),
                        "location": fields[1].get_text(strip=True),
                        "category_raw": fields[2].get_text(strip=True),
                        "published": fields[4].get_text(strip=True),
                        "education": meta.get("学历要求", ""),
                        "requirements": "\n".join(
                            v
                            for v in [
                                bodies.get("岗位要求", ""),
                                "专业：" + meta["专业"] if meta.get("专业") else "",
                            ]
                            if v
                        ),
                        "duties": bodies.get("岗位职责", ""),
                        "apply_url": link,
                        "source_url": url,
                    }
                )
            for row in self.add_page(scope, rows, seen, lambda r: r["id"]):
                self.result.jobs.append(
                    self.job(
                        row["id"],
                        **{k: v for k, v in row.items() if k != "id"},
                        field_sources={
                            "published": "校园目录发布时间",
                            "education": "学历要求",
                            "requirements": "岗位要求及专业",
                            "duties": "岗位职责（源站可为空）",
                            "deadline": "source_missing",
                        },
                    )
                )
                scope.details += 1
        scope.terminal = True


TENANTS = (SystCampus, TiannengCampus)
