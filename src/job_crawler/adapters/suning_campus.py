"""Suning.com's public 1200 graduate program catalog."""

from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

ROOT = "https://campus.suning.cn"
PATH = "/rps-campus/ftl/campus/managePlan.htm?type=manage"


def catalog(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    check("苏宁易购" in soup.get_text(" ", strip=True), "苏宁校园页主体改变")
    form = soup.select_one("form#form")
    check(
        form is not None and form.select_one('input[name="type"][value="manage"]') is not None,
        "苏宁校园项目筛选改变",
    )
    check(not soup.select(".pagination,.pager,.page-list,.pages"), "苏宁校园页新增未处理分页")
    rows: list[dict[str, str]] = []
    for anchor in soup.select("a.post-link[href]"):
        path = urlsplit(urljoin(ROOT, str(anchor["href"])))
        ids = parse_qs(path.query).get("poId", [])
        check(
            path.hostname == "campus.suning.cn"
            and path.path == "/rps-campus/ftl/campus/managePositionDetail.htm"
            and len(ids) == 1
            and ids[0].isdigit(),
            "苏宁校园职位链接身份改变",
        )
        card = anchor.find_parent(class_="post-th")
        check(card is not None, "苏宁校园职位卡结构改变")
        assert card is not None
        title = text(anchor.get_text(" ", strip=True))
        place_node = card.select_one(".th-2")
        degree_node = card.select_one(".th-3")
        location = text(place_node.get_text(" ", strip=True)) if place_node is not None else ""
        education = text(degree_node.get_text(" ", strip=True)) if degree_node is not None else ""
        check(
            bool(title and location and education) and "实习" not in title, "苏宁校园职位摘要不完整"
        )
        rows.append(
            {
                "id": ids[0],
                "title": title,
                "location": location,
                "education": education,
                "url": urljoin(ROOT, str(anchor["href"])),
            }
        )
    check(bool(rows) and len({row["id"] for row in rows}) == len(rows), "苏宁校园目录为空或ID重复")
    return rows


def detail(html: str, row: dict[str, str]) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".section-title")
    check(
        title is not None and text(title.get_text(" ", strip=True)) == row["title"],
        "苏宁详情与目录标题不一致",
    )
    check("苏宁易购" in soup.get_text(" ", strip=True), "苏宁详情主体改变")
    selector = soup.select_one('input[id="poType"]')
    check(selector is not None and selector.get("value") == "6", "苏宁详情不再属于校园1200项目")
    table = soup.select_one(".section-table")
    check(table is not None, "苏宁详情基本字段缺失")
    assert table is not None
    fields: dict[str, str] = {}
    for cell in table.select("th"):
        label = text(cell.get_text(" ", strip=True)).rstrip("：")
        sibling = cell.find_next_sibling("td")
        if sibling is not None:
            degree = sibling.select_one("#degreeText") if label == "学历要求" else None
            fields[label] = text((degree or sibling).get_text(" ", strip=True))
    check(fields.get("工作性质") == "全职", "苏宁详情混入非正式岗位")
    check(fields.get("工作地点") == row["location"], "苏宁详情地点与列表不一致")
    check(fields.get("学历要求") == row["education"], "苏宁详情学历与列表不一致")
    body = soup.select(".section-detail.clearfix")
    check(len(body) == 1, "苏宁职位正文区域缺失")
    captions = body[0].select(".caption")
    check(len(captions) == 2, "苏宁职责与任职章节缺失")
    labels = [text(node.get_text(" ", strip=True)) for node in captions]
    check(labels == ["岗位职责：", "任职要求："], "苏宁正文栏目顺序变化")
    paragraphs = [node.find_next_sibling("p") for node in captions]
    check(
        all(node is not None and text(node.get_text(" ", strip=True)) for node in paragraphs),
        "苏宁职责或要求为空",
    )
    assert paragraphs[0] is not None and paragraphs[1] is not None
    return {
        "category_raw": fields.get("职位类别", ""),
        "duties": paragraphs[0].get_text("\n", strip=True),
        "requirements": paragraphs[1].get_text("\n", strip=True),
    }


class SuningCampus(Adapter):
    name = "suning-1200-campus"
    host = "campus.suning.cn"
    path = PATH
    scope_description = "苏宁易购官网所链 1200 校园招聘全部公开岗位；不含苏宁置业或金融独立招聘"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "苏宁校园目录未就绪")
        rows = catalog(await session.page.content())
        list_evidence = session.last_evidence
        scope = Scope(name="suning-1200-all", expected=len(rows))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["id"]):
            try:
                listing = self.job(row["id"], title=row["title"], source_url=row["url"])
                listing.evidence = [list_evidence]
                reused = self.before_detail(
                    f"job:{row['id']}", row, scope, listing, evidence=list_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                await session.open(row["url"])
                html = await session.page.content()
                session.snapshot(f"suning-1200-{row['id']}", html)
                values = detail(html, row)
                job = self.job(
                    row["id"],
                    title=row["title"],
                    source_url=row["url"],
                    unit="苏宁易购",
                    work_type="校招",
                    location=row["location"],
                    education=row["education"],
                    **values,
                    field_sources={
                        "unit": "苏宁易购官网所链专属校园门户",
                        "location": "校园目录及逐岗详情.工作地点",
                        "education": "校园目录及逐岗详情.学历要求",
                        "duties": "逐岗详情.岗位职责",
                        "requirements": "逐岗详情.任职要求",
                        "published": "source_missing:校园详情无发布日期",
                        "deadline": "source_missing:校园详情无截止日期",
                    },
                )
                job.evidence = [list_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{row['id']}", row, [job])
            except Exception as exc:
                self.error(exc, row["id"])
                if isinstance(exc, CrawlError) and exc.code in {
                    "access_denied",
                    "request_budget",
                    "time_budget",
                }:
                    return
        scope.terminal = True
