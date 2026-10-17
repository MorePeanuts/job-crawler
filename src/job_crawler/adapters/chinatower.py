"""Read China Tower's public virtualized job table through its normal UI pagination."""

import asyncio
import json
import math
import re
from typing import Any, cast
from urllib.parse import urlencode, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.moka import sections
from job_crawler.adapters.platforms import check
from job_crawler.adapters.shudao_notices import attach_notice_deadlines
from job_crawler.models import Collection, Job, Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession

# Only job fields used by the public recruitment page, excluding contact/account data.
PUBLIC_TABLE = """extraFields => {
 const element=document.querySelector('hc-list-new');
 const grid=element && angular.element(element).isolateScope();
 const pagerElement=document.querySelector('[ng-click*=onPagingClick]');
 const p=pagerElement && angular.element(pagerElement).scope().paging;
 if (!grid || !p || !Array.isArray(grid.model.data)) return null;
 const m=grid.model;
 const fields=['status','u_unit','id','name','department_name','u_first_party','u_MainOrgDepart','u_subordinate_unit','job_class','job_property','is_open','job_desc','u_professional','work_city','work_address','address_multi','background','release_date','auto_offline_date'].concat(extraFields || []);
 return {url:location.href,current:p.current_page,model_page:m.current_page,total:p.total_count,
 pages:p.page_count,size:p.page_size,fetching:p._is_fetching,
 selected_departments:document.querySelectorAll('.selected-department').length,
 deadline_label:m.columns_metas.auto_offline_date?.label,
 education_labels:m.columns_metas.background?.mask,
 status_labels:m.columns_metas.status?.mask,
 field_labels:Object.fromEntries((extraFields || []).map(k=>[k,m.columns_metas[k]?.label])),
 rows:m.data.map(r=>Object.fromEntries(fields.map(k=>[k,r[k]??null])))};
}"""


def validate_page(
    data: dict[str, Any], page: int, expected: int | None, deadline_label: str = "职位申请结束时间"
) -> int:
    count = int(data["total"])
    size = int(data["size"])
    check(count >= 0 and 0 < size <= 200, "铁塔目录计数无效")
    check(
        data["current"] == page and data["model_page"] == page and not data["fetching"],
        "铁塔页码与内容未同步",
    )
    check(int(data["pages"]) == math.ceil(count / size), "铁塔总页数不符")
    check(not data["selected_departments"], "铁塔目录带有分公司筛选")
    check(expected is None or count == expected, "铁塔分页期间总数变化")
    check(
        len(data["rows"]) == min(size, max(0, count - (page - 1) * size)),
        "铁塔虚拟表格未返回整页岗位",
    )
    check(data["deadline_label"] == deadline_label, "铁塔截止日期语义改变")
    return count


class ChinaTowerCampus(Adapter):
    name = "chinatower-campus"
    host = "zhaopin.chinatowercom.cn"
    path = "/recruit#/index"
    scope_description = (
        "中国铁塔官方公开校园招聘根目录，包含铁塔/智联/能源及各分公司；正常UI分页读取完整表格模型"
    )

    extra_fields: tuple[str, ...] = ()
    deadline_label = "职位申请结束时间"

    async def prepare(self, session: BrowserSession) -> None:
        page = session.page
        prompt = page.locator('[ng-click="knowTip()"]')
        if await prompt.count():
            await prompt.click(timeout=15000)
        await page.get_by_text("校园招聘", exact=True).first.click(timeout=20000)

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        page = session.page
        check(page is not None, "铁塔浏览器页面丢失")
        assert page is not None
        await self.prepare(session)
        await page.wait_for_selector("hc-list-new", timeout=30000)
        scope = Scope(name=self.name + "-all-campus")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        number = 1
        previous: set[str] = set()
        while True:
            data = None
            for _ in range(80):
                candidate = await page.evaluate(PUBLIC_TABLE, list(self.extra_fields))
                if (
                    candidate
                    and candidate["current"] == number
                    and candidate["model_page"] == number
                    and not candidate["fetching"]
                ):
                    keys = {str(r["id"]) for r in candidate["rows"]}
                    expected_rows = min(
                        int(candidate["size"]),
                        max(0, int(candidate["total"]) - (number - 1) * int(candidate["size"])),
                    )
                    if len(keys) == expected_rows and (not previous or keys != previous):
                        data = candidate
                        break
                await asyncio.sleep(0.5)
            check(data is not None, "铁塔分页没有更新完整数据")
            assert data is not None
            evidence = session.output / f"tower-campus-page-{number:04}.json"
            write_json(evidence, data)
            session.last_evidence = str(evidence)
            count = validate_page(data, number, scope.expected, self.deadline_label)
            scope.expected = count
            rows = self.add_page(scope, data["rows"], seen, lambda r: str(r["id"]))
            for row in rows:
                self.result.jobs.append(self.parse_job(row, data))
                scope.details += 1
            if scope.unique >= count:
                scope.terminal = True
                break
            previous = {str(r["id"]) for r in rows}
            session.consume_request()
            await page.locator("[ng-click=\"onPagingClick('next')\"]").click(timeout=10000)
            number += 1

    def parse_job(self, row: dict[str, Any], data: dict[str, Any]) -> Job:
        check(
            row["job_class"] == "校园招聘" and row["job_property"] == "全职",
            "铁塔目录包含其他招聘类型",
        )
        check(row["is_open"] is True, "铁塔目录包含关闭岗位")
        check(
            bool(row["name"]) and bool(row["job_desc"]) and bool(row["u_professional"]),
            "铁塔岗位正文缺失",
        )
        education = data["education_labels"].get(str(row["background"]))
        check(education is not None, "铁塔学历枚举未在源站字典中定义")
        unit = row.get("u_first_party") or row.get("u_subordinate_unit") or {}
        return self.job(
            str(row["id"]),
            title=text(row["name"]),
            unit=text(unit.get("name") or row["department_name"]),
            source_url=data["url"],
            education=text(education),
            duties=text(row["job_desc"]),
            requirements=text(row["u_professional"]),
            location=text(row["address_multi"] or row["work_city"]),
            address=text(row["work_address"]),
            published=text(row["release_date"]),
            deadline=text(row["auto_offline_date"]),
            field_sources={
                "duties": "公开岗位表.job_desc",
                "requirements": "公开岗位表.u_professional",
                "education": "background + 页面学历枚举",
                "published": "release_date（发布时间）",
                "deadline": "auto_offline_date（职位申请结束时间）",
                "address": "work_address",
            },
        )


class JacCampus(ChinaTowerCampus):
    name = "jac-campus"
    host = "zp.jac.com.cn"
    path = "/recruit#/portal_job_list?job_class=campus"
    deadline_label = "自动下线时间"
    scope_description = (
        "江汽集团官方HCM校园根目录全部事业部与子公司；使用status招聘状态，自动下线时间不写报名截止"
    )

    async def collect(self) -> Collection:
        try:
            check(urlsplit(self.source.url).hostname == self.host, "江汽来源域名不匹配")
            await self.session.open(f"https://{self.host}:8444{self.path}")
            await self.harvest()
        except Exception as exc:
            self.error(exc)
        return self.result

    async def prepare(self, session: BrowserSession) -> None:
        check("job_class=campus" in session.page.url, "江汽入口不是校园招聘")

    def parse_job(self, row: dict[str, Any], data: dict[str, Any]) -> Job:
        check(row["job_class"] == "校园招聘", "江汽混入其他招聘类别")
        check(bool(row["job_desc"]), "江汽正文缺失")
        check(str(row["status"]) in {"1", "2"}, "江汽招聘状态枚举改变")
        education = data["education_labels"].get(str(row["background"]))
        check(education is not None, "江汽学历枚举未知")
        duties, requirements = sections(
            text(row["job_desc"])
            .replace("岗位描述", "岗位职责")
            .replace("任职资格要求", "任职要求")
        )
        return self.job(
            str(row["id"]),
            title=text(row["name"]),
            unit=text((row.get("u_unit") or {}).get("name") or row["department_name"]),
            source_url=data["url"],
            work_type="校招" if row["job_property"] == "全职" else text(row["job_property"]),
            closed=str(row["status"]) == "2",
            education=text(education),
            duties=duties,
            requirements=requirements,
            location=text(row["address_multi"] or row["work_city"]),
            address=text(row["work_address"]),
            published=text(row["release_date"]),
            field_sources={
                "duties": "公开job_desc",
                "requirements": "公开job_desc:任职要求",
                "education": "background + 页面字典",
                "published": "release_date",
                "deadline": "source_missing（自动下线时间不是报名截止）",
            },
        )


class GuangxinCampus(JacCampus):
    name = "guangxin-campus"
    host = "ehr.gdghg.com"
    path = "/recruit/#/index"
    scope_description = (
        "广新集团官方校园应届生全公司目录；完整虚拟表格分页，保留实际招聘状态与发布时间"
    )

    async def collect(self) -> Collection:
        return await Adapter.collect(self)

    async def prepare(self, session: BrowserSession) -> None:
        await session.page.get_by_text("校园招聘", exact=True).first.click(timeout=20000)
        await session.page.get_by_text("应届生", exact=True).first.click(timeout=20000)

    def parse_job(self, row: dict[str, Any], data: dict[str, Any]) -> Job:
        labels = data.get("status_labels", {})
        check(labels.get("1") == "招聘中" and labels.get("2") == "已下线", "广新职位状态字典变化")
        normalized = dict(row)
        normalized["job_desc"] = re.sub(
            r"(?m)^([ \t]*)招聘条件([：:]?[ \t]*)$", r"\1任职要求\2", text(row["job_desc"])
        )
        job = super().parse_job(normalized, data)
        job.field_sources["requirements"] = "公开job_desc：任职要求/招聘条件"
        return job


class ShudaoCampus(ChinaTowerCampus):
    name = "shudao-campus"
    host = "sdhr.shudaojt.com"
    path = "/recruit#/index"
    deadline_label = "自动下线时间"
    extra_fields = (
        "u_out_org",
        "u_workplace",
        "professional",
        "u_serviceCondition",
        "u_age",
        "u_release_time",
        "department",
        "u_notice",
    )
    scope_description = "蜀道集团官方校园根目录全部单位；完整公开表格分页，保留源站工作地与招聘要求"

    async def harvest(self) -> None:
        await super().harvest()
        notice_scope = Scope(name="linked-recruitment-announcements", unit="公告")
        self.result.scopes.append(notice_scope)
        for name, exc in await attach_notice_deadlines(
            cast(BrowserSession, self.session), self.result.jobs, notice_scope
        ):
            self.error(exc, name)

    async def prepare(self, session: BrowserSession) -> None:
        prompt = session.page.get_by_text("我已阅读并同意", exact=True)
        if await prompt.count():
            await prompt.first.click(timeout=15000)
        await session.page.get_by_text("校园招聘", exact=True).first.click(timeout=20000)

    def parse_job(self, row: dict[str, Any], data: dict[str, Any]) -> Job:
        check(
            {key: data.get("field_labels", {}).get(key) for key in self.extra_fields[:6]}
            == {
                "u_out_org": "用人单位",
                "u_workplace": "工作地",
                "professional": "专业要求",
                "u_serviceCondition": "任职要求",
                "u_age": "年龄要求",
                "u_release_time": "发布时间",
            },
            "蜀道公开岗位字段语义变化",
        )
        status = data.get("status_labels", {})
        check(status.get("1") == "招聘中" and status.get("2") == "已下线", "蜀道职位状态字典变化")
        check(
            row["job_class"] == "校园招聘" and row["job_property"] in {"全职", ""},
            "蜀道混入其他类型",
        )
        check(str(row["status"]) in {"1", "2"}, "蜀道职位状态需复核")
        check(
            bool(row["name"] and (row["job_desc"] or row["u_serviceCondition"])), "蜀道岗位正文缺失"
        )
        education = data["education_labels"].get(str(row["background"]))
        check(education is not None, "蜀道学历字典缺失")
        requirements = "\n".join(
            f"{label}：{text(row.get(key))}"
            for label, key in (
                ("任职要求", "u_serviceCondition"),
                ("专业要求", "professional"),
                ("年龄要求", "u_age"),
            )
            if text(row.get(key))
        )
        check(isinstance(row.get("department"), int), "蜀道岗位部门身份缺失")
        params = {"id": row["id"], "contract_unit": None, "depart_id": row["department"]}
        detail_url = f"https://{self.host}/recruit#/common_board_view_anonymous?" + urlencode(
            {"board_category": 40, "params": json.dumps(params, separators=(",", ":"))}
        )
        return self.job(
            str(row["id"]),
            title=text(row["name"]),
            batch=text((row.get("u_notice") or {}).get("name")),
            unit=text(row["u_out_org"] or row["department_name"]),
            location=text(row["u_workplace"] or row["address_multi"] or row["work_city"]),
            address=text(row["work_address"]),
            education=text(education),
            duties=text(row["job_desc"]),
            requirements=requirements,
            source_url=detail_url,
            published=text(row["u_release_time"]),
            closed=str(row["status"]) == "2",
            field_sources={
                "duties": "公开job_desc",
                "requirements": "u_serviceCondition + professional + u_age",
                "location": "页面u_workplace优先",
                "education": "background + 当前页面字典",
                "published": "u_release_time（页面发布时间）",
                "deadline": "source_missing（自动下线不是报名截止）",
            },
        )
