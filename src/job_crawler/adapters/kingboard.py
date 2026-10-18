"""Kingboard's official inline vacancy document and separate internship programme."""

import hashlib
import re
from typing import cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://www.kingboard.com"
CAREERS = ROOT + "/portal/list/index/id/80.html"
STUDENTS = ROOT + "/portal/list/index/id/35.html"
UNIT = "建滔覆铜板（深圳）有限公司"


def document(html: str, title: str) -> BeautifulSoup:
    doc = BeautifulSoup(html, "html.parser")
    main = doc.select("main")
    check(len(main) == 1, "建滔招聘主内容缺失或重复")
    nav = main[0].select(".nav-list")
    check(len(nav) == 1, "建滔招聘范围导航缺失")
    links = {
        a.get_text(strip=True): urljoin(ROOT, str(a["href"])) for a in nav[0].select("a[href]")
    }
    check(
        links
        == {
            "建滔招聘信息": CAREERS,
            "大学生学习计划": STUDENTS,
            "报名表格": ROOT + "/portal/enlist/index.html",
        }
        and len(nav[0].select("a[href]")) == 3,
        "建滔招聘出现新栏目或入口变化",
    )
    check(title in main[0].get_text(" ", strip=True), "建滔页面标题错配")
    check(not main[0].select(".pagination, .pager, [rel=next], iframe"), "建滔新增分页或外嵌目录")
    return doc


def catalog(html: str) -> list[dict[str, str]]:
    doc = document(html, "建滔招聘信息")
    containers = doc.select("main .investor-relations-container")
    check(len(containers) == 1, "建滔招聘文档容器变化")
    bodies = containers[0].select(".ir-content")
    check(len(bodies) == 1, "建滔招聘全文缺失或重复")
    body = bodies[0]
    check(
        not body.select("a, img, iframe, object, video, audio, table"),
        "建滔正文含未核验附件或新结构",
    )
    check(
        all(child.name in {"p", "style"} for child in body.find_all(recursive=False)),
        "建滔正文新增未解析分节",
    )
    lines = [p.get_text("", strip=True) for p in body.select(":scope > p")]
    lines = [line for line in lines if line]
    check(
        lines[:2] == [f"招聘企业全称：{UNIT}", "所属行业：制造业"],
        "建滔用人单位或正文开头变化",
    )
    check(sum(line.startswith("招聘企业全称：") for line in lines) == 1, "建滔新增用人单位")
    ends = [i for i, line in enumerate(lines) if line.startswith("公司地址：")]
    check(len(ends) == 1 and ends[0] == len(lines) - 4, "建滔正文末端不完整或新增内容")
    end = ends[0]
    check(
        lines[end + 1] == "联系人-联系电话（手机）-邮箱：" and lines[-1].endswith("@kingboard.com"),
        "建滔招聘联系方式闭合证据缺失",
    )
    starts = [i for i, line in enumerate(lines[:end]) if line.startswith("计划招用的岗位：")]
    check(len(starts) == 14 and starts[0] == 2, "建滔已验证14分节结构变化，须重新核验")
    rows = []
    descriptions: set[str] = set()
    for ordinal, (start, stop) in enumerate(zip(starts, [*starts[1:], end], strict=True), 1):
        title = lines[start].removeprefix("计划招用的岗位：").strip()
        section = lines[start + 1 : stop]
        check(
            bool(title) and len(section) >= 4 and section[0] == "岗位需求：",
            "建滔岗位标题或需求缺失",
        )
        check(section.count("岗位需求：") == 1, "建滔岗位需求重复或分节丢失")
        text = "\n".join(section[1:])
        check(text not in descriptions and len(text) > 25, "建滔重复或空岗位正文")
        descriptions.add(text)
        # No source job ID exists. Position plus unit/title preserves separate same-title sections.
        identity = hashlib.sha256(f"{UNIT}|{ordinal}|{title}".encode()).hexdigest()[:20]
        rows.append({"id": f"page80-{identity}", "title": title, "requirements": text})
    return rows


def internship(html: str) -> None:
    doc = document(html, "大学生学习计划")
    programs = doc.select("main .main-internship-program")
    check(len(programs) == 1, "建滔学生计划内容缺失或新增")
    program = programs[0]
    intro = program.select(".ip-A .content-text")
    check(
        len(intro) == 1
        and "大學生實習計劃" in intro[0].get_text()
        and "20個實習職位" in intro[0].get_text(),
        "建滔学生计划类型或名额形态变化",
    )
    fields: dict[str, str] = {}
    for item in program.select(".ip-list .item"):
        heading, value = item.select_one(".item-title"), item.select_one(".item-text")
        check(heading is not None and value is not None, "建滔学生计划字段缺失")
        assert heading is not None and value is not None
        key = heading.get_text(strip=True)
        check(key not in fields, "建滔学生计划字段重复")
        fields[key] = value.get_text(strip=True)
    check(
        set(fields) == {"申請資格", "實習日期", "實習地點", "費用"}
        and "全日制大專學生" in fields["申請資格"],
        "建滔学生计划资格或范围变化",
    )
    closing: list[str] = []
    for item in program.select(".ip-C .item"):
        heading = item.select_one(".item-title")
        check(heading is not None, "建滔学生报名信息标题缺失")
        assert heading is not None
        if heading.get_text(strip=True) == "截止日期":
            content = item.select_one(".content")
            check(content is not None, "建滔学生计划截止正文缺失")
            assert content is not None
            closing.append(content.get_text(strip=True))
    check(closing == ["截止報名 (已以電郵通知入選者)"], "建滔学生计划截止状态变化")
    check(
        not re.search(r"校園招聘|校园招聘|應屆畢業生|应届毕业生|正式招聘", program.get_text()),
        "建滔学生栏目出现新的正式招聘内容",
    )
    links = {urljoin(ROOT, str(a["href"])) for a in program.select("a[href]")}
    check(
        links
        == {
            ROOT + "/portal/enlist/index.html",
            ROOT + "/upload/portal/20211011/202110111432321055.xlsx",
        },
        "建滔学生计划新增链接或附件",
    )


class KingboardCareers(Adapter):
    name = "kingboard-careers"
    host = "www.kingboard.com"
    path = "/portal/list/index/id/80.html"
    scope_description = "建滔集团官网统一招聘信息全文；核对已截止暑期实习，限官方统一栏目"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name="kingboard-official-vacancies")
        self.result.scopes.append(scope)
        rows = catalog(await session.request_html(CAREERS))
        self.add_page(scope, rows, set(), lambda row: row["id"])
        for row in rows:
            self.result.jobs.append(
                self.job(
                    row["id"],
                    title=row["title"],
                    unit=UNIT,
                    source_url=CAREERS,
                    requirements=row["requirements"],
                    work_type="校招" if "应届毕业生" in row["requirements"] else "未明确校招",
                    field_sources={
                        "requirements": "官网对应计划招用的岗位分节；岗位需求及原始福利全文",
                        "duties": "来源没有独立职责分节，留空",
                        "published": "来源未提供",
                        "deadline": "来源未提供",
                        "location": "只有公司联系地址，不推定岗位工作地",
                        "source_key": "无源ID；目录80+单位+分节序号+标题，重排可能重新发现",
                    },
                )
            )
            scope.details += 1
        scope.expected = len(rows)
        scope.terminal = True
        student_scope = Scope(name="kingboard-student-programme", unit="项目")
        self.result.scopes.append(student_scope)
        internship(await session.request_html(STUDENTS))
        student_scope.expected = student_scope.listed = student_scope.unique = 1
        student_scope.skipped_out_of_scope = 1
        student_scope.evidence.append(session.last_evidence)
        student_scope.terminal = True
