"""Mingtai's complete inline directory, paired with canonical mobile job IDs."""

import re
from dataclasses import dataclass
from datetime import date
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://www.hngymt.com"
PATH = "/contact/recruitment/"
COMPANY = "河南明泰铝业股份有限公司"


@dataclass
class Card:
    key: str
    title: str
    location: str
    published: str
    url: str
    body: Tag


def mobile_fields(anchor: Tag) -> tuple[str, str, str, str]:
    heading = anchor.select_one("h2")
    place = anchor.select_one("p")
    check(heading is not None and place is not None, "明泰移动岗位字段缺失")
    assert heading is not None and place is not None
    published = heading.select_one("span")
    number = place.select_one("span")
    check(published is not None and number is not None, "明泰移动岗位日期或人数缺失")
    return (
        "".join(str(x) for x in heading.find_all(string=True, recursive=False)).strip(),
        "".join(str(x) for x in place.find_all(string=True, recursive=False)).strip(),
        text(number),
        text(published),
    )


def catalog(html: str) -> list[Card]:
    doc = BeautifulSoup(html, "html.parser")
    content = doc.get_text(" ", strip=True)
    check(
        COMPANY in content and "601677" in content and "人才招聘" in content,
        "明泰主体或招聘栏目变化",
    )
    desktop = doc.select(".table-box > ul.table > li")
    mobile = doc.select(".table-box-xs > ul > li > a")
    check(bool(desktop) and len(desktop) == len(mobile), "明泰双布局目录缺失或数量不符")
    check(
        not doc.select('.pagination, .pages, .page, a[rel="next"], [class*="load-more"]')
        and not any(
            re.search(r"(?:[?&](?:page|PageIndex)=|index_\d+\.)", str(a.get("href")))
            for a in doc.select("a[href]")
        ),
        "明泰出现未支持分页或加载更多",
    )
    identities: dict[tuple[str, str, str, str], tuple[str, str]] = {}
    seen: set[str] = set()
    for anchor in mobile:
        signature = mobile_fields(anchor)
        url = urljoin(ROOT + PATH, str(anchor.get("href") or ""))
        parts = urlsplit(url)
        match = re.fullmatch(r"/contact/recruitment/\d{4}/\d{4}/(\d+)\.shtml", parts.path)
        check(
            parts.hostname == "www.hngymt.com"
            and parts.scheme == "https"
            and not parts.query
            and match is not None,
            "明泰移动详情链接身份异常",
        )
        assert match is not None
        check(
            match[1] not in seen and signature not in identities, "明泰岗位ID重复或布局关联有歧义"
        )
        seen.add(match[1])
        identities[signature] = match[1], url
    cards = []
    for li in desktop:
        values = tuple(text(x) for x in li.select(":scope > .item"))
        check(len(values) == 4 and values in identities, "明泰桌面与移动字段错配")
        title, location, number, published = values
        key, url = identities.pop((title, location, number, published))
        check(
            bool(title and location) and date.fromisoformat(published).isoformat() == published,
            "明泰岗位标题、地点或日期异常",
        )
        body = li.select_one(":scope > .con")
        check(body is not None, "明泰完整内联正文缺失")
        assert body is not None
        cards.append(Card(key, title, location, published, url, body))
    check(not identities, "明泰移动目录存在未匹配岗位")
    return cards


def sections(card: Card) -> dict[str, str]:
    result: dict[str, str] = {}
    for block in card.body.select(":scope > .bb"):
        heading = block.select_one(":scope > .tt")
        label = text(heading)
        check(
            label in {"任职要求", "岗位职责", "薪酬福利"} and label not in result,
            "明泰正文章节缺失、重复或变化",
        )
        check(not block.select("img,a[href],iframe,object,embed"), "明泰正文含未处理附件")
        paragraphs = block.find_all("p", recursive=False)
        check(bool(paragraphs), "明泰正文段落结构变化")
        result[label] = "\n".join(text(p) for p in paragraphs)
    check(
        set(result) == {"任职要求", "岗位职责", "薪酬福利"} and all(result.values()),
        "明泰完整职责、要求或福利章节缺失",
    )
    return result


def accepts_graduates(requirements: str) -> bool:
    if "应届" not in requirements:
        return False
    positive = bool(re.search(r"(?:^|\n)\s*\d+[、.]\s*接受应届毕业生[，,；;。]", requirements))
    negative = "不接受应届毕业生" in requirements
    check(positive != negative, "明泰应届资格表述未知或矛盾")
    return positive


class MingtaiCampus(Adapter):
    name = "mingtai-campus"
    host = "www.hngymt.com"
    path = PATH
    scope_description = "明泰官网完整招聘目录；仅任职要求明确接受应届毕业生的正式岗位"

    async def harvest(self) -> None:
        html = await cast(BrowserSession, self.session).page.content()
        cards = catalog(html)
        scope = Scope(
            name="mingtai-all-public-jobs",
            expected=len(cards),
            listed=len(cards),
            unique=len(cards),
        )
        scope.evidence.append(self.session.last_evidence)
        self.result.scopes.append(scope)
        for card in cards:
            try:
                values = sections(card)
                if not accepts_graduates(values["任职要求"]):
                    scope.skipped_out_of_scope += 1
                    continue
                duty_lines = values["岗位职责"].splitlines()
                department = next(
                    (
                        line.removeprefix("所属部门：").strip()
                        for line in duty_lines
                        if line.startswith("所属部门：")
                    ),
                    "",
                )
                job = self.job(
                    card.key,
                    title=card.title,
                    unit=department,
                    location=card.location,
                    duties=values["岗位职责"],
                    requirements=values["任职要求"],
                    published=card.published,
                    source_url=card.url,
                    work_type="校招",
                    field_sources={
                        "published": "官网目录明确的发布时间，桌面与移动字段一致",
                        "deadline": "source_missing:官网未披露截止时间",
                        "duties": "ul.table内联岗位职责章节",
                        "requirements": "ul.table内联任职要求章节，明确接受应届毕业生",
                        "unit": "岗位职责中的所属部门，不改写公司主体",
                        "location": "官网工作地点原文，不推断详细地址",
                    },
                )
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, card.key)
        scope.terminal = True
