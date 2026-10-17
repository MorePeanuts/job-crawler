"""Huadian campus notices and the young-talent unit demand appendix."""

import json
import re
from typing import cast

from pydantic import BaseModel, TypeAdapter

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession

CATEGORIES = {10000: "校园招聘", 10010: "青年骏才"}


class Header(BaseModel):
    pk: int
    name: str
    corp_pk: int
    corp_ext_name: str
    zp_class_item_pk: int
    zp_class_item_ext_name: str
    begin_date: str
    end_date: str
    notice_status: int
    off_status: int


class Post(BaseModel):
    pk: int
    notice_pk: int
    name: str
    corp_pk: int
    corp_ext_name: str
    job_status: int
    work_place: str = ""
    job_edu_requirements: str = ""
    job_pro_requirements: str = ""


class Notice(Header):
    content: str
    noticeFileList: list[dict[str, object]]
    zpJobVOList: list[Post]


class Demand(BaseModel):
    number: int
    unit: str
    unit_location: str
    majors: str


def common_requirements(body: str) -> str:
    plain = text(body).replace("**", "")
    section = re.search(
        r"(?ms)^\s*[一二三四五六七八九十]+[、.．]\s*招聘(?:要求|条件)\s*\n"
        r"(.*?)(?=^\s*[一二三四五六七八九十]+[、.．]|\Z)",
        plain,
    )
    check(section is not None and bool(section[1].strip()), "华电公告共同招聘条件缺失")
    assert section is not None
    return section[1].strip()


def young_demands(body: str) -> list[Demand]:
    plain = text(body).replace("**", "")
    lines = [line.strip() for line in plain.splitlines() if line.strip().startswith("|")]
    check(len(lines) >= 3, "华电青年骏才需求附表缺失")
    headings = [cell.strip() for cell in lines[0].strip("|").split("|")]
    check(headings == ["序号", "需求单位", "单位所在地", "需求专业"], "华电附表表头变化")
    check(bool(re.fullmatch(r"[|:\-\s]+", lines[1])), "华电附表分隔行变化")
    rows: list[Demand] = []
    units: set[str] = set()
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        check(len(cells) == 4 and cells[0].isdigit(), "华电附表行结构变化")
        check(int(cells[0]) == len(rows) + 1 and all(cells), "华电附表序号或字段缺失")
        check(cells[1] not in units, "华电附表需求单位重复")
        units.add(cells[1])
        rows.append(
            Demand(number=int(cells[0]), unit=cells[1], unit_location=cells[2], majors=cells[3])
        )
    return rows


def validate_notice(header: Header, detail: Notice) -> None:
    check(
        header.model_dump() == detail.model_dump(include=set(Header.model_fields)),
        "华电公告与索引身份或状态不一致",
    )
    check(detail.notice_status == 10 and detail.off_status == 0, "华电公告发布状态变化")
    check(bool(detail.content.strip()) and bool(detail.zpJobVOList), "华电公告正文或岗位表为空")
    check(not detail.noticeFileList, "华电公告新增附件，须核验补充范围")
    check(not re.search(r"<img\b|!\[", detail.content), "华电公告新增图片内容，须核验")
    ids: set[int] = set()
    for post in detail.zpJobVOList:
        check(post.pk not in ids, "华电公告内岗位重复")
        ids.add(post.pk)
        check(
            post.notice_pk == detail.pk and post.corp_pk == detail.corp_pk,
            "华电岗位关联公告或单位不一致",
        )
        check(
            post.corp_ext_name == detail.corp_ext_name and bool(post.name.strip()),
            "华电岗位单位或标题变化",
        )
        check(post.job_status == 0, "华电岗位发布状态变化")


class ChdCampus(Adapter):
    name = "chd-campus-notices"
    host = "rencaishichang.chd.com.cn"
    path = "/w3/"
    scope_description = "华电校园公告完整职位表及青年骏才需求单位附表；不重复输出共用专业投递入口"

    def notice_url(self, header: Header) -> str:
        return f"https://{self.host}/w3/#/w3/notice/card_view?notice_pk={header.pk}&class_item_pk={header.zp_class_item_pk}"

    def parse_jobs(self, detail: Notice) -> list[Job]:
        requirements = common_requirements(detail.content)
        common = {
            "source_url": self.notice_url(detail),
            "batch": detail.name,
            "deadline": detail.end_date,
            "field_sources": {
                "published": "source_missing:begin_date为招聘开始，不当作发布日期",
                "deadline": "Notice.end_date；页面招聘时间结束",
                "requirements": "职位表专业要求及公告招聘要求/条件原文",
                "duties": "source_missing:源公告未提供独立岗位职责",
            },
        }
        if detail.zp_class_item_pk == 10010:
            return [
                self.job(
                    f"{detail.pk}:unit:{row.unit}",
                    title=f"青年骏才（{row.majors}）",
                    unit=row.unit,
                    requirements=f"需求专业：{row.majors}\n单位所在地（非岗位工作地点）：{row.unit_location}\n\n{requirements}",
                    **common,
                )
                for row in young_demands(detail.content)
            ]
        return [
            self.job(
                f"{detail.pk}:{post.pk}",
                title=post.name,
                unit=post.corp_ext_name,
                education=post.job_edu_requirements,
                location=post.work_place if post.work_place != "--" else "",
                requirements=f"专业要求：{post.job_pro_requirements}\n\n{requirements}",
                **common,
            )
            for post in detail.zpJobVOList
        ]

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check("中国华电集团有限公司" in await session.page.content(), "华电门户主体变化")
        menu = json.loads((await session.observed_path("/cdata/ZPClassItemIndex.json"))["body"])
        check(isinstance(menu, list), "华电招聘栏目字典不是数组")
        labels = {item["pk"]: item["name"] for item in menu if item.get("b_website_show")}
        check(
            all(labels.get(key) == label for key, label in CATEGORIES.items()),
            "华电校园栏目字典变化",
        )
        all_notices: set[int] = set()
        all_posts: set[int] = set()
        for category, label in CATEGORIES.items():
            await session.open(
                f"https://{self.host}/w3/#/w3/notice/main_view?class_item_pk={category}"
            )
            observed = await session.observed_path(f"/cdata/{category}/ZPNoticeIndex.json")
            headers = TypeAdapter(list[Header]).validate_python(json.loads(observed["body"]))
            check(0 < len(headers) <= 1000, "华电公告索引为空或超出预算")
            scope = Scope(name=f"{category}-notices", expected=len(headers), unit="公告")
            self.result.scopes.append(scope)
            list_evidence = session.last_evidence
            rows = self.add_page(
                scope, [h.model_dump() for h in headers], set(), lambda row: str(row["pk"])
            )
            scope.terminal = True
            for raw in rows:
                header = Header.model_validate(raw)
                try:
                    check(
                        header.zp_class_item_pk == category
                        and header.zp_class_item_ext_name == label,
                        "华电目录招聘栏目错配",
                    )
                    check(header.pk not in all_notices, "华电跨栏目公告重复")
                    all_notices.add(header.pk)
                    listing = self.job(
                        str(header.pk),
                        title=header.name,
                        source_url=self.notice_url(header),
                        deadline=header.end_date,
                    )
                    if select(listing, "all", self.as_of).reason == "expired":
                        scope.skipped_expired += 1
                        continue
                    entity = f"announcement:{header.pk}"
                    cached = self.before_detail(entity, raw, scope, evidence=list_evidence)
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    data = await session.request(
                        f"https://{self.host}/cdata/{category}/Notice{header.pk}.json", detail=True
                    )
                    detail = Notice.model_validate(data)
                    validate_notice(header, detail)
                    evidence = session.last_evidence
                    post_ids = {p.pk for p in detail.zpJobVOList}
                    check(not post_ids & all_posts, "华电跨公告岗位ID重复")
                    all_posts.update(post_ids)
                    jobs = self.parse_jobs(detail)
                    self.result.scopes.append(
                        Scope(
                            name=f"notice-{header.pk}-positions",
                            expected=len(post_ids),
                            listed=len(post_ids),
                            unique=len(post_ids),
                            details=len(post_ids),
                            unit="投递分类" if category == 10010 else "岗位",
                            terminal=True,
                            evidence=[evidence],
                        )
                    )
                    if category == 10010:
                        self.result.scopes.append(
                            Scope(
                                name=f"notice-{header.pk}-unit-demands",
                                expected=len(jobs),
                                listed=len(jobs),
                                unique=len(jobs),
                                details=len(jobs),
                                unit="单位需求",
                                terminal=True,
                                evidence=[evidence],
                            )
                        )
                    for job in jobs:
                        job.evidence = [list_evidence, evidence]
                    self.result.jobs.extend(jobs)
                    scope.details += 1
                    self.remember(entity, raw, jobs)
                except Exception as exc:
                    self.error(exc, str(header.pk))
