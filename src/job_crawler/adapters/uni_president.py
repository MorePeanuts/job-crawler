"""Uni-President's inline catalog and six-employer MA programme."""

import json
import re
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://hr.pec.com.tw"
CAREERS = ROOT + "/zh-CN/job"
API = "https://pechr-web-backend.azurewebsites.net/api/jobs"
MA = ROOT + "/zh-CN/hr/upgrecruit/upgma"
MATCHING = ROOT + "/HRMatching/hrmatching"
INTERN = "https://www.uni-president.com.tw/HR/pecintern/index.html"
Q8 = "Q8.我是應屆畢業生，但尚未取得畢業證書或正在服兵役，是否可以申請？"
Q5 = "Q5.統一集團事業夥伴有多少家公司參與？"
EMPLOYERS = {
    "www.uni-president.com.tw",
    "www.7-11.com.tw",
    "www.cosmed.com.tw",
    "www.ppc-life.com.tw",
    "www.uni-ustyle.com.tw",
    "www.dream-mall.com.tw",
}


def catalog(data: object) -> tuple[list[dict[str, Any]], int]:
    check(isinstance(data, dict), "统一职位响应不是对象")
    assert isinstance(data, dict)
    rows, total = data.get("items"), data.get("totalCount")
    check(isinstance(rows, list) and type(total) is int and total >= 0, "统一职位总数/列表无效")
    assert isinstance(rows, list) and isinstance(total, int)
    for row in rows:
        check(isinstance(row, dict), "统一职位不是对象")
        check(type(row.get("jobId")) is int and row["jobId"] > 0, "统一职位缺少ID")
        for field in ("jobName", "jobDesc", "orgCode"):
            check(isinstance(row.get(field), str) and bool(row[field].strip()), f"统一缺少{field}")
        for field in (
            "workPlace",
            "conditionEdu",
            "conditionLang",
            "conditionExp",
            "conditionOthers",
            "jobIntroUrl",
            "jobCategory",
        ):
            check(isinstance(row.get(field), str), f"统一{field}结构变化")
        check(not row["jobIntroUrl"], "统一新增未解析职位附件/介绍链接")
        for field in ("isClosedMark", "isActiveMark", "isDeleteMark", "isSubJob"):
            check(type(row.get(field)) is bool, f"统一{field}状态缺失")
        check(
            row["isActiveMark"] and not row["isClosedMark"] and not row["isDeleteMark"],
            "公开在招目录含非活动职位，须核验状态",
        )
        for field in ("startDate", "endDate"):
            value = row.get(field)
            check(isinstance(value, str) and bool(value), f"统一{field}缺失")
            parsed = datetime.fromisoformat(value)
            check(parsed.tzinfo is not None, "统一日期缺少时区")
        check(
            datetime.fromisoformat(row["startDate"]) <= datetime.fromisoformat(row["endDate"]),
            "统一日期倒置",
        )
    return rows, total


def ma_program(conditions: str, faq: str) -> tuple[list[dict[str, str]], str]:
    doc = BeautifulSoup(conditions, "html.parser")
    headings = [x for x in doc.select("h2") if x.get_text(strip=True) == "申請資格"]
    check(len(headings) == 1, "统一MA申请资格缺失")
    common = headings[0].find_next_sibling("div")
    check(common is not None, "统一MA公共要求缺失")
    assert common is not None
    common_text = common.get_text("\n", strip=True)
    check("不限學歷" in common_text and "不限科系" in common_text, "统一MA资格变化")
    faq_doc = BeautifulSoup(faq, "html.parser")
    answers: dict[str, str] = {}
    for panel in faq_doc.select(".v-expansion-panel"):
        title = panel.select_one(".q_title")
        answer = panel.select_one(".v-expansion-panel-text__wrapper")
        if title is not None and answer is not None:
            answers[title.get_text(strip=True)] = answer.get_text("\n", strip=True)
    check(
        Q8 in answers
        and "可以，請您於填寫履歷時說明。" in answers[Q8]
        and "取得畢業證書" in answers[Q8],
        "统一MA应届资格未核对",
    )
    check(Q5 in answers and "6家公司的業態" in answers[Q5], "统一MA参与范围变化")
    rows: list[dict[str, str]] = []
    for heading in doc.select(".sheet-item-title"):
        links = heading.select("a.webBtn[href]")
        check(len(links) == 1, "统一MA公司标识不唯一")
        company_url = str(links[0]["href"])
        employer = urlsplit(company_url).hostname or ""
        check(employer in EMPLOYERS and company_url.startswith("https://"), "统一MA新增单位须核验")
        section = heading.parent.parent if heading.parent else None
        check(section is not None, "统一MA职位分节缺失")
        assert section is not None
        fields: dict[str, str] = {}
        for label in section.select(".itemlabel"):
            value = label.find_next_sibling("div")
            check(value is not None, "统一MA分节字段缺失")
            assert value is not None
            check(not value.select("a[href], img, iframe, object"), "统一MA职位字段新增链接或附件")
            key = label.get_text(strip=True)
            check(key not in fields, "统一MA分节字段重复")
            fields[key] = value.get_text("\n", strip=True)
        check(
            set(fields) == {"職缺名稱", "工作內容", "實作規劃", "職涯發展"}
            and all(fields.values()),
            "统一MA分节不完整",
        )
        check(not section.select("iframe, object, table"), "统一MA新增嵌入目录")
        rows.append(
            {
                "id": employer,
                "company_url": company_url,
                "title": fields["職缺名稱"],
                "duties": fields["工作內容"],
                "training": fields["實作規劃"],
                "career": fields["職涯發展"],
            }
        )
    check(len(rows) == 6 and {r["id"] for r in rows} == EMPLOYERS, "统一MA六个公司分节未闭合")
    return rows, common_text + "\n【官网应届资格问答】\n" + Q8 + "\n" + answers[Q8]


def requirements(row: dict[str, Any]) -> str:
    return "\n".join(
        f"{label}：{row[key]}"
        for key, label in (
            ("conditionEdu", "學歷"),
            ("conditionLang", "語言"),
            ("conditionExp", "經驗"),
            ("conditionOthers", "其他條件"),
        )
        if row[key]
    )


class UniPresidentCareers(Adapter):
    name = "uni-president-careers"
    host = "hr.pec.com.tw"
    path = "/zh-CN/job"
    ready_endpoints = (API + "?",)
    scope_description = "统一官网全部公开职位与集团MA六公司分节；核对暑期实习和制造人才媒合"

    async def views(self) -> tuple[str, str, str, str, list[str]]:
        session = cast(BrowserSession, self.session)
        evidence: list[str] = []
        await session.open(MA)
        await session.page.get_by_role("tab", name="職缺條件", exact=True).click()
        await session.page.locator(".sheet-item-title").first.wait_for()
        conditions = await session.page.content()
        evidence.append(session.snapshot("ma-conditions", conditions))
        await session.page.get_by_role("tab", name="應徵Q&A", exact=True).click()
        for question in (Q8, Q5):
            await session.page.get_by_text(question, exact=True).click()
        await session.page.get_by_text("可以，請您於填寫履歷時說明。", exact=True).wait_for()
        faq = await session.page.content()
        evidence.append(session.snapshot("ma-faq", faq))
        await session.open(MATCHING)
        matching = await session.page.content()
        evidence.append(session.snapshot("manufacturing-matching", matching))
        await session.open(INTERN)
        intern = await session.page.content()
        evidence.append(session.snapshot("intern-programme", intern))
        return conditions, faq, matching, intern, evidence

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        scope = Scope(name="uni-president-public-catalog")
        self.result.scopes.append(scope)
        initial = await session.observed(API + "?")
        _, initial_total = catalog(json.loads(initial["body"]))
        # Use one fresh target time for the entire catalog; never replay an old query date.
        target = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        seen: set[str] = set()
        plans: list[tuple[dict[str, Any], str]] = []
        page = 1
        while True:
            data = await session.request(
                API + "?" + urlencode({"page": page, "countPerPage": 10, "targetDate": target}),
                credentials="omit",
            )
            rows, total = catalog(data)
            check(total == initial_total, "统一职位总数在采集期间变化")
            scope.expected = total
            expected_page = min(10, max(0, total - (page - 1) * 10))
            check(len(rows) == expected_page, "统一分页短页或越界")
            self.add_page(scope, rows, seen, lambda r: str(r["jobId"]))
            for row in rows:
                if row["isSubJob"]:
                    check(
                        row["orgCode"] == "GRP"
                        and re.fullmatch(r"\d{4}統一企業集團事業夥伴（ＭＡ）", row["jobName"])
                        is not None,
                        "统一新增未知招募计划",
                    )
                    plans.append((row, session.last_evidence))
                else:
                    check(row["orgCode"] == "PEC", "统一目录新增单位须核验")
                    self.result.jobs.append(
                        self.job(
                            str(row["jobId"]),
                            title=row["jobName"],
                            source_url=CAREERS,
                            duties=text(row["jobDesc"]),
                            requirements=requirements(row),
                            education=row["conditionEdu"],
                            location=row["workPlace"],
                            published=datetime.fromisoformat(row["startDate"])
                            .astimezone(ZoneInfo("Asia/Taipei"))
                            .date()
                            .isoformat(),
                            deadline=row["endDate"],
                            category_raw=row["jobCategory"],
                            work_type="校招"
                            if re.search(
                                r"應屆|应届|新鮮人|校園徵才",
                                row["jobName"] + row["conditionOthers"],
                            )
                            else "未明确校招",
                            field_sources={
                                "published": "startDate；官网职务发布日期，UTC转换台湾日历日",
                                "deadline": "endDate源UTC时刻原值，不延长至日末",
                                "requirements": "conditionEdu/Lang/Exp/Others",
                                "location": "workPlace；不使用页脚地址",
                            },
                        )
                    )
                    scope.details += 1
            if len(seen) == total:
                break
            page += 1
            check(page <= 100, "统一分页超过验证预算")
        check(len(plans) == 1, "统一MA计划缺失或新增，需核验页面范围")
        ma_scope = Scope(name="uni-president-ma-employers", unit="公司职位")
        self.result.scopes.append(ma_scope)
        conditions, faq, matching, intern, view_evidence = await self.views()
        expanded, common = ma_program(conditions, faq)
        plan, plan_evidence = plans[0]
        self.add_page(ma_scope, expanded, set(), lambda row: row["id"])
        ma_scope.expected = len(expanded)
        ma_scope.evidence = [plan_evidence, *view_evidence[:2]]
        for row in expanded:
            job = self.job(
                f"{plan['jobId']}:{row['id']}",
                title=row["title"],
                source_url=MA,
                apply_url=CAREERS,
                batch=plan["jobName"],
                duties=row["duties"],
                requirements=common
                + "\n【实作规划】\n"
                + row["training"]
                + "\n【职涯发展】\n"
                + row["career"],
                education=plan["conditionEdu"],
                location=plan["workPlace"],
                published=datetime.fromisoformat(plan["startDate"])
                .astimezone(ZoneInfo("Asia/Taipei"))
                .date()
                .isoformat(),
                deadline=plan["endDate"],
                field_sources={
                    "work_type": "官网MA问答Q8明确应届可申请",
                    "source_key": "目录计划jobId+官方公司链接域名",
                    "unit": "公司以Logo/官网URL标识，未从URL猜测法人名：" + row["company_url"],
                    "location": "对应集团MA目录workPlace统一分发范围",
                    "published": "对应MA目录startDate；UTC转换台湾日历日",
                    "deadline": "对应MA目录endDate源UTC时刻，不延长至日末",
                },
            )
            job.evidence = ma_scope.evidence[:]
            self.result.jobs.append(job)
            ma_scope.details += 1
        ma_scope.terminal = True
        scope.details += 1
        scope.terminal = True
        other = Scope(name="uni-president-other-programmes", unit="项目", expected=2)
        self.result.scopes.append(other)
        matching_text = text(matching)
        check(
            "請填寫基本資料" in matching_text
            and "進行媒合60天" in matching_text
            and "確認送出" in matching_text,
            "统一制造伙伴不再是已验证媒合登记",
        )
        other.listed = other.unique = other.skipped_out_of_scope = 1
        other.evidence = view_evidence[2:]
        intern_text = text(intern)
        check(
            "暑期實習生招募" in intern_text
            and "實習期間為全職學生身分" in intern_text
            and not re.search(r"正式校招|應屆畢業生招募", intern_text),
            "统一实习计划范围变化",
        )
        other.listed = other.unique = other.skipped_out_of_scope = 2
        other.terminal = True
