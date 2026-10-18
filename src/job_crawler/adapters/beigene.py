"""BeOne China campus and global jobs; independent scopes and cache identities."""

import re
from typing import Any, cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import Moka
from job_crawler.adapters.platforms import check
from job_crawler.adapters.workday import WorkdayPublicJobs, recruitment_type, words
from job_crawler.models import Collection, Job, Scope
from job_crawler.transport import BrowserSession, CrawlError

BACKGROUND_LINKS = {
    "mailto:accommodationsus@beonemed.com",
    "mailto:medaffairsfellowship@beonemed.com",
    "https://beonemedicines.com/",
    "https://twitter.com/BeiGeneGlobal",
    "https://beonemedicines.com/privacy-policy",
    "https://www.moseeker.com/positions/index/cid/1266291",
    "https://cts.businesswire.com/ct/CT?id=smartlink&url=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Fbeigene&esheet=53903210&newsitemid=20240229874068&lan=en-US&anchor=LinkedIn&index=5&md5=5a874533b60f10b6daaace549b9543bc",
}


def block_lines(doc: BeautifulSoup) -> list[str]:
    # Joining every text node with a separator corrupts M<span>aster and 202<span>7.
    for node in list(doc.find_all(string=True)):
        node.replace_with(re.sub(r"\s+", " ", str(node)))
    for node in doc.select("p,li,div,h1,h2,h3,h4,h5,h6,br"):
        node.insert_before("\n")
        node.insert_after("\n")
    return [words(line) for line in doc.get_text().splitlines() if words(line)]


class Namespaced(Adapter):
    namespace = ""

    def job(self, key: str, **fields: Any) -> Job:
        return super().job(self.namespace + key, **fields)

    def before_detail(
        self,
        entity: str,
        listing: object,
        scope: Scope,
        listing_job: Job | None = None,
        *,
        evidence: str | None = None,
    ) -> list[Job] | None:
        return super().before_detail(
            self.namespace + entity, listing, scope, listing_job, evidence=evidence
        )

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        super().remember(self.namespace + entity, listing, jobs)


class BeigeneMoka(Namespaced, Moka):
    namespace = "moka:"
    org = "beigene"
    site_id = 98935
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"

    def verify_detail(self, listing: dict[str, Any], detail: dict[str, Any]) -> None:
        check(text(detail.get("title")) == text(listing.get("title")), "百济校园详情标题错配")
        check(detail.get("commitment") in {"全职", "实习", "兼职"}, "百济校园用工类型变化")
        check(detail.get("status") in {"open", "closed"}, "百济校园开放状态变化")
        doc = BeautifulSoup(detail.get("jobDescription") or "", "html.parser")
        check(len(doc.get_text(strip=True)) > 30, "百济校园详情正文缺失")
        check(not doc.select("a[href],img,iframe,object,embed,video"), "百济校园正文附件待核对")


class BeigeneWorkday(Namespaced, WorkdayPublicJobs):
    namespace = "workday:"
    tenant = "beigene"
    site = "BeiGene"
    host = "beigene.wd5.myworkdayjobs.com"
    path = "/en-US/BeiGene"
    ready_endpoints = ("/wday/cxs/beigene/BeiGene/jobs",)
    allow_locationless = True

    def detail_endpoint(self, row: dict[str, Any]) -> str:
        self.listing_key(row)
        return self.api + row["externalPath"]

    def scope_text(self, duties: str, requirements: str) -> str:
        return duties + "\n" + requirements

    def kind(self, title: str, requirements: str, time_type: str) -> str:
        content = words(requirements)
        if re.search(r"\bintern(?:ship)?\b|\bestagi[aá]ri[oa]\b", title, re.I):
            return "实习"
        if time_type == "Full time" and re.search(r"\bfellow\b", title, re.I):
            if re.search(r"recent pharmacy graduate\b", content, re.I) or re.search(
                r"Candidate should have completed .{1,200}\bby July 20\d{2}\b", content, re.I
            ):
                return "校招"
        return recruitment_type(title, content, time_type)

    def body(self, html: str) -> tuple[str, str]:
        doc = BeautifulSoup(html, "html.parser")
        check(not doc.select("img,iframe,object,embed,video"), "百济全球正文媒体待展开")
        check(
            all(a.get("href") in BACKGROUND_LINKS for a in doc.select("a[href]")),
            "百济全球新增正文链接待核对",
        )
        lines = block_lines(doc)
        # Remove only the observed corporate introduction and common benefits footer.
        lines = [
            line
            for line in lines
            if not re.match(r"(?:BeOne|BeiGene) continues to grow at a rapid pace", line)
        ]
        tails = [
            n
            for n, line in enumerate(lines)
            if re.fullmatch(r"(?:BeOne |BeiGene )?Global Competencies:?", line)
            or line.startswith("Salary Range:")
        ]
        if tails:
            lines = lines[: min(tails)]
        check(len("\n".join(lines)) > 100, "百济全球正文缺失")
        duties: list[str] = []
        requirements: list[str] = []
        current = duties
        boundary = False
        for line in lines:
            heading = line.rstrip(":：")
            if re.fullmatch(
                r"(?:Education(?: and Experience)? Required|(?:Required |Preferred |Other )?Qualifications|Qualification Required|(?:Minimum |Key |Job )?Requirements|Computer Skills|Travel|Preferred)",
                heading,
                re.I,
            ):
                current = requirements
                boundary = True
            elif re.fullmatch(
                r"General Description(?:\s*/\s*Scope of Responsibilities)?|Job Description|Essential Functions of the Job|Responsibilities(?: and essential functions of the job)?|Supervisory Responsibilities",
                heading,
                re.I,
            ):
                current = duties
            current.append(line)
        if not boundary:
            return "", "\n".join(lines)
        return "\n".join(duties), "\n".join(requirements)


class BeigeneMoseeker(Namespaced):
    namespace = "moseeker:"
    host = "www.moseeker.com"
    path = "/positions/index/cid/1266291"

    def catalog(self, html: str) -> tuple[int, list[dict[str, str]]]:
        doc = BeautifulSoup(html, "html.parser")
        totals = re.findall(r"\btotalNum:\s*(\d+)", html)
        check(len(totals) == 1 and 0 < int(totals[0]) <= 5000, "百济仟寻目录总数缺失或超预算")
        rows = []
        for card in doc.select("a.PositionList__job-item"):
            href = card.get("href", "")
            check(isinstance(href, str), "百济仟寻岗位路径类型变化")
            assert isinstance(href, str)
            match = re.fullmatch(r"/position/index/pid/(\d+)", href)
            title = card.select_one(".job-title")
            check(match is not None and title is not None, "百济仟寻岗位ID或标题缺失")
            assert match is not None and title is not None
            check(card.get("title") == "百济神州", "仟寻列表混入其他公司")
            rows.append(
                {
                    "id": match[1],
                    "title": words(title.get_text()),
                    "url": urljoin(f"https://{self.host}", href),
                }
            )
        return int(totals[0]), rows

    def parse_detail(self, html: str, row: dict[str, str]) -> dict[str, str]:
        doc = BeautifulSoup(html, "html.parser")
        ids = re.findall(r"\bpositionId:\s*(\d+)", html)
        companies = re.findall(r"\bcompanyId:\s*['\"](\d+)['\"]", html)
        title = doc.select_one("h2.postion-title")
        check(ids == [row["id"]] and companies == ["1266291"], "百济仟寻详情身份错配")
        check(title is not None and words(title.get_text()) == row["title"], "百济仟寻详情标题错配")
        check(bool(doc.select('a[href="/company/1266291"]')), "百济仟寻公司归属缺失")
        check(bool(doc.select("a.apply-button")), "百济仟寻详情公开投递状态变化")
        sections: dict[str, str] = {}
        for article in doc.select("article.position-detail"):
            heading = article.select_one("h3.title")
            body = article.select_one("section.qx-postion-panel-body")
            check(heading is not None and body is not None, "百济仟寻正文结构变化")
            assert heading is not None and body is not None
            label = words(heading.get_text())
            check(
                label in {"职位描述", "任职条件"} and label not in sections, "百济仟寻正文分节变化"
            )
            check(
                not body.select("a[href],img,iframe,object,embed,video"), "百济仟寻正文附件待核对"
            )
            sections[label] = "\n".join(block_lines(BeautifulSoup(str(body), "html.parser")))
        check(bool(sections.get("职位描述")), "百济仟寻职责正文为空")
        fields = {}
        for item in doc.select(".postion-attributes-item"):
            label, sep, value = words(item.get_text()).partition("：")
            check(bool(sep) and label not in fields, "百济仟寻属性结构变化")
            fields[label] = value
        check(fields.get("招聘类型") in {"校招", "社招"}, "百济仟寻招聘类型变化")
        check(fields.get("工作性质") in {"全职", "实习", "兼职", "合同工"}, "百济仟寻用工类型变化")
        location = doc.select_one(".qx-company-header-body .position-text")
        team = doc.select_one(".qx-company-header-body .is-team")
        check(location is not None and "/" in location.get_text(), "百济仟寻地点结构变化")
        assert location is not None
        work_type = fields["工作性质"] if fields["工作性质"] != "全职" else fields["招聘类型"]
        if re.search(r"实习|\bintern(?:ship)?\b", row["title"], re.I):
            work_type = "实习"
        education = fields.get("学历要求", "")
        alternative = re.search(r"或本科教育学历，专业能力表现卓越", sections.get("任职条件", ""))
        if education == "博士" and alternative:
            # Keep the explicit conditional alternative for the shared eligibility resolver.
            education += "；" + alternative[0]
        return {
            "title": row["title"],
            "source_url": row["url"],
            "work_type": work_type,
            "unit": words(team.get_text()).partition("·")[2].strip() if team else "",
            "location": words(location.get_text()).split("/", 1)[1].strip(),
            "education": education,
            "duties": sections["职位描述"],
            "requirements": sections.get("任职条件", ""),
        }

    async def harvest(self) -> None:
        browser = cast(BrowserSession, self.session)
        entry = f"https://{self.host}{self.path}"
        scope = Scope(name="moseeker-beigene-1266291-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        first: list[dict[str, str]] = []
        for page in range(1, 280):
            url = (
                entry
                if page == 1
                else entry + f"?city=&custom=&keyword=&occupation=&pageNum={page}"
            )
            total, rows = self.catalog(await browser.request_html(url))
            if page == 1:
                scope.expected = total
                first = rows
            check(total == scope.expected, "百济仟寻目录总数变化")
            check(len(rows) == min(18, total - (page - 1) * 18), "百济仟寻目录短页")
            evidence = self.session.last_evidence
            for row in self.add_page(scope, rows, seen, lambda x: x["id"]):
                try:
                    reused = self.before_detail("job:" + row["id"], row, scope, evidence=evidence)
                    if reused is not None:
                        self.result.jobs.extend(reused)
                        continue
                    fields = self.parse_detail(await browser.request_html(row["url"]), row)
                    job = self.job(
                        row["id"],
                        **fields,
                        field_sources={
                            "published": "source_missing:仅有更新日期，不代替发布时间",
                            "deadline": "source_missing:未提供截止日期",
                            "work_type": "招聘类型/工作性质；实习优先排除",
                            "education": "学历要求原值；存在明确本科例外时并存其资格原文待公共层判断",
                            "duties": "职位描述section",
                            "requirements": "任职条件section；无内容时留空",
                            "location": "详情薪资/地点栏原值，不猜地址",
                            "unit": "页头所属团队，非推定法人",
                        },
                    )
                    job.evidence = [evidence, self.session.last_evidence]
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember("job:" + row["id"], row, [job])
                except Exception as exc:
                    self.error(exc, row["id"])
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if scope.unique == scope.expected:
                current_total, current_first = self.catalog(await browser.request_html(entry))
                check(
                    current_total == scope.expected and current_first == first,
                    "百济仟寻遍历期间目录变化",
                )
                scope.evidence.append(self.session.last_evidence)
                scope.terminal = True
                return
        raise ValueError("百济仟寻分页超预算")


class BeigeneRecruitment(Adapter):
    name = "beigene-campus-global"
    host = BeigeneMoka.host
    path = BeigeneMoka.path
    scope_description = "百济神州中国Moka应届目录、全球Workday与仟寻历史活动全目录；排除实习、社招及无明确应届资格项目"
    children: tuple[type[Adapter], ...] = (BeigeneMoka, BeigeneWorkday, BeigeneMoseeker)

    async def collect(self) -> Collection:
        if self.source.url != f"https://{self.host}{self.path}":
            self.error(CrawlError("entry_mismatch", "百济需使用已验证的98935应届生目录"))
            return self.result
        for child_type in self.children:
            source = self.source.model_copy(
                update={"url": f"https://{child_type.host}{child_type.path}"}
            )
            child = child_type(
                source, self.session, self.collected_at, self.as_of, incremental=self.incremental
            )
            collected = await child.collect()
            self.result.jobs.extend(collected.jobs)
            self.result.scopes.extend(collected.scopes)
            self.result.issues.extend(collected.issues)
            self.result.warnings.extend(collected.warnings)
        return self.result
