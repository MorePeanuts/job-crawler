"""LONGi's server-rendered legacy Hotjob campus catalog for its listed parent."""

import re
from typing import Protocol, cast
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope

ROOT = "https://www.hotjob.cn"
LIST_PATH = "/wt/LONGI/mobweb/v8/position/list"
DETAIL_PATH = "/wt/LONGI/mobweb/v8/position/detail"
COMPANY = "隆基绿能科技股份有限公司"
PAGE_SIZE = 10
ID_PATTERN = re.compile(r"toDetailPostUrl\((\d+),1,(\d+)\)")
DETAIL_ID_PATTERN = re.compile(r'var postId\s*=\s*"(\d+)"')
DETAIL_TYPE_PATTERN = re.compile(r'var recruitType\s*=\s*"1"')


class LegacyPage(Protocol):
    async def content(self) -> str: ...


class LegacySession(Protocol):
    page: LegacyPage
    last_evidence: str

    async def request_html(self, url: str, *, detail: bool = False) -> str: ...


def _page_url(page: int) -> str:
    values: dict[str, str] = {"brandCode": "1", "recruitType": "1"}
    if page > 1:
        values = {
            "ajaxMini": "true",
            "pc.currentPage": str(page),
            "recruitType": "1",
            "brandCode": "1",
        }
    return ROOT + LIST_PATH + "?" + urlencode(values)


def _detail_url(job_id: str, page: int) -> str:
    return (
        ROOT
        + DETAIL_PATH
        + "?"
        + urlencode(
            {
                "safe": "Y",
                "canBack": "true",
                "recruitType": "1",
                "postIdsAry": job_id,
                "postCanApply": "0",
                "entityPage.currentPage": page,
                "openid": "",
                "brandCode": "1",
                "chooseSiteId": "",
            }
        )
    )


def _text(node: Tag | None) -> str:
    return node.get_text("\n", strip=True) if node else ""


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _cards(html: str, page: int) -> tuple[list[tuple[str, Tag]], str | None]:
    doc = BeautifulSoup(html, "html.parser")
    rows = doc.select("li.position_list-list-demo")
    cards: list[tuple[str, Tag]] = []
    for row in rows:
        target = row.select_one('[onclick^="javascript:toDetailPostUrl"]')
        match = ID_PATTERN.search(str(target.get("onclick"))) if target else None
        check(match is not None and int(match[2]) == page, "隆基校招岗位 ID 或页号变化")
        assert match is not None
        cards.append((match[1], row))
    current = doc.select_one('input[name="currentPage"]')
    terminal = doc.select_one('input[name="lastPage"]')
    if current is None and terminal is None:
        return cards, None
    check(
        current is not None
        and terminal is not None
        and current.get("value") == str(page)
        and terminal.get("value") in {"true", "false"},
        "隆基校招分页字段不完整",
    )
    assert terminal is not None
    return cards, str(terminal.get("value"))


def _card_fields(row: Tag) -> tuple[str, str, str, str, str]:
    title = _text(row.select_one(".position_list-list-demo-title"))
    values = row.select(".position_list-first-row span")
    descriptions = row.select(".hidden .detailedInformation")
    check(
        bool(title) and len(values) >= 3 and len(descriptions) >= 2,
        "隆基校招卡片标题、机构或正文缺失",
    )
    return (
        title,
        _text(values[0]),
        _text(values[2]),
        _text(descriptions[0]),
        _text(descriptions[1]),
    )


class LongiLegacyCampus(Adapter):
    name = "longi-legacy-campus"
    host = "www.hotjob.cn"
    path = LIST_PATH + "?brandCode=1&recruitType=1"
    scope_description = "隆基旧版 Hotjob 公开校招；仅列表和详情均显示股份本级的岗位"

    async def harvest(self) -> None:
        session = cast(LegacySession, self.session)
        scope = Scope(name="campus-recruit-type-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        html = await session.page.content()
        while True:
            if page > 1:
                html = await session.request_html(_page_url(page))
            cards, terminal = _cards(html, page)
            check(bool(cards) and len(cards) <= PAGE_SIZE, "隆基校招目录空页或分页大小变化")
            list_evidence = session.last_evidence
            scope.evidence.append(list_evidence)
            page_ids: list[str] = []
            for job_id, row in cards:
                check(job_id not in seen, "隆基校招跨页岗位 ID 重复")
                seen.add(job_id)
                page_ids.append(job_id)
                scope.listed += 1
                scope.unique += 1
                title, unit, location, duties, requirements = _card_fields(row)
                check(bool(unit), "隆基校招招聘机构缺失")
                if unit != COMPANY:
                    scope.skipped_out_of_scope += 1
                    continue
                try:
                    url = _detail_url(job_id, page)
                    detail_html = await session.request_html(url, detail=True)
                    doc = BeautifulSoup(detail_html, "html.parser")
                    detail_id = DETAIL_ID_PATTERN.search(detail_html)
                    detail_fields = doc.select(".detailedInformation")
                    detail_values = doc.select(".position_list-first-row span")
                    check(
                        detail_id is not None
                        and detail_id[1] == job_id
                        and DETAIL_TYPE_PATTERN.search(detail_html) is not None
                        and len(detail_values) >= 3
                        and len(detail_fields) >= 2
                        and _text(doc.select_one(".position_list-list-demo-title")) == title
                        and _text(detail_values[0]) == COMPANY
                        and _text(detail_values[2]) == location
                        and _compact(_text(detail_fields[0])) == _compact(duties)
                        and _compact(_text(detail_fields[1])) == _compact(requirements),
                        "隆基校招详情身份、机构或正文与目录不一致",
                    )
                    job = self.job(
                        job_id,
                        title=title,
                        unit=COMPANY,
                        batch="校园招聘",
                        location=location,
                        duties=duties,
                        requirements=requirements,
                        source_url=url,
                        field_sources={
                            "unit": "旧版列表单位 + 公开详情单位均为股份本级",
                            "duties": "岗位卡片隐藏区工作描述 + 详情复核",
                            "requirements": "岗位卡片隐藏区职位要求 + 详情复核",
                            "location": "列表和详情工作地点",
                            "published": "仅相对更新时间；不作为发布日期",
                        },
                    )
                    job.evidence = [list_evidence, session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, job_id)
            if terminal == "true":
                scope.expected = len(seen)
                scope.terminal = True
                break
            if terminal is None:
                check(page > 1 and len(cards) < PAGE_SIZE, "隆基校招分页末页证据不足")
                repeat_html = await session.request_html(_page_url(page + 1))
                repeated, repeat_terminal = _cards(repeat_html, page)
                check(
                    repeat_terminal is None and [x[0] for x in repeated] == page_ids,
                    "隆基校招分页末端重复校验失败",
                )
                scope.evidence.append(session.last_evidence)
                scope.expected = len(seen)
                scope.terminal = True
                break
            check(terminal == "false" and len(cards) == PAGE_SIZE, "隆基校招未到末页却少于整页")
            page += 1
