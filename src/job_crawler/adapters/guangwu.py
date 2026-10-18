"""Whole public campus arrays, with explicit unresolved rolling deadlines."""

import json
import re
from dataclasses import asdict, dataclass
from typing import cast
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections, strip_heading
from job_crawler.models import Scope
from job_crawler.storage import fingerprint
from job_crawler.transport import BrowserSession

ROOT = "https://xy.liepin.com"
PATH = "/guangwuzhaopin/job.html"
CATALOG = ROOT + "/guangwuzhaopin/js/job3.json"
UNITS = ROOT + "/guangwuzhaopin/js/job4.json"
MIRROR = ROOT + "/guangwu2025/job.html"
MIRROR_DATA = ROOT + "/guangwu2025/js/job.json"
ANNOUNCEMENT = "https://job.henu.edu.cn/module/position_brief_detail/id-109253/nid-10822"


def array(observed: dict[str, object], endpoint: str) -> list[dict[str, object]]:
    url = urlsplit(str(observed.get("url", "")))
    target = urlsplit(endpoint)
    check(
        url.scheme == target.scheme and url.netloc == target.netloc and url.path == target.path,
        "广物接口身份变化",
    )
    check(observed.get("status") == 200, "广物目录HTTP失败")
    body = observed.get("body")
    check(isinstance(body, str), "广物响应格式变化")
    rows = json.loads(cast(str, body))
    check(
        isinstance(rows, list) and all(isinstance(row, dict) for row in rows),
        "广物目录不是完整数组",
    )
    return rows


def unit_tree(html: str, rows: list[dict[str, object]]) -> dict[str, str]:
    document = BeautifulSoup(html, "html.parser")
    check(
        "校招岗位" in document.get_text() and "广物控股集团" in document.get_text(),
        "广物页面范围变化",
    )
    check(not document.select(".pagination,.pager"), "广物新增未处理分页")
    tree: dict[str, str] = {}
    for node in document.select(".ltab p[data-id]"):
        key, label = str(node["data-id"]), node.get_text(strip=True)
        check(key.isdigit() and bool(label), "广物单位ID或名称缺失")
        check(key not in tree or tree[key] == label, "广物重复单位ID名称冲突")
        tree[key] = label
    expected: dict[str, str] = {}
    for row in rows:
        key, label = str(row.get("data-id", "")), row.get("company")
        check(key.isdigit() and isinstance(label, str) and bool(label), "广物单位映射字段缺失")
        check(key not in expected, "广物单位映射重复")
        expected[key] = cast(str, label)
    check(bool(tree) and tree == expected, "广物完整单位树与映射不一致")
    return tree


@dataclass
class Position:
    group: str
    owner: str
    company: str
    department: str
    title: str
    link: str
    education: str
    major: str
    category: str
    location: str
    description: str
    requirements: str

    @property
    def key(self) -> str:
        return fingerprint([self.group, self.company, self.department, self.title, self.link])


def positions(rows: list[dict[str, object]], tree: dict[str, str]) -> list[Position]:
    check(bool(rows), "广物全目录空数组缺少明确零岗位证明")
    result = []
    seen: set[str] = set()
    fields = {
        "owner": "所属企业",
        "company": "company",
        "department": "Department",
        "title": "jobName",
        "link": "link",
        "education": "edu",
        "major": "major",
        "category": "Category",
        "location": "address",
        "description": "job_description",
        "requirements": "job_requirements",
    }
    for row in rows:
        check(type(row.get("data-id")) is int, "广物岗位单位ID结构变化")
        group = str(row["data-id"])
        values: dict[str, str] = {}
        for field, source in fields.items():
            value = row.get(source)
            check(isinstance(value, str), f"广物岗位字段结构变化：{source}")
            values[field] = cast(str, value).strip()
        check(group in tree and tree[group] == values["owner"], "广物岗位不属于完整单位树")
        check(all(values[k] for k in ("company", "title", "link")), "广物岗位身份缺失")
        check(urlsplit(values["link"]).scheme in {"https", "http"}, "广物岗位投递URL无效")
        post = Position(group=group, **values)
        check(post.key not in seen, "广物完整目录重复岗位身份")
        seen.add(post.key)
        result.append(post)
    return result


def deadline(html: str) -> str:
    document = BeautifulSoup(html, "html.parser")
    body = document.select_one("#main_content")
    check(body is not None, "广物简章正文缺失")
    assert body is not None
    text = body.get_text("\n", strip=True)
    check("广物控股集团" in text and "国内2026届" in text, "广物简章主体或届别变化")
    match = re.search(r"3[.、]\s*截止时间\s*招满即止[。.]?\s*五[、.]", text)
    check(match is not None, "广物正文截止条件变化，不能使用平台顶部日期")
    # The only image is the already verified application QR, not job content.
    images = body.select("img")
    check(
        len(images) == 1
        and str(images[0].get("src", "")).endswith("/d2890820954c40e1b972a7d44c9a2b98.jpg"),
        "广物简章二维码或附件变化",
    )
    check(not body.select("iframe,object,embed"), "广物简章新增未处理正文附件")
    check(
        all(
            a.get_text(strip=True) == "登录后查看详情" and a.get("href") == "javascropt:void(0)"
            for a in body.select("a[href]")
        ),
        "广物简章新增未处理链接附件",
    )
    return "招满即止"


def details(post: Position) -> dict[str, str]:
    for value in (post.description, post.requirements):
        check(not BeautifulSoup(value, "html.parser").find(), "广物纯文本正文新增HTML或附件")
    duties, extra = split_sections(post.description)
    requirements = strip_heading(post.requirements, "requirements")
    if extra and extra not in requirements:
        requirements += "\n" + extra
    if post.major:
        requirements += "\n专业要求：" + post.major
    education = post.education
    summary = re.findall(r"博士|硕士|本科|大专|专科", education.replace("专科", "大专"))
    body = set(
        re.findall(
            r"(博士|硕士|本科|大专)(?:及以上)?(?:学历|学位)", requirements.replace("专科", "大专")
        )
    )
    if len(set(summary)) == 1 and body and set(summary) != body:
        education = "来源冲突（摘要：" + education + "；正文：" + "、".join(sorted(body)) + "）"
    return {"duties": duties, "requirements": requirements.strip(), "education": education}


class GuangwuCampus(Adapter):
    name = "guangwu-campus"
    host = "xy.liepin.com"
    path = PATH
    ready_endpoints = (CATALOG, UNITS)
    scope_description = (
        "广物官网统一校园目录全部单位，与2026届门户交叉核验；招满即止全部保留截止待核验"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        raw = array(await session.observed(CATALOG), CATALOG)
        evidence = [session.last_evidence]
        tree = unit_tree(await session.page.content(), array(await session.observed(UNITS), UNITS))
        evidence.append(session.last_evidence)
        posts = positions(raw, tree)
        await session.open(MIRROR, ready_endpoints=(MIRROR_DATA,))
        mirror = array(await session.observed(MIRROR_DATA), MIRROR_DATA)
        check(mirror == raw, "广物两个校园门户目录不一致")
        evidence.append(session.last_evidence)
        await session.open(ANNOUNCEMENT)
        ending = deadline(await session.page.content())
        evidence.append(session.last_evidence)
        parent = Scope(
            name="guangwu-units",
            expected=len(tree),
            listed=len(tree),
            unique=len(tree),
            details=len(tree),
            terminal=True,
            unit="单位",
            evidence=evidence,
        )
        self.result.scopes.append(parent)
        for group, label in tree.items():
            selected = [p for p in posts if p.group == group]
            scope = Scope(
                name=f"guangwu-campus:{group}:{label}",
                expected=len(selected),
                listed=len(selected),
                unique=len(selected),
                terminal=True,
                evidence=evidence,
            )
            self.result.scopes.append(scope)
            for post in selected:
                key = "campus:" + post.key
                state = {**asdict(post), "deadline": ending, "batch": "2026届"}
                try:
                    listing = self.job(
                        key, title=post.title, source_url=ROOT + PATH, deadline=ending
                    )
                    cached = self.before_detail(key, state, scope, listing, evidence=evidence[0])
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    job = self.job(
                        key,
                        title=post.title,
                        source_url=ROOT + PATH,
                        apply_url=post.link,
                        unit=" / ".join([post.owner, post.company, post.department]),
                        batch="2026届",
                        category_raw=post.category,
                        location=post.location,
                        deadline=ending,
                        **details(post),
                        field_sources={
                            "published": "source_missing:目录没有首次发布日期，不沿用公告平台日期",
                            "deadline": ANNOUNCEMENT + "#main_content 正文截止条件；待核验",
                            "education": "edu与正文交叉核对；冲突保留原文待核验",
                            "location": "address实际为工作地点，不推断详细地址",
                            "address": "source_missing:未提供街道地址",
                            "duties": "job_description明确章节",
                            "requirements": "job_requirements及job_description明确要求和major",
                        },
                    )
                    job.evidence = list(evidence)
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(key, state, [job])
                except Exception as exc:
                    self.error(exc, key)
