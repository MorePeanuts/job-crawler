"""Yankuang Energy's linked 2027 graduate jobs on UIBE."""

import re
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "兖矿能源集团股份有限公司"
NOTICE_ID = "2098326250287316994"


def compact(value: str) -> str:
    return "".join(text(value).split())


def listing(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h3.content_title")
    body = soup.select_one(".content")
    check(
        title is not None
        and compact(title.get_text()) == f"{EMPLOYER}2027届校园招聘"
        and body is not None,
        "兖矿高校公告标题或正文变化",
    )
    assert body is not None
    page = compact(body.get_text(" ", strip=True))
    check(
        f"招聘单位：{EMPLOYER}" in page
        and "山东能源集团的旗舰资产" in page
        and "国(境)内外2027年毕业的本科及以上学历毕业生" in page
        and "在招职位" in page,
        "兖矿公告主体、集团关系或招聘届别变化",
    )
    anchors = body.select('a[href*="/front/zwxx.jspa?"]')
    check(bool(anchors), "兖矿高校公告在招职位为空或链接缺失")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in anchors:
        href = str(anchor.get("href") or "")
        url = urljoin("https://aeo.uibe.edu.cn", href)
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        keys = query.get("xqzwId") or []
        parent = query.get("zpxxId") or []
        title_text = text(anchor.get_text(" ", strip=True)).lstrip("> ").strip()
        check(
            parts.scheme == "https"
            and parts.netloc == "aeo.uibe.edu.cn"
            and parts.path == "/front/zwxx.jspa"
            and len(keys) == len(parent) == 1
            and keys[0].isdigit()
            and parent[0] == NOTICE_ID
            and bool(title_text)
            and keys[0] not in seen,
            "兖矿在招职位 ID、标题或公告关联变化",
        )
        seen.add(keys[0])
        rows.append({"key": keys[0], "title": title_text, "url": url})
    return rows


def detail(html: str, expected_title: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h3.content_header_title")
    desc = soup.select_one(".content_header_desc")
    body = soup.select_one(".content")
    facts = soup.select_one(".content_detail")
    check(
        title is not None
        and text(title.get_text()) == expected_title
        and desc is not None
        and body is not None
        and facts is not None,
        "兖矿职位详情标题或结构变化",
    )
    assert desc is not None and body is not None and facts is not None
    header = compact(desc.get_text(" ", strip=True))
    check(EMPLOYER in header, "兖矿职位详情招聘主体不一致")
    dates = re.findall(r"发布于(\d{4}-\d{2}-\d{2})", header)
    check(len(dates) == 1, "兖矿职位详情发布时间缺失或重复")
    content = text(body.get_text(" ", strip=True))
    check("2027年毕业的本科及以上学历毕业生" in content, "兖矿职位非 2027 届应届")
    majors = re.search(r"招聘专业：\s*(.*?)\s*岗位要求：", content)
    check(majors is not None and bool(majors[1]), "兖矿职位详情专业要求缺失")
    assert majors is not None
    locations = [
        text(p.get_text(" ", strip=True)).removeprefix("工作地点：").strip()
        for p in facts.select("p")
        if compact(p.get_text()).startswith("工作地点：")
    ]
    check(len(locations) == 1 and bool(locations[0]), "兖矿职位详情工作地点缺失")
    return {
        "published": dates[0],
        "location": locations[0],
        "majors": majors[1].strip(),
        "requirements": content,
    }


class YankuangUibe2027(Adapter):
    name = "yankuang-uibe-2027"
    host = "aeo.uibe.edu.cn"
    path = f"/front/zpxx.jspa?tid={NOTICE_ID}"
    scope_description = "山东能源旗下兖矿能源在贸大 2027 届公告的全部在招职位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "兖矿高校公告未就绪")
        rows = listing(await session.page.content())
        list_evidence = session.last_evidence
        scope = Scope(name=f"yankuang-uibe-2027-{NOTICE_ID}", expected=len(rows))
        scope.evidence.append(list_evidence)
        self.result.scopes.append(scope)
        for item in self.add_page(scope, rows, set(), lambda row: row["key"]):
            key = item["key"]
            brief = self.job(key, title=item["title"], source_url=item["url"])
            reused = self.before_detail(f"job:{key}", item, scope, brief)
            if reused is not None:
                self.result.jobs.extend(reused)
                continue
            try:
                await session.open(item["url"])
                data = detail(await session.page.content(), item["title"])
                job = self.job(
                    key,
                    title=item["title"],
                    source_url=item["url"],
                    unit=EMPLOYER,
                    work_type="校招",
                    location=data["location"],
                    education="本科及以上",
                    requirements=data["requirements"],
                    published=data["published"],
                    field_sources={
                        "unit": "公告及职位详情均标明兖矿能源；公告称其为山东能源旗舰资产",
                        "title": "在招职位链接与详情标题一致",
                        "location": "职位详情工作地点",
                        "education": "职位详情岗位要求明确 2027 届本科及以上",
                        "requirements": "职位详情招聘专业和岗位要求",
                        "published": "职位详情发布于日期；列表更新时间不作为发布日",
                        "headcount": "公告招聘人数 5 是名额，不拆岗",
                        "duties": "source_missing:未单列岗位职责",
                        "deadline": "source_missing:高校职位未列申请截止日期",
                    },
                )
                job.evidence = [list_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", item, [job])
            except Exception as exc:
                self.error(exc, key)
        scope.terminal = True
