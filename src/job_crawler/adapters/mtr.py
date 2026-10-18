"""MTR graduate programmes reconciled with their public Taleo announcement."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ENTRY = "https://www.mtr.com.hk/graduate-development-programme/index.php"
HKT = ZoneInfo("Asia/Hong_Kong")


def words(value: str | Tag) -> str:
    return " ".join(text(value).split())


def name_key(value: str) -> str:
    return words(value).removesuffix(" Programme").replace(" & ", " and ").casefold()


@dataclass
class Programme:
    key: str
    title: str
    body: str


@dataclass
class Campaign:
    year: str
    number: str
    announcement_url: str
    start: datetime
    end: datetime
    experience: str
    programmes: list[Programme]


def campaign(html: str) -> Campaign:
    document = BeautifulSoup(html, "html.parser")
    banners = document.select('img[alt^="Graduate Recruitment "]')
    check(len(banners) == 1, "港铁毕业生项目年份标识缺失或重复")
    match = re.fullmatch(r"Graduate Recruitment (\d{4})", str(banners[0]["alt"]))
    check(match is not None, "港铁毕业生项目年份格式变化")
    assert match is not None
    year = match[1]
    counts = document.find_all(string=re.compile(r"^\s*\d+ different programmes available\s*$"))
    check(len(counts) == 1, "港铁计划总数声明缺失或重复")
    expected = int(str(counts[0]).split()[0])
    buttons = document.select('#sectionOpportunities a[data-bs-toggle="modal"][data-bs-target]')
    modals = document.select(".opportunities-modal")
    check(
        expected > 0 and len(buttons) == len(modals) == expected, "港铁计划按钮、正文或总数不一致"
    )
    keys: set[str] = set()
    names: set[str] = set()
    programmes = []
    for button in buttons:
        target = str(button["data-bs-target"])
        check(re.fullmatch(r"#modal\d+", target) is not None, "港铁计划目标ID变化")
        key, title = target[1:], words(button)
        check(
            key not in keys and bool(title) and name_key(title) not in names, "港铁计划ID或名称重复"
        )
        bodies = [modal for modal in modals if modal.get("id") == key]
        check(len(bodies) == 1, "港铁计划缺少关联正文")
        keys.add(key)
        names.add(name_key(title))
        programmes.append(Programme(key, title, str(bodies[0])))
    check(keys == {str(modal.get("id")) for modal in modals}, "港铁存在未关联计划正文")

    application = document.select_one("#sectionApplication")
    check(application is not None, "港铁申请时段缺失")
    assert application is not None
    # Maintenance dates are not the application closing date.
    application_copy = BeautifulSoup(str(application), "html.parser")
    for remark in application_copy.select(".application-remark"):
        remark.decompose()
    period = re.search(
        r"from (\d{1,2} [A-Za-z]+ \d{4}) \((\d{2}:\d{2}) HKT\) to "
        r"(\d{1,2} [A-Za-z]+ \d{4}) \((\d{2}:\d{2}) HKT\)",
        words(str(application_copy)),
    )
    check(period is not None, "港铁申请时段或时区格式变化")
    assert period is not None
    start = datetime.strptime(period[1] + " " + period[2], "%d %B %Y %H:%M").replace(tzinfo=HKT)
    end = datetime.strptime(period[3] + " " + period[4], "%d %B %Y %H:%M").replace(tzinfo=HKT)
    check(start < end, "港铁申请起止日期矛盾")
    targets = {
        urljoin(ENTRY, str(a["href"]))
        for a in document.select("a[href]")
        if words(a) == "Apply Now"
    }
    check(len(targets) == 1, "港铁项目申请公告链接缺失或不一致")
    url = targets.pop()
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    check(
        parts.scheme == "https"
        and parts.netloc == "careers.mtr.com.hk"
        and parts.path == "/careersection/mtr_graduates_apply/jobdetail.ftl"
        and set(query) == {"job", "lang"}
        and query["lang"] == ["en"]
        and len(query["job"]) == 1
        and re.fullmatch(r"[A-Z0-9]{8}", query["job"][0]) is not None,
        "港铁公开招聘公告链接或ID变化",
    )
    faqs = [
        li
        for li in document.select("#sectionFAQs li")
        if "Do you hire graduates with some work experience?" in words(li.select_one("h3") or "")
    ]
    check(len(faqs) == 1, "港铁公共毕业生经验资格缺失")
    experience = words(faqs[0].select_one("p") or "")
    check(
        "recent graduates with not more than 3 years' work experience" in experience,
        "港铁公共毕业生资格范围变化",
    )
    return Campaign(year, query["job"][0], url, start, end, experience, programmes)


def taleo_field(document: BeautifulSoup, label: str) -> str:
    labels = [node for node in document.select("span.subtitle") if words(node) == label]
    check(len(labels) == 1, "港铁公告字段缺失或重复：" + label)
    container = labels[0].find_parent("div", class_="contentlinepanel")
    check(container is not None, "港铁公告字段容器变化：" + label)
    assert container is not None
    values = container.select(":scope > span.text")
    check(len(values) == 1 and bool(words(values[0])), "港铁公告字段值缺失：" + label)
    return words(values[0])


def announcement(html: str, project: Campaign) -> tuple[str, str, str]:
    document = BeautifulSoup(html, "html.parser")
    title = document.select_one('[id="requisitionDescriptionInterface.reqTitleLinkAction.row1"]')
    check(
        words(title or "") == project.year + " Graduate Recruitment", "港铁公告项目年份或标题错配"
    )
    check(taleo_field(document, "Job Number:") == project.number, "港铁公告ID错配")
    check(
        taleo_field(document, "Job") == "Graduates"
        and taleo_field(document, "Schedule") == "Full-time",
        "港铁公告不是全职毕业生招聘",
    )
    published = datetime.strptime(
        taleo_field(document, "Job Posting"), "%d/%b/%y, %I:%M:%S %p"
    ).replace(tzinfo=HKT)
    deadline = datetime.strptime(
        taleo_field(document, "Closing Date"), "%d/%b/%y, %I:%M:%S %p"
    ).replace(tzinfo=HKT)
    check(
        deadline.replace(second=0) == project.end and published <= deadline,
        "港铁官网与公告截止时间不一致",
    )
    names = [
        words(p).removeprefix("•").strip() for p in document.select("p") if words(p).startswith("•")
    ]
    check(
        len(names) == len(project.programmes)
        and {name_key(name) for name in names} == {name_key(p.title) for p in project.programmes},
        "港铁公告计划集合与官网不一致",
    )
    check(
        any(a.get("href") == ENTRY for a in document.select("a[href]")), "港铁公告缺少官网项目关联"
    )
    qualifications = [
        words(p) for p in document.select("p") if words(p).startswith("Regardless of races,")
    ]
    check(
        len(qualifications) == 1
        and "final-year university students and recent graduates" in qualifications[0],
        "港铁公告公共资格缺失",
    )
    return published.isoformat(sep=" "), deadline.isoformat(sep=" "), qualifications[0]


def programme_fields(programme: Programme) -> tuple[str, str, str]:
    document = BeautifulSoup(programme.body, "html.parser")
    body = document.select_one(".modal-body")
    check(body is not None, "港铁计划正文容器缺失")
    assert body is not None
    check(
        not body.select("img,a[href],iframe,object,embed,table"), "港铁计划正文含未处理附件或结构"
    )
    heading = words(body.select_one("h3") or "")
    match = re.fullmatch(
        r"(Corporate General Management|Functional Professional Expertise) [–-] (.+) Programme",
        heading,
    )
    check(match is not None, "港铁计划完整标题格式变化")
    assert match is not None
    canonical = re.sub(r"\s*\([^)]*\)", "", match[2])
    check(name_key(canonical) == name_key(programme.title), "港铁计划按钮与正文标题错配")
    sections: list[list[str]] = [[], []]
    split = False
    for node in body.children:
        if not isinstance(node, Tag) or node.name in {"h3", "br"}:
            continue
        check(node.name in {"p", "ul", "ol"}, "港铁计划出现未知正文章节")
        value = text(node)
        if words(node) == "We are looking for:":
            check(not split, "港铁计划资格标题重复")
            split = True
        elif value:
            sections[int(split)].append(value)
    check(split and all(sections), "港铁计划培养内容或资格缺失")
    return match[1], "\n".join(sections[0]), "\n".join(sections[1])


class MtrGraduate(Adapter):
    name = "mtr-graduate"
    host = "www.mtr.com.hk"
    path = "/graduate-development-programme/index.php"
    scope_description = "港铁官网完整毕业生发展计划及同项目Taleo公开全职公告；按独立计划展开"

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        html = await browser.page.content()
        project = campaign(html)
        page_evidence = browser.snapshot("mtr-graduate-campaign", html)
        notice_scope = Scope(
            name="mtr-graduate-announcement", unit="公告", expected=1, listed=1, unique=1
        )
        programme_scope = Scope(
            name="mtr-graduate-programmes",
            expected=len(project.programmes),
            listed=len(project.programmes),
            unique=len(project.programmes),
        )
        self.result.scopes.extend([notice_scope, programme_scope])
        await self.session.open(project.announcement_url)
        notice_html = await browser.page.content()
        notice_evidence = browser.snapshot("mtr-graduate-announcement", notice_html)
        published, deadline, qualification = announcement(notice_html, project)
        notice_scope.evidence.extend([page_evidence, notice_evidence])
        notice_scope.details = 1
        notice_scope.terminal = True
        programme_scope.evidence.extend([page_evidence, notice_evidence])
        for programme in project.programmes:
            key = project.number + ":" + programme.key
            try:
                job = self.job(
                    key,
                    title=programme.title,
                    source_url=ENTRY + "#" + programme.key,
                    apply_url=project.announcement_url,
                    batch=project.year + " Graduate Recruitment",
                    published=published,
                    deadline=deadline,
                )
                job.evidence = [page_evidence, notice_evidence]
                fingerprint = {
                    "body": programme.body,
                    "published": published,
                    "deadline": deadline,
                    "qualification": qualification,
                    "experience": project.experience,
                    "title": programme.title,
                }
                reused = self.before_detail(
                    "programme:" + key, fingerprint, programme_scope, job, evidence=page_evidence
                )
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                category, job.duties, requirements = programme_fields(programme)
                job.category_raw = category
                job.requirements = (
                    requirements
                    + "\n项目公共资格（公告及官网FAQ）：\n"
                    + qualification
                    + "\n"
                    + project.experience
                )
                job.field_sources = {
                    "duties": "官网计划modal：We are looking for之前的培养职责",
                    "requirements": "官网计划modal资格、Taleo公共资格与官网经验FAQ",
                    "published": "Taleo Job Posting，HKT；不是报名开始时间",
                    "deadline": "Taleo Closing Date，HKT；与官网申请截止核对到分钟",
                    "education": "source_missing:未提供独立最低学历字段，保留源资格原文",
                    "location": "source_missing:未明确列出工作地点；不使用宣讲地点或轮岗可能性",
                    "address": "source_missing:未提供详细工作地址",
                    "apply_url": "官网链接的Taleo公开招聘描述；未投递",
                }
                self.result.jobs.append(job)
                programme_scope.details += 1
                self.remember("programme:" + key, fingerprint, [job])
            except Exception as exc:
                self.error(exc, key)
        programme_scope.terminal = True
