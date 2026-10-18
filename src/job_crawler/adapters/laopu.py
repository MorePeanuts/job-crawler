"""Laopu's full public employer catalog plus its latest campus announcement."""

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections, strip_heading
from job_crawler.filtering import parse_date
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

ROOT = "https://job.hutb.edu.cn"
COMPANY = "老铺黄金股份有限公司"
EMPLOYER = ROOT + "/detail/company?company_id=117167"
ANNOUNCEMENT = ROOT + "/detail/career?id=716780"
CATALOG = ROOT + "/detail/get_job_list"


def page_data(html: str) -> dict[str, Any]:
    """Parse server-provided public JSON without evaluating website code."""
    document = BeautifulSoup(html, "html.parser")
    values = []
    for node in document.select("script:not([src])"):
        script = node.get_text()
        match = re.search(r"window\.PAGE_DATA\s*=\s*", script)
        if match:
            value, _ = json.JSONDecoder().raw_decode(script[match.end() :])
            check(isinstance(value, dict), "老铺公开页面数据不是对象")
            values.append(value)
    check(len(values) == 1, "老铺公开页面数据缺失或重复，不能把页壳算零岗位")
    return values[0]


def employer(data: dict[str, Any]) -> None:
    company = data.get("company_info", {})
    check(
        company.get("company_id") == 117167 and company.get("company_name") == COMPANY,
        "老铺企业目录主体不匹配",
    )
    history = data.get("recruitment_list")
    check(isinstance(history, list), "老铺企业招聘记录缺失")
    assert isinstance(history, list)
    talks = [r for r in history if r.get("business_type") == "宣讲会"]
    check(bool(talks) and str(talks[0].get("id")) == "716780", "老铺出现尚未核对的新宣讲范围")
    check(not data.get("recruitment_info"), "老铺企业新增未处理的独立招聘简章")


@dataclass
class Role:
    name: str
    location: str
    duties: str
    requirements: str


def public_text(html: str) -> str:
    document = BeautifulSoup(html, "html.parser")
    check(
        not document.select("img,a[href],iframe,object,embed,table"),
        "老铺岗位正文包含未处理附件或表格",
    )
    return document.get_text("\n", strip=True)


def announcement(data: dict[str, Any]) -> tuple[dict[str, Role], list[dict[str, Any]]]:
    career = data.get("career", {})
    check(
        career.get("company_id") == 117167
        and career.get("company_name") == COMPANY
        and str(career.get("career_talk_id")) == "716780",
        "老铺校园简章身份错配",
    )
    check(career.get("docs") == [] and career.get("practices") == [], "老铺简章新增附件或实习分支")
    document = BeautifulSoup(career.get("remark", ""), "html.parser")
    paragraphs = [p.get_text("", strip=True) for p in document.find_all("p", recursive=False)]
    check(len(paragraphs) > 6 and "HK6181" in document.get_text(), "老铺简章正文主体缺失")
    begin = [i for i, p in enumerate(paragraphs) if p == "二、招聘岗位及薪资标准"]
    end = [i for i, p in enumerate(paragraphs) if p == "三、福利"]
    check(len(begin) == len(end) == 1 and begin[0] < end[0], "老铺招聘正文边界变化")
    nodes = document.find_all("p", recursive=False)[begin[0] + 1 : end[0]]
    for node in nodes:
        public_text(str(node))
    # No non-paragraph content can contain a silently omitted role or attachment.
    check(
        all(getattr(n, "name", None) == "p" for n in document.contents if str(n).strip()),
        "老铺简章出现未处理正文结构",
    )
    values = paragraphs[begin[0] + 1 : end[0]]
    heads = [
        (i, re.fullmatch(r"【([^】]+)】(?:（工作地点：([^）]+)）)?", p))
        for i, p in enumerate(values)
    ]
    starts = [(i, m) for i, m in heads if m]
    check(bool(starts), "老铺简章没有岗位段落")
    roles: dict[str, Role] = {}
    for number, (index, match) in enumerate(starts):
        assert match is not None
        finish = starts[number + 1][0] if number + 1 < len(starts) else len(values)
        body = "\n".join(values[index + 1 : finish])
        duties, requirements = split_sections(body, include_preamble=False)
        check(bool(requirements), "老铺岗位缺少完整任职要求")
        name = match[1]
        check(name not in roles, "老铺简章角色重复")
        roles[name] = Role(name, match[2] or "", duties, requirements)
    cards = career.get("jobs")
    check(isinstance(cards, list), "老铺简章职位卡片缺失")
    ids = [str(c.get("publish_id", "")) for c in cards]
    check(all(i.isdigit() for i in ids) and len(set(ids)) == len(ids), "老铺简章卡片ID重复或缺失")
    for card in cards:
        check(card.get("job_name") in roles, "老铺简章卡片没有对应正文角色")
    return roles, cards


def catalog_page(body: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    check(body.get("code") == 1 and isinstance(body.get("data"), dict), "老铺公开职位接口失败")
    data = body["data"]
    count = str(data.get("total", ""))
    check(count.isdigit(), "老铺企业总数不明确")
    rows = data.get("items")
    check(isinstance(rows, list) and len(rows) <= 10, "老铺分页结构变化")
    result = []
    for row in rows:
        check(isinstance(row, dict) and str(row.get("publish_id", "")).isdigit(), "老铺目录ID缺失")
        result.append(
            {
                k: row[k]
                for k in ["publish_id", "job_name", "city_name", "degree_require", "create_time"]
            }
        )
        check(
            all(
                isinstance(result[-1][k], str)
                for k in ["job_name", "city_name", "degree_require", "create_time"]
            ),
            "老铺目录业务字段结构变化",
        )
        check(bool(result[-1]["job_name"]), "老铺岗位名为空")
    return int(count), result


def reconcile(
    rows: list[dict[str, Any]], roles: dict[str, Role], cards: list[dict[str, Any]]
) -> list[Role]:
    index = {str(row["publish_id"]): row for row in rows}
    check(len(index) == len(rows), "老铺企业目录重复ID")
    for card in cards:
        key = str(card["publish_id"])
        check(
            key in index and index[key]["job_name"] == card["job_name"],
            "老铺卡片不在企业完整目录中",
        )
    check(all(row["job_name"] in roles for row in rows), "老铺企业目录出现未核对校园角色")
    present = {row["job_name"] for row in rows}
    missing = [role for name, role in roles.items() if name not in present]
    check(
        all(role.name == "招聘经理助理" and role.duties and role.requirements for role in missing),
        "老铺新增未核对的简章独有岗位",
    )
    return missing


def location(value: str, role: Role) -> str:
    if not role.location or value.removesuffix("市") == role.location.removesuffix("市"):
        return value
    return value + "；校招简章：" + role.location


def detail(data: dict[str, Any], row: dict[str, Any], role: Role) -> dict[str, Any]:
    job = data.get("job", {})
    check(
        str(job.get("publish_id")) == str(row["publish_id"])
        and job.get("company_id") == 117167
        and job.get("company_name") == COMPANY
        and job.get("job_name") == row["job_name"],
        "老铺详情身份或标题错配",
    )
    check(job.get("is_practice") in [0, 1], "老铺详情工作类型未知")
    state = job.get("job_status")
    check(state in {"招聘中", "已过期", "已结束", "招聘结束", "已截止"}, "老铺详情招聘状态未知")
    published, ending = job.get("publish_time", ""), job.get("end_time", "")
    check(isinstance(published, str) and isinstance(ending, str), "老铺日期字段结构变化")
    check(
        (not published or parse_date(published) is not None)
        and (not ending or parse_date(ending) is not None),
        "老铺逐岗日期无法解析",
    )
    duties = strip_heading(public_text(job.get("job_descript", "")), "duties")
    requirements = strip_heading(public_text(job.get("job_require", "")), "requirements")
    check(bool(duties and requirements), "老铺独立详情正文不完整")
    city = job.get("city_name", "")
    degree = job.get("degree_require", "")
    check(
        city == row["city_name"] and degree == row["degree_require"], "老铺列表与详情地点/学历变化"
    )
    return {
        "duties": duties,
        "requirements": requirements,
        "location": location(city, role),
        "education": degree,
        "published": published,
        "deadline": ending,
        "address": text(job.get("work_address")),
        "work_type": "实习" if job["is_practice"] else "校招",
        "visible": state == "招聘中",
        "closed": state != "招聘中",
    }


class LaopuCampus(Adapter):
    name = "laopu-campus"
    host = "job.hutb.edu.cn"
    path = "/detail/career?id=716780"
    scope_description = "老铺黄金湖南工商大学完整企业目录与最新校园简章联合；6个目录ID及1个简章内联角色，不合并同名不同岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        roles, cards = announcement(page_data(await session.page.content()))
        announcement_evidence = session.last_evidence
        employer(page_data(await session.request_html(EMPLOYER)))
        employer_evidence = session.last_evidence
        scope = Scope(name="laopu-employer-117167")
        self.result.scopes.append(scope)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        evidences: dict[str, str] = {}
        page = 1
        while True:
            body = await session.request(f"{CATALOG}?company_id=117167&page={page}&pagesize=10")
            total, values = catalog_page(body)
            if scope.expected is None:
                scope.expected = total
            check(scope.expected == total, "老铺分页总数变化")
            fresh = self.add_page(scope, values, seen, lambda r: str(r["publish_id"]))
            check(scope.unique <= total, "老铺目录数量超过总数")
            rows.extend(fresh)
            for row in fresh:
                evidences[str(row["publish_id"])] = session.last_evidence
            if scope.unique == total:
                scope.terminal = True
                break
            check(len(values) == 10, "老铺企业目录提前结束")
            page += 1
        extra = reconcile(rows, roles, cards)
        role_scope = Scope(
            name="laopu-career-716780-roles",
            expected=len(roles),
            listed=len(roles),
            unique=len(roles),
            details=len(roles),
            terminal=True,
            unit="简章角色",
            evidence=[announcement_evidence, employer_evidence],
        )
        self.result.scopes.append(role_scope)
        for row in rows:
            key = str(row["publish_id"])
            role = roles[row["job_name"]]
            state = {"row": row, "role": asdict(role)}
            try:
                listing = self.job(
                    key, title=row["job_name"], source_url=f"{ROOT}/detail/job?id={key}"
                )
                cached = self.before_detail(key, state, scope, listing, evidence=evidences[key])
                if cached is not None:
                    self.result.jobs.extend(cached)
                    continue
                await session.open(listing.source_url)
                fields = detail(page_data(await session.page.content()), row, role)
                job = self.job(
                    key,
                    title=row["job_name"],
                    source_url=listing.source_url,
                    **fields,
                    field_sources={
                        "published": "PAGE_DATA.job.publish_time；不使用目录create_time",
                        "deadline": "PAGE_DATA.job.end_time；不使用活动日期或全简章最大截止",
                        "location": "详情city_name与当前简章交叉核对；冲突保留原文待核验",
                        "address": "PAGE_DATA.job.work_address；为空时不沿用公司注册地址",
                        "education": "PAGE_DATA.job.degree_require；同名不同ID分别保留",
                        "duties": "PAGE_DATA.job.job_descript",
                        "requirements": "PAGE_DATA.job.job_require",
                    },
                )
                job.evidence = [evidences[key], announcement_evidence, session.last_evidence]
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(key, state, [job])
            except Exception as exc:
                self.error(exc, key)
        if extra:
            inline = Scope(
                name="laopu-career-716780-inline",
                expected=len(extra),
                listed=len(extra),
                unique=len(extra),
                terminal=True,
                evidence=[announcement_evidence],
            )
            self.result.scopes.append(inline)
            for role in extra:
                key = "career:716780:" + role.name
                state = asdict(role)
                listing = self.job(key, title=role.name, source_url=ANNOUNCEMENT)
                cached = self.before_detail(
                    key, state, inline, listing, evidence=announcement_evidence
                )
                if cached is not None:
                    self.result.jobs.extend(cached)
                    continue
                job = self.job(
                    key,
                    title=role.name,
                    source_url=ANNOUNCEMENT,
                    duties=role.duties,
                    requirements=role.requirements,
                    location=role.location,
                    field_sources={
                        "duties": "当前简章该角色完整工作职责",
                        "requirements": "当前简章该角色完整任职要求",
                        "published": "source_missing:简章未披露岗位首次发布日期",
                        "deadline": "source_missing:该内联角色未披露岗位截止时间；旧详情跳转不视为关闭",
                        "address": "source_missing:只给城市，不使用公司注册地址",
                        "location": "当前简章明确工作地点",
                    },
                )
                job.evidence = [announcement_evidence]
                self.result.jobs.append(job)
                inline.details += 1
                self.remember(key, state, [job])
