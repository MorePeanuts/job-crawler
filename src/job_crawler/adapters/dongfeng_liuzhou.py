"""东风柳汽 2027 届专题静态完整岗位卡。"""

from collections import Counter
from typing import cast
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

EMPLOYER = "东风柳州汽车有限公司"
ANNOUNCEMENT = "https://career.hebut.edu.cn/correcruit/content/id/82020.html"
COUNTS = {"技术研发": 10, "智能制造": 15, "营销运营": 7, "职能管理": 4}


def positions(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("title")
    check(
        title is not None and "东风柳汽2027届校园招聘" in text(title.get_text()), "东风柳汽届别改变"
    )
    check(not soup.select(".pagination,.pager,.pages"), "东风柳汽岗位页出现分页")
    cards = soup.select(".job_table.job_cards .job-card")
    check(bool(cards), "东风柳汽岗位卡缺失")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    categories: Counter[str] = Counter()
    for card in cards:
        title_node = card.select_one(".job-card-title")
        category_node = card.select_one(".job-card-cat")
        education_node = card.select_one(".job-card-tag")
        city_node = card.select_one(".job-card-city .cell-city")
        body = card.select(".cell-collapse .cell-content")
        apply = card.select_one("a.job-apply[href]")
        check(
            all(
                node is not None
                for node in (title_node, category_node, education_node, city_node, apply)
            )
            and len(body) == 2,
            "东风柳汽岗位卡字段改变",
        )
        assert title_node and category_node and education_node and city_node and apply
        title_text = text(title_node.get_text(" ", strip=True))
        category = text(category_node.get_text(" ", strip=True))
        education = text(education_node.get_text(" ", strip=True))
        city = text(city_node.get_text(" ", strip=True))
        duties = text(body[0].get_text("\n", strip=True))
        requirements = text(body[1].get_text("\n", strip=True))
        link = str(apply["href"])
        check(
            bool(title_text)
            and title_text not in seen
            and category in COUNTS
            and education == "本科及以上"
            and city in {"柳州", "柳州/海外营销驻地", "全国营销驻地"}
            and bool(duties)
            and bool(requirements)
            and urlsplit(link).netloc == "www.liepin.com"
            and urlsplit(link).path.startswith("/lptjob/"),
            "东风柳汽岗位身份或内容不完整",
        )
        seen.add(title_text)
        categories[category] += 1
        result.append(
            {
                "title": title_text,
                "category": category,
                "education": education,
                "location": city,
                "duties": duties,
                "requirements": requirements,
            }
        )
    check(dict(categories) == COUNTS and len(result) == 36, "东风柳汽岗位类别或目录数量改变")
    return result


def verify_parent(html: str) -> None:
    body = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    check(
        EMPLOYER in body
        and "2027届" in body
        and "东风汽车集团股份有限公司持股75%" in body.replace(" ", ""),
        "东风柳汽高校公告未能证明届别或集团关系",
    )


class DongfengLiuzhou2027(Adapter):
    name = "dongfeng-liuzhou-2027"
    host = "xy.liepin.com"
    path = "/dflzqc/zhaopin.html"
    scope_description = "东风柳汽 2027 届官方专题 36 张静态岗位卡"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "东风柳汽岗位页未就绪")
        rows = positions(await session.page.content())
        catalog_evidence = self.session.last_evidence
        await self.session.open(ANNOUNCEMENT)
        check(session.page is not None, "东风柳汽高校主体公告未就绪")
        verify_parent(await session.page.content())
        relation_evidence = self.session.last_evidence
        scope = Scope(name="dongfeng-liuzhou-2027-cards", expected=len(rows))
        scope.evidence.extend((catalog_evidence, relation_evidence))
        self.result.scopes.append(scope)
        for row in self.add_page(scope, rows, set(), lambda item: item["title"]):
            try:
                job = self.job(
                    row["title"],
                    title=row["title"],
                    work_type="校招",
                    source_url=self.source.url,
                    unit=EMPLOYER,
                    location=(
                        "广西壮族自治区柳州市" if row["location"] == "柳州" else row["location"]
                    ),
                    education=row["education"],
                    duties=row["duties"],
                    requirements=row["requirements"],
                    field_sources={
                        "unit": "河北工大东风柳汽 2027 届公告及集团持股关系",
                        "title": "东风柳汽专题独立岗位卡标题",
                        "location": "岗位卡工作地址；柳州与高校公告广西柳州交叉核对",
                        "education": "岗位卡 学历标签",
                        "duties": "岗位卡 职责描述",
                        "requirements": "岗位卡 任职要求",
                        "published": "source_missing:专题未提供逐岗发布时间",
                        "deadline": "source_missing:专题未提供逐岗截止日期",
                    },
                )
                job.evidence = [catalog_evidence, relation_evidence]
                self.result.jobs.append(job)
                scope.details += 1
            except Exception as exc:
                self.error(exc, row["title"])
        scope.terminal = True
