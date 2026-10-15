"""Zhejiang transport group's 23 public 2027 campus announcement catalogs."""

import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


@dataclass(frozen=True)
class Notice:
    needs_id: str
    announce_id: str
    planned_hires: int


def notices_from_article(html: str, expected: int) -> list[Notice]:
    soup = BeautifulSoup(html, "html.parser")
    check(
        "2027届" in soup.get_text() and "浙江省交通投资集团有限公司" in soup.get_text(),
        "浙江交投公告主体或届别改变",
    )
    tables = [table for table in soup.select("table") if "PC端链接" in table.get_text()]
    check(len(tables) == 1, "浙江交投公告岗位链接表缺失或重复")
    result: list[Notice] = []
    previous: list[str] = []
    for row in tables[0].select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        links = {
            anchor.get_text(" ", strip=True): str(anchor.get("href") or "")
            for anchor in row.select("a[href]")
        }
        if "PC端链接" not in links:
            if cells:
                previous = cells
            continue
        pc = links["PC端链接"]
        mobile = links.get("移动端链接", "")
        match = re.fullmatch(r"https://dhr\.cncico\.com:18443/noticeDetail/(\d+)", pc)
        fragment = urlsplit(mobile).fragment
        mobile_id = parse_qs(fragment.partition("?")[2]).get("id", [""])[0]
        check(match is not None and mobile_id.isdigit(), "浙江交投公告 PC/移动链接无效")
        assert match is not None
        check(bool(previous) and previous[-1].isdigit(), "浙江交投公告计划人数缺失")
        check(len(previous) >= 2, "浙江交投公告单位名称缺失")
        result.append(Notice(match.group(1), mobile_id, int(previous[-1])))
    check(len(result) == expected, "浙江交投公告成员单位数量变化")
    check(
        len({n.needs_id for n in result}) == expected
        and len({n.announce_id for n in result}) == expected,
        "浙江交投公告链接 ID 重复",
    )
    return result


def announcement_job_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    for anchor in soup.select('a[href*="/postDetail/"]'):
        match = re.fullmatch(
            r"https://dhr\.cncico\.com:18443/postDetail/(\d+)", str(anchor.get("href") or "")
        )
        check(match is not None, "浙江交投公告逐岗链接结构改变")
        assert match is not None
        ids.append(match.group(1))
    check(bool(ids) and len(ids) == len(set(ids)), "浙江交投公告逐岗链接为空或重复")
    return set(ids)


class Zjjt2027(Adapter):
    name = "zjjt-2027-campus"
    host = "jt.hzshyy.com"
    path = "/content/82659"
    ready_endpoints = ("/front/content/view/82659",)
    scope_description = "浙江交通集团2027届总部管培生及22家成员单位公开校招公告全部岗位"
    api = "https://dhr.cncico.com:18443/api/cicoms-cicohr-personnel/recruitannounce"

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        group_html = await browser.request_html(f"https://{self.host}/content/82659")
        group_evidence = self.session.last_evidence
        group = notices_from_article(group_html, 22)
        trainee_html = await browser.request_html(f"https://{self.host}/content/82696")
        trainee_evidence = self.session.last_evidence
        trainee = notices_from_article(trainee_html, 1)
        check(all(n.planned_hires > 0 for n in group + trainee), "浙江交投官方招聘计划人数无效")
        notices = [(notice, group_evidence) for notice in group]
        notices.extend((notice, trainee_evidence) for notice in trainee)
        await self.session.open(
            f"https://dhr.cncico.com/#/notice/detail?id={notices[0][0].announce_id}",
            ready_endpoints=(f"{self.api}/detail?id=", f"{self.api}/get-needs-detail?"),
        )
        for notice, article_evidence in notices:
            scope = Scope(name=f"announce-{notice.announce_id}")
            scope.evidence.append(article_evidence)
            self.result.scopes.append(scope)
            try:
                response = await browser.request(
                    query(f"{self.api}/detail", id=notice.announce_id),
                    detail=True,
                    credentials="omit",
                )
                check(
                    response.get("code") == 200 and response.get("success") is True,
                    "浙江交投公告详情业务失败",
                )
                announcement = response["data"]
                check(
                    str(announcement["id"]) == notice.announce_id
                    and str(announcement["needsId"]) == notice.needs_id,
                    "浙江交投公告 PC/移动身份不一致",
                )
                announce_title = text(announcement["announceTitle"])
                check(
                    announcement.get("status") == 2
                    and announcement.get("isDeleted") == 0
                    and "2027届" in announce_title
                    and ("校园招聘" in announce_title or "管理培训生招聘" in announce_title),
                    "浙江交投公告不是开放的 2027 正式校招",
                )
                publish = text(announcement.get("publishDate"))
                check(bool(publish), "浙江交投公告发布日期缺失")
                announcement_evidence = self.session.last_evidence
                ids = announcement_job_ids(announcement["announceContent"])
                scope.expected = len(ids)
                response = await browser.request(
                    query(f"{self.api}/get-needs-detail", announceId=notice.announce_id),
                    detail=True,
                    credentials="omit",
                )
                check(
                    response.get("code") == 200 and response.get("success") is True,
                    "浙江交投公告岗位目录业务失败",
                )
                rows = response["data"]
                check(isinstance(rows, list), "浙江交投公告岗位目录不是数组")
                list_evidence = self.session.last_evidence
                seen: set[str] = set()
                fresh = self.add_page(scope, rows, seen, lambda row: str(row["id"]))
                check(seen == ids, "浙江交投公告表格岗位与公开接口目录不一致")
                check(
                    sum(int(row["recruitNum"]) for row in fresh) == notice.planned_hires,
                    "浙江交投公告计划人数与逐岗招聘人数不一致",
                )
                for row in fresh:
                    key = str(row["id"])
                    try:
                        check(str(row["needsId"]) == notice.needs_id, "浙江交投岗位归属公告错误")
                        check(
                            row.get("status") == 1 and row.get("isDeleted") == 0,
                            "浙江交投公告包含非公开岗位",
                        )
                        mode = text(row.get("recruitModeName"))
                        if mode == "面向集团内部招聘":
                            scope.skipped_out_of_scope += 1
                            continue
                        check(
                            mode in {"面向集团外部招聘", "面向集团内外部招聘"},
                            "浙江交投公告招聘方式改变",
                        )
                        check(
                            bool(text(row.get("postName")))
                            and bool(text(row.get("postResponsibility")))
                            and bool(text(row.get("postQualification"))),
                            "浙江交投岗位正文缺失",
                        )
                        member = text(row.get("memberName"))
                        org = text(row.get("reportOrgName"))
                        unit = " / ".join(dict.fromkeys(v for v in (member, org) if v))
                        job = self.job(
                            key,
                            title=text(row["postName"]),
                            batch=text(announcement["announceTitle"]),
                            source_url=f"https://dhr.cncico.com:18443/postDetail/{key}",
                            apply_url=f"https://dhr.cncico.com:18443/postDetail/{key}",
                            unit=unit,
                            location=text(row.get("workLocation")),
                            address=text(row.get("workLocationDetail")),
                            education=text(row.get("eduRequireName")),
                            category_raw=text(row.get("postCategoryName")),
                            duties=text(row["postResponsibility"]),
                            requirements=text(row["postQualification"]),
                            published=publish,
                            work_type="实习" if "实习" in text(row["postName"]) else "校招",
                            field_sources={
                                "published": "recruitannounce/detail.data.publishDate；公告发布日期",
                                "deadline": "source_missing",
                                "unit": "get-needs-detail.data[].memberName/reportOrgName 原层级",
                                "duties": "get-needs-detail.data[].postResponsibility",
                                "requirements": "get-needs-detail.data[].postQualification",
                            },
                        )
                        job.evidence = [article_evidence, announcement_evidence, list_evidence]
                        self.result.jobs.append(job)
                        scope.details += 1
                    except Exception as exc:
                        self.error(exc, key)
                scope.terminal = not any(issue.job_key in seen for issue in self.result.issues)
            except Exception as exc:
                self.error(exc, notice.announce_id)
