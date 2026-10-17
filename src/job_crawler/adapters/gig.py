"""GIG campus data delivered by the unauthenticated Zhaopin ZK portal."""

import json
import re
from collections import Counter
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession

API = "/zhaokao/api/site/portal/pc/"
API_HOST = "zkapi.zhaopin.com"
COMPANY = "广西投资集团有限公司"
LABELS = {
    "customkey076177cd58ab": "招聘企业",
    "jobName": "岗位名称",
    "jobNumber": "岗位编号",
    "customkey3d9b2e7c1e25": "岗位类型",
    "customkey20ecf65a8df9": "招聘人数",
    "eduRecord": "学历要求",
    "professionReq": "专业要求",
    "customkey70ce360cce67": "工作地点",
}


class Node(BaseModel):
    id: str
    parentId: str
    name: str
    jobNum: int = Field(ge=0)
    childJobNum: int | None = Field(default=None, ge=0)
    childs: list["Node"] = Field(default_factory=list)


class Record(BaseModel):
    id: str = Field(min_length=1)
    jobName: str = Field(min_length=1)
    jobNumber: str = Field(min_length=1)
    deptId: str
    jobGroupName: str
    status: int
    eduRecord: str
    professionReq: str
    unit: str = Field(alias="customkey076177cd58ab", min_length=1)
    category: str = Field(alias="customkey3d9b2e7c1e25")
    location: str = Field(alias="customkey70ce360cce67")


class Label(BaseModel):
    jobColumnKey: str
    jobColumnName: str
    showIs: int


def validate_labels(values: list[object]) -> None:
    labels = [Label.model_validate(v) for v in values]
    visible = [v for v in labels if v.showIs == 1]
    mapping = {v.jobColumnKey: v.jobColumnName for v in visible}
    check(len(mapping) == len(visible) and mapping == LABELS, "广投公开详情字段变化")


def validate_tree(roots: list[Node], rows: list[Record], expected: int) -> list[Node]:
    check(len(roots) == 1 and roots[0].name == "校园招聘", "广投校园单位根目录变化")
    check(len(rows) == expected, "广投校园分组与全目录数量不符")
    check(len({r.id for r in rows}) == len(rows), "广投岗位ID重复")
    check(len({r.jobNumber for r in rows}) == len(rows), "广投岗位编号重复")
    counts = Counter(r.deptId for r in rows)
    nodes: list[Node] = []
    seen: set[str] = set()

    def walk(node: Node, parent: str) -> int:
        check(node.id not in seen and node.parentId == parent, "广投单位重复或父级不符")
        seen.add(node.id)
        nodes.append(node)
        check(counts[node.id] == node.jobNum, f"广投单位岗位数不符：{node.name}")
        children = sum(walk(child, node.id) for child in node.childs)
        if node.childJobNum is not None:
            check(children == node.childJobNum, f"广投下属岗位数不符：{node.name}")
        return node.jobNum + children

    check(walk(roots[0], "") == expected, "广投全树岗位数不符")
    check(set(counts) <= seen, "广投岗位出现未知单位")
    return nodes


def announcement(data: dict[str, Any]) -> tuple[str, str, str]:
    detail = data["detail"]
    title = text(detail["title"])
    check(bool(re.fullmatch(r"广西投资集团\d{4}届秋季校园招聘启事", title)), "广投公告范围变化")
    check(not detail.get("siteFileList"), "广投公告新增附件，须核验岗位内容")
    # Office-authored spans split even single years across inline elements.
    body = re.sub(r"\s+", "", text(detail["content"]))
    target = re.search(r"二、招聘对象\s*(\d{4}届高校毕业生。)", body)
    check(target is not None, "广投招聘对象缺失")
    assert target is not None
    year = target[1][:4]
    check(year in title and f"面向{year}届硕士、博士毕业生" in body, "广投专项校园对象变化")
    deadline = re.search(
        r"报名截止时间[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})", body
    )
    published = re.search(r"广西投资集团有限公司\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*$", body)
    check(deadline is not None and published is not None, "广投公告发布日期或截止时刻缺失")
    assert deadline is not None and published is not None
    date = "-".join(f"{int(x):02}" for x in published.groups())
    end = "-".join(f"{int(x):02}" for x in deadline.groups()[:3])
    end += f" {int(deadline[4]):02}:{deadline[5]}:00"
    return title, date, end


async def observed(session: BrowserSession, endpoint: str) -> tuple[Any, dict[str, Any], str]:
    response = await session.observed_path(API + endpoint)
    url = urlsplit(response["url"])
    check(url.hostname == API_HOST and url.path == API + endpoint, "广投响应来自未知接口")
    payload = json.loads(response["body"])
    check(payload.get("code") == 200 and payload.get("success") is True, "广投业务接口失败")
    return payload["data"], response, session.last_evidence


class GigCampus(Adapter):
    name = "gig-campus-public-catalog"
    host = "gtjt.zhaopin.com"
    path = "/"
    ready_endpoints = (f"https://{API_HOST}{API}cms-menu/listArticleByMenuId?",)
    scope_description = "广西投资集团公开校园全目录及急需紧缺硕博专项；单位树与全目录闭合"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        site, _, _ = await observed(session, "site")
        check(site["siteName"] == COMPANY, "广投站点主体变化")
        article, _, article_evidence = await observed(session, "cms-menu/listArticleByMenuId")
        title, published, deadline = announcement(article)
        session.consume_request()
        await session.page.get_by_text("招聘岗位", exact=True).first.click(timeout=10000)
        groups, _, group_evidence = await observed(session, "job-info/job-column-type-list-reformc")
        campus = [g for g in groups if g["name"] == "校园招聘"]
        check(len(campus) == 1, "广投校园分组缺失或重复")
        group = campus[0]
        session.consume_request()
        await session.page.get_by_text("校园招聘", exact=True).first.click(timeout=10000)
        raw, response, listing_evidence = await observed(session, "job-info/portal-list-reformc")
        check(
            json.loads(response["post_data"])
            == {"jobName": "", "deptIds": [], "jobGroups": [group["value"]]},
            "广投目录带有局部筛选",
        )
        labels, _, label_evidence = await observed(session, "job-info/job-title-list")
        validate_labels(labels)
        tree, _, tree_evidence = await observed(session, "site/dept/tree/list")
        rows = [Record.model_validate(row) for row in raw]
        nodes = validate_tree(
            [Node.model_validate(n) for n in tree], rows, int(group["jobDataNum"])
        )
        evidence = [
            article_evidence,
            group_evidence,
            listing_evidence,
            label_evidence,
            tree_evidence,
        ]
        directory = Scope(name="campus-unit-tree", unit="单位", expected=len(nodes))
        self.result.scopes.append(directory)
        session.last_evidence = tree_evidence
        self.add_page(directory, [n.model_dump() for n in nodes], set(), lambda n: n["id"])
        directory.details = len(nodes)
        directory.terminal = True
        page_url = f"https://{self.host}/zk/#/dept-job-list/list?jobGroup={group['value']}"
        for node in nodes:
            scope = Scope(name=f"unit:{node.id}:{node.name}", expected=node.jobNum)
            self.result.scopes.append(scope)
            session.last_evidence = listing_evidence
            unit_rows = [r for r in raw if r["deptId"] == node.id]
            for row in self.add_page(scope, unit_rows, set(), lambda r: r["id"]):
                key = str(row["id"])
                try:
                    record = Record.model_validate(row)
                    check(
                        record.status == 1 and record.jobGroupName == "校园招聘",
                        "广投岗位状态或类型变化",
                    )
                    job = self.job(
                        key,
                        title=text(record.jobName),
                        source_url=page_url,
                        apply_url=page_url,
                        unit=text(record.unit),
                        batch=title,
                        category_raw=text(record.category),
                        education=text(record.eduRecord),
                        location=text(record.location),
                        duties="",
                        requirements=f"招聘对象：{title[6:10]}届高校毕业生。\n学历要求：{text(record.eduRecord)}\n专业要求：{text(record.professionReq)}",
                        published=published,
                        deadline=deadline,
                        field_sources={
                            "unit": "job-info元数据招聘企业/customkey076177cd58ab",
                            "location": "job-info元数据工作地点/customkey70ce360cce67",
                            "education": "job-info.eduRecord",
                            "requirements": "公告招聘对象与job-info.eduRecord/professionReq",
                            "duties": "source_missing",
                            "published": "当前校园招聘公告落款日期",
                            "deadline": "当前校园招聘公告报名截止时间",
                        },
                    )
                    job.evidence = evidence.copy()
                    fingerprint = {"row": row, "announcement": article}
                    resolved = self.before_detail(
                        f"job:{key}", fingerprint, scope, job, evidence=listing_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{key}", fingerprint, [job])
                except Exception as exc:
                    self.error(exc, key)
            scope.terminal = True
