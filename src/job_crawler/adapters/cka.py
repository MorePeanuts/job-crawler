"""CK Asset's official paginated, inline vacancy directory."""

import re
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://www.ckah.com/careers"


def words(value: str) -> str:
    return " ".join(value.split())


def page_number(link: str) -> int:
    parts = urlsplit(urljoin(ROOT, link))
    query = parse_qs(parts.query)
    check(
        parts.netloc == "www.ckah.com"
        and parts.path == "/careers"
        and not parts.fragment
        and set(query) == {"page"}
        and len(query["page"]) == 1
        and query["page"][0].isdigit(),
        "长江实业分页路径或筛选变化",
    )
    return int(query["page"][0])


def catalog(html: str, page: int) -> tuple[int, str, list[dict[str, str]]]:
    doc = BeautifulSoup(html, "html.parser")
    check("CK Asset Holdings Limited" in doc.get_text(" ", strip=True), "长江实业招聘主体缺失")
    sections = doc.select(".panel-section")
    check(len(sections) == 1, "长江实业目录区缺失或重复")
    section = sections[0]
    forms = section.select('form[action="/careers"]')
    check(len(forms) == 1, "长江实业筛选表结构变化")
    check(
        [x.get("value") for x in forms[0].select('select[name="tag_id"] option[selected]')]
        == ["All"],
        "长江实业目录存在部门筛选",
    )
    check(not forms[0].select('input[type="text"][value]'), "长江实业出现未验证搜索条件")
    pager = section.select_one("nav.pager")
    check(pager is not None, "长江实业分页或零目录形态未验证")
    assert pager is not None
    current = pager.select('a[aria-current="page"]')
    check(
        len(current) == 1 and page_number(str(current[0]["href"])) == page, "长江实业当前页码错配"
    )
    targets = [page_number(str(a["href"])) for a in pager.select("a[href]")]
    last = max(targets)
    check(0 < last < 100 and page <= last, "长江实业总页数无效或超预算")
    next_links = pager.select(".pager__item--next a[href]")
    check(len(next_links) == (1 if page < last else 0), "长江实业下一页与末页不符")
    next_url = urljoin(ROOT, str(next_links[0]["href"])) if next_links else ""
    if next_url:
        check(page_number(next_url) == page + 1, "长江实业下一页不连续")
    if page:
        previous = pager.select(".pager__item--previous a[href]")
        check(
            len(previous) == 1 and page_number(str(previous[0]["href"])) == page - 1,
            "长江实业前一页错配",
        )
    rows = []
    titles = section.select(".panel-title a[href]")
    bodies = section.select(".panel-collapse")
    check(
        len(titles) == len(bodies) and 0 < len(titles) <= 8 and (page == last or len(titles) == 8),
        "长江实业目录丢行或分页短页",
    )
    refs: set[str] = set()
    ids: set[str] = set()
    for title in titles:
        anchor = str(title["href"])
        match = re.fullmatch(r"#accordion-(\d+)-1", anchor)
        check(match is not None and bool(title.get_text(strip=True)), "长江实业岗位身份缺失")
        assert match is not None
        key = match[1]
        check(key not in ids, "长江实业同页重复岗位")
        ids.add(key)
        matches = section.select(anchor)
        check(len(matches) == 1, "长江实业标题正文关联失败")
        body = matches[0].select_one(".panel-body")
        check(
            body is not None and not body.select("a, img, iframe, object, video"),
            "长江实业正文缺失或含未展开链接媒体",
        )
        assert body is not None
        content = body.get_text("\n", strip=True)
        lines = content.splitlines()
        ref_match = re.fullmatch(r"Ref\.: ([A-Z0-9&-]+)", lines[0])
        check(ref_match is not None, "长江实业业务编号缺失")
        assert ref_match is not None
        ref = ref_match[1]
        check(ref not in refs, "长江实业同页业务编号重复")
        refs.add(ref)
        description = "\n".join(lines[1:])
        check(len(description) > 40, "长江实业岗位正文为空")
        duties, requirements = "", description
        if description.startswith("Responsibilities:\n"):
            check(description.count("\nRequirements:\n") == 1, "长江实业职责资格分节异常")
            duties, requirements = description.removeprefix("Responsibilities:\n").split(
                "\nRequirements:\n"
            )
        else:
            check(
                "Responsibilities:" not in description and "Requirements:" not in description,
                "长江实业新增正文分节需核对",
            )
        rows.append(
            {
                "id": key,
                "ref": ref,
                "title": words(title.get_text(" ", strip=True)),
                "duties": duties,
                "requirements": requirements,
                "url": (ROOT if page == 0 else f"{ROOT}?page={page}") + anchor,
            }
        )
    return last, next_url, rows


def recruitment_type(title: str, requirements: str) -> str:
    if re.search(r"\b(?:temporary|part[- ]time)\b", title, re.I):
        return "临时岗位"
    if re.search(r"\bintern(?:ship)?\b", title, re.I):
        return "实习"
    if re.search(r"\b(?:fresh|recent|new) graduates?\b", requirements, re.I):
        return "校招"
    return "未明确校招"


class CkaCareers(Adapter):
    name = "cka-careers"
    host = "www.ckah.com"
    path = "/careers"
    scope_description = "长江实业集团官网Careers全部部门与分页；仅明确应届，排除临时岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name="cka-official-careers")
        self.result.scopes.append(scope)
        url = ROOT
        last = None
        seen: set[str] = set()
        refs: set[str] = set()
        for page in range(100):
            html = await session.request_html(url)
            end, next_url, rows = catalog(html, page)
            if last is None:
                last = end
            check(end == last, "长江实业分页末页变化")
            fresh = self.add_page(scope, rows, seen, lambda r: r["id"])
            for row in fresh:
                check(row["ref"] not in refs, "长江实业跨页业务编号重复")
                refs.add(row["ref"])
                self.result.jobs.append(
                    self.job(
                        row["id"],
                        title=row["title"],
                        source_url=row["url"],
                        duties=row["duties"],
                        requirements=row["requirements"],
                        work_type=recruitment_type(row["title"], row["requirements"]),
                        field_sources={
                            "duties": "正文Responsibilities分节；无则空",
                            "requirements": "官网岗位内联正文/Requirements分节",
                            "published": "来源未提供",
                            "deadline": "来源未提供",
                            "work_type": "明确fresh graduates；临时岗位单独排除",
                        },
                    )
                )
                scope.details += 1
            if not next_url:
                check(page == last, "长江实业提前终止")
                scope.expected = scope.unique
                scope.terminal = True
                return
            url = next_url
        raise ValueError("长江实业目录超过100页预算")
