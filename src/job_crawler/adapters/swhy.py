"""SWHY's five officially linked campus portals, with isolated evidence and keys."""

import json
import re
from typing import Any, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.hotjob import Hotjob
from job_crawler.adapters.moka import Moka, sections
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession


class Branch(Adapter):
    prefix = ""
    deadline = ""

    def job(self, key: str, **fields: Any) -> Job:
        return super().job(f"{self.prefix}:{key}", **fields)

    def entity_key(self, entity: str) -> str:
        kind, separator, key = entity.partition(":")
        check(bool(separator) and kind == "job", "申万宏源增量对象类型改变")
        return f"{kind}:{self.prefix}:{key}"

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
            self.entity_key(entity),
            {"record": listing, "deadline": self.deadline},
            scope,
            listing_job,
            evidence=evidence,
        )

    def remember(self, entity: str, listing: object, jobs: list[Job]) -> None:
        super().remember(
            self.entity_key(entity), {"record": listing, "deadline": self.deadline}, jobs
        )


class Securities(Branch, Moka):
    prefix = "securities"
    org = "swhysc-job"
    site_id = 166086
    path = "/campus-recruitment/swhysc-job/166086#/jobs"
    deadline = ""
    deadline_evidence: list[str]

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        # The public job page supplies the year; the current official FAQ supplies the time.
        href = await session.page.evaluate(
            "() => document.querySelector('a[href*=\"#/job/\"]')?.href"
        )
        check(
            isinstance(href, str)
            and href.startswith(
                f"https://{self.host}/campus-recruitment/{self.org}/{self.site_id}#/job/"
            ),
            "申万宏源目录缺公开详情",
        )
        await session.open(href, ready_endpoints=("/api/outer/ats-apply/website/job",))
        body = BeautifulSoup(await session.page.content(), "html.parser").get_text("", strip=True)
        rule = re.search(
            r"2027届秋招允许\d{4}年\d{2}月\d{2}日至(\d{4})年(\d{2})月(\d{2})日内投递1次", body
        )
        check(
            rule is not None and "申万宏源证券有限公司" in body,
            "申万宏源当届公开申请日期或主体变化",
        )
        assert rule is not None
        self.deadline_evidence = [session.last_evidence]
        await session.open("https://app.mokahr.com/campus-recruitment/swhysc-job/148689")
        faq = BeautifulSoup(await session.page.content(), "html.parser").get_text("", strip=True)
        end = re.search(r"网申及测评完成时间最晚截至(\d{1,2})月(\d{1,2})日(\d{2}:\d{2})", faq)
        check(end is not None and "2027届校招" in faq, "申万宏源校招手册截止缺失")
        assert end is not None
        check(
            tuple(map(int, rule.groups()[1:])) == tuple(map(int, end.groups()[:2])),
            "申万宏源两处截止不一致",
        )
        self.deadline = f"{rule[1]}-{rule[2]}-{rule[3]} {end[3]}:00"
        self.deadline_evidence.append(session.last_evidence)
        await session.open(f"https://{self.host}{self.path}", ready_endpoints=self.ready_endpoints)
        await Moka.harvest(self)

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        *,
        is_detail: bool = False,
    ) -> Job:
        job = super()._job(row, listing, evidence, is_detail=is_detail)
        job.deadline = self.deadline
        job.evidence.extend(self.deadline_evidence)
        job.field_sources["deadline"] = "同届公开详情申请规则年月日 + 官网校招手册时分，逐字段核对"
        return job


class Swsmu(Securities):
    prefix = "swsmu"
    host = "job.swsmu.com"
    org = "swsmu"
    site_id = 74260
    route = "campus_apply"
    path = "/campus_apply/swsmu/74260#/jobs"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        await session.open(f"https://{self.host}/{self.route}/{self.org}/{self.site_id}#/")
        body = BeautifulSoup(await session.page.content(), "html.parser").get_text("", strip=True)
        match = re.search(r"网申截止时间为(\d{4})年(\d{1,2})月(\d{1,2})日(\d{2}:\d{2})", body)
        check(
            match is not None and "2027届秋季校园招聘" in body and "hr@swsmu.com" in body,
            "申万菱信当届校招身份或截止改变",
        )
        assert match is not None
        self.deadline = f"{match[1]}-{int(match[2]):02}-{int(match[3]):02} {match[4]}:00"
        self.deadline_evidence = [session.last_evidence]
        await session.open(f"https://{self.host}{self.path}", ready_endpoints=self.ready_endpoints)
        await Moka.harvest(self)


class Research(Branch, Hotjob):
    prefix = "research"
    suite = "SU64464d3abef57c46aff3357c"
    path = f"/{suite}/pb/school.html"


class Hongyuan(Branch):
    prefix = "hongyuan"
    host = "www.iguopin.com"
    company_id = "10685381919606097"
    path = f"/company?id={company_id}"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        home = json.loads((await session.observed("/api/company/index/v1/home?"))["body"])
        check(home.get("code") == 200, "宏源期货主体接口失败")
        info = home["data"]["company_info"]
        check(
            info["id"] == self.company_id
            and info["name"] == "宏源期货有限公司"
            and info["group_name"] == "申万宏源集团股份有限公司",
            "宏源期货集团身份变化",
        )
        identity_evidence = session.last_evidence
        counts = json.loads((await session.observed("/api/jobs/v1/count?"))["body"])
        check(counts.get("code") == 200, "宏源期货计数失败")
        counts = counts["data"]
        tree = json.loads((await session.observed("/api/company/index/v1/children-list?"))["body"])
        check(
            tree.get("code") == 200 and isinstance(tree.get("data"), list), "宏源期货下级目录失败"
        )
        names = {str(row["company_id"]): text(row["company_name"]) for row in tree["data"]}
        check(
            len(names) == len(tree["data"])
            and sum(row["jobs_num"] for row in tree["data"]) == counts["lower_job_count"],
            "宏源期货下级单位计数不一致",
        )
        names[self.company_id] = info["name"]
        tree_evidence = session.last_evidence
        seen: set[str] = set()
        for children in (False, True):
            key = "lower_job_count" if children else "company_job_count"
            path = "/company/sub/jobs" if children else "/company/jobs"
            payload: dict[str, Any] = {"page": 1, "page_size": 20}
            if children:
                payload.update(
                    company_id_only_sub=self.company_id,
                    order=[{"field": "update_time", "sort": "desc"}],
                )
            else:
                payload["company_id"] = [self.company_id]
            await session.open(
                f"https://{self.host}{path}?id={self.company_id}",
                ready_endpoints=("/api/jobs/v1/home-job",),
            )
            observed = await session.observed("/api/jobs/v1/home-job")
            check(json.loads(observed["post_data"]) == payload, "宏源期货完整目录筛选改变")
            scope = Scope(name=f"hongyuan-{key}", expected=counts[key])
            scope.evidence.extend([identity_evidence, tree_evidence])
            self.result.scopes.append(scope)
            page_seen: set[str] = set()
            page = 1
            while True:
                response = await session.request(
                    observed["url"], payload={**payload, "page": page}, credentials="omit"
                )
                check(response.get("code") == 200, "宏源期货目录业务失败")
                data = response["data"]
                check(
                    data["total"] == scope.expected
                    and data["page"] == page
                    and data["page_size"] == 20,
                    "宏源期货分页/总数改变",
                )
                rows = self.add_page(scope, data["list"], page_seen, lambda row: str(row["job_id"]))
                evidence = session.last_evidence
                for row in rows:
                    job_id = str(row["job_id"])
                    check(job_id not in seen, "宏源期货跨目录重复")
                    seen.add(job_id)
                    unit_id = str(row["company_id"])
                    check(
                        unit_id in names
                        and row["company_name"] == names[unit_id]
                        and (unit_id != self.company_id) == children,
                        "宏源期货岗位单位越界",
                    )
                    check(
                        row.get("status") == 1
                        and row.get("recruitment_type_cn") == "校园招聘"
                        and row.get("nature_cn") in {"校招", "实习"},
                        "宏源期货岗位状态或类型未知",
                    )
                    if row["nature_cn"] != "校招":
                        scope.skipped_out_of_scope += 1
                        continue
                    body = text(row.get("contents"))
                    duties, requirements = sections(body)
                    check(
                        bool(duties) and bool(requirements) and bool(row.get("job_name")),
                        "宏源期货全文缺失",
                    )
                    job = self.job(
                        job_id,
                        title=text(row["job_name"]),
                        unit=names[unit_id],
                        source_url=f"https://{self.host}/job/detail?id={job_id}",
                        duties=duties,
                        requirements=requirements
                        + f"\n专业要求：{text(row.get('major_cn'))}\n工作经验：{text(row.get('experience_cn'))}",
                        education=text(row.get("education_cn")),
                        location="、".join(
                            text(v.get("area_cn")) for v in row.get("district_list", [])
                        ),
                        deadline=text(row.get("end_time")),
                        field_sources={
                            "published": "source_missing:更新时间与招聘起始不当发布日期",
                            "deadline": "home-job.end_time，详情明确报名截止",
                            "requirements": "home-job.contents完整任职要求+major_cn+experience_cn",
                        },
                    )
                    job.evidence = [evidence, identity_evidence, tree_evidence]
                    resolved = self.before_detail(
                        f"job:{job_id}", row, scope, job, evidence=evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{job_id}", row, [job])
                if scope.unique >= int(counts[key]):
                    scope.terminal = True
                    break
                check(bool(rows), "宏源期货目录提前为空")
                page += 1


class Futures(Branch):
    prefix = "futures"
    host = "www.sywgqh.com.cn"
    path = "/Pc/Aboutus/Talent"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        soup = BeautifulSoup(await session.page.content(), "html.parser")
        body = soup.get_text("", strip=True)
        check("申银万国期货有限公司" in body and "申万宏源证券子公司" in body, "申万期货主体变化")
        check(not soup.select(".pagination,.page a"), "申万期货新增未处理分页")
        cards = soup.select(".jobListBox .tr")
        check(bool(cards), "申万期货混合目录缺失")
        scope = Scope(name="futures-mixed-all", expected=len(cards))
        scope.evidence.append(session.last_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for card in cards:
            scope.listed += 1
            cells = [node.get_text(" ", strip=True) for node in card.select(".td td")]
            detail = card.select_one(".details")
            check(
                len(cells) == 4 and detail is not None and cells[0] not in seen,
                "申万期货列表或完整详情缺失/重复",
            )
            assert detail is not None
            seen.add(cells[0])
            scope.unique += 1
            check(not detail.select("img,a,iframe"), "申万期货新增未处理附件")
            headings = detail.find_all("b")
            check(
                [n.get_text(strip=True) for n in headings]
                == ["职位描述：", "职位要求：", "联系方式："],
                "申万期货详情章节改变",
            )
            paragraphs = [node.find_next("p") for node in headings]
            check(all(node is not None for node in paragraphs), "申万期货详情章节无正文")
            duties, requirements, contact = [text(node) for node in paragraphs]
            check(bool(duties) and bool(requirements), "申万期货职责要求缺失")
            if "应届毕业生" not in requirements and not re.search(r"\d{4}届校招", contact):
                scope.skipped_out_of_scope += 1
                continue
            job = self.job(
                cells[0],
                title=cells[0],
                unit="申银万国期货有限公司",
                location=cells[1],
                education=cells[3],
                duties=duties,
                requirements=requirements + "\n" + contact,
                source_url=f"https://{self.host}{self.path}",
                field_sources={
                    "requirements": "官网隐藏完整详情，保留实际毕业届次；不把毕业范围当截止",
                    "published": "source_missing",
                    "deadline": "source_missing",
                },
            )
            self.result.jobs.append(job)
            scope.details += 1
        scope.terminal = True


BRANCHES = (Securities, Swsmu, Research, Hongyuan, Futures)
LINKS = {
    "申万菱信": "https://job.swsmu.com/campus_apply/swsmu/74260#/",
    "宏源期货": "https://www.iguopin.com/company?id=10685381919606097",
    "研究所": "https://wecruit.hotjob.cn/SU64464d3abef57c46aff3357c/pb/school.html",
    "申万期货": "https://www.sywgqh.com.cn/Pc/Aboutus/Talent",
}


class SwhyCampus(Adapter):
    name = "swhy-group-campus"
    host = "app.mokahr.com"
    path = "/campus-recruitment/swhysc-job/166086"
    scope_description = (
        "申万宏源当届主门户及四个官方独立子公司入口完整覆盖；实际单位保留，排除实习和无校招依据岗位"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        soup = BeautifulSoup(await session.page.content(), "html.parser")
        links = {str(a.get("title")): str(a.get("href")) for a in soup.select("a[title][href]")}
        check(
            set(links)
            == set(LINKS)
            | {
                "总部岗位",
                "集团",
                "分支机构",
                "【部门大揭秘】",
                "【小贴士、QA】",
                "长图文",
                "双选会行程",
                "云宣讲",
            },
            "申万宏源导航新增或删除，需重新核验子公司范围",
        )
        check(
            all(links.get(name) == url for name, url in LINKS.items()), "申万宏源独立子公司导航变化"
        )
        for name in ("总部岗位", "集团", "分支机构"):
            check(
                links.get(name, "").startswith(f"https://{self.host}{self.path}#/jobs?zhineng"),
                "申万宏源总部/集团/分支门户范围变化",
            )
        navigation_evidence = session.last_evidence
        original_output = session.output
        for adapter_type in BRANCHES:
            try:
                session.output = original_output / adapter_type.prefix
                session.output.mkdir(parents=True, exist_ok=True)
                source = self.source.model_copy(
                    update={"url": f"https://{adapter_type.host}{adapter_type.path}"}
                )
                adapter = adapter_type(
                    source,
                    self.session,
                    self.collected_at,
                    self.as_of,
                    incremental=self.incremental,
                )
                result = await adapter.collect()
                for scope in result.scopes:
                    scope.name = f"{adapter_type.prefix}:{scope.name}"
                    scope.evidence.append(navigation_evidence)
                self.result.scopes.extend(result.scopes)
                self.result.jobs.extend(result.jobs)
                self.result.issues.extend(result.issues)
                self.result.warnings.extend(result.warnings)
            except Exception as exc:
                self.error(exc, adapter_type.prefix)
            finally:
                session.output = original_output
