"""Public store trainee project linked directly by Haidilao's corporate site."""

import json
import re
from typing import Any, cast
from urllib.parse import parse_qs

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter
from job_crawler.adapters.platforms import check
from job_crawler.models import Issue, Scope
from job_crawler.transport import BrowserSession

API = "https://rc.xiucaizp.com/api/"
BRANDS = API + "websiteStaffTypeConfig/getBrandList"
CATEGORIES = API + "websiteStaffTypeConfig/getList"
DETAIL = API + "websiteStaffTypeDetailConfig/getListByConfigId"
LABELS = {1: "正式员工", 3: "钟点工/假期工", 6: "管培生"}
MODULES = {
    1: "招聘岗位",
    2: "职位要求",
    3: "福利待遇",
    4: "发展途径(经竟聘考核后可入职)",
    5: "报名渠道",
    6: "工作内容",
}


def data(
    observed: dict[str, Any], endpoint: str, form: dict[str, list[str]]
) -> list[dict[str, Any]]:
    check(observed["url"] == endpoint, "海底捞接口域名或路径变化")
    check(parse_qs(observed.get("post_data") or "") == form, "海底捞接口表单范围不符")
    response = json.loads(observed["body"])
    check(
        response.get("code") == 200 and isinstance(response.get("data"), list), "海底捞业务响应失败"
    )
    rows = response["data"]
    check(all(isinstance(row, dict) for row in rows), "海底捞目录数据结构变化")
    return rows


def categories(rows: list[dict[str, Any]], html: str) -> None:
    check(
        len(rows) == 3
        and {row.get("id"): row.get("staffTypeName") for row in rows} == LABELS
        and all(row.get("brandId") == "1567" and row.get("isActive") == 1 for row in rows),
        "海底捞门店完整招聘栏目变化",
    )
    document = BeautifulSoup(html, "html.parser")
    check(
        [(n.get("data-id"), n.get_text(strip=True)) for n in document.select(".btnToggle")]
        == [(str(key), name) for key, name in LABELS.items()],
        "海底捞页面栏目与完整接口不一致",
    )


def project(rows: list[dict[str, Any]]) -> dict[str, str]:
    check(
        len(rows) == len(MODULES)
        and {r.get("moduleType"): r.get("moduleName") for r in rows} == MODULES
        and len({r.get("id") for r in rows}) == len(rows)
        and all(
            r.get("websiteStaffTypeConfigId") == 6 and r.get("isActive") == r.get("isEnable") == 1
            for r in rows
        ),
        "海底捞管培生详情模块、父ID或启用状态变化",
    )
    contents: dict[int, str] = {}
    for row in rows:
        if row["moduleType"] == 5:
            # This is an application QR, not additional job content.
            continue
        document = BeautifulSoup(row.get("content") or "", "html.parser")
        check(
            not document.select("img,a[href],iframe,object,embed"), "海底捞项目出现未处理正文附件"
        )
        contents[row["moduleType"]] = document.get_text("\n", strip=True)
    intro = contents[1]
    requirements = contents[2]
    check("海底捞" in intro and "门店" in intro, "海底捞管培生项目介绍身份变化")
    check(
        "2027届应届生" in requirements and "2026届毕业一年内" in requirements,
        "海底捞校园招聘对象变化",
    )
    degree = re.search(r"(本科及以上)学历", requirements)
    location = re.search(r"可接受(全国)分配", requirements)
    return {
        "duties": contents[6],
        "requirements": requirements,
        "education": degree[1] if degree else "",
        "location": location[1] if location else "",
    }


class HaidilaoStoreTrainee(Adapter):
    name = "haidilao-store-trainee"
    host = "weihaizhaopin.wehichina.com"
    path = "/"
    ready_endpoints = (BRANDS, CATEGORIES)
    scope_description = (
        "海底捞官网门店招聘门户完整管培生项目；排除通用员工与假期工栏目，不含独立职能渠道"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        brands = data(await session.observed(BRANDS), BRANDS, {})
        check(
            brands == [{"brandId": "1567", "brandName": "海底捞门店岗位"}], "海底捞门店品牌目录变化"
        )
        rows = data(await session.observed(CATEGORIES), CATEGORIES, {"brandId": ["1567"]})
        categories(rows, await session.page.content())
        list_evidence = session.last_evidence
        scope = Scope(name="haidilao-store-categories", expected=3, unit="招聘栏目")
        scope.evidence.append(list_evidence)
        self.result.scopes.append(scope)
        self.add_page(scope, rows, set(), lambda r: str(r["id"]))
        scope.skipped_out_of_scope = 2
        session.consume_request()
        async with session.page.expect_response(
            lambda response: response.url == DETAIL and response.request.post_data == "configId=6",
            timeout=int(session.config.timeout * 1000),
        ) as waiting:
            await session.page.locator('.btnToggle[data-id="6"]').click()
        response = await waiting.value
        check(response.status == 200, "海底捞管培生请求失败")
        await response.finished()
        modules = data(await session.observed(DETAIL), DETAIL, {"configId": ["6"]})
        values = project(modules)
        detail_evidence = session.last_evidence
        # Retain only public business fields in the incremental fingerprint.
        fingerprint = [
            {
                key: row[key]
                for key in [
                    "id",
                    "websiteStaffTypeConfigId",
                    "moduleType",
                    "moduleName",
                    "content",
                    "isEnable",
                ]
            }
            for row in modules
        ]
        listing = self.job("config:6", title=LABELS[6], source_url=self.source.url)
        reused = self.before_detail(
            "job:config:6", fingerprint, scope, listing, evidence=detail_evidence
        )
        if reused is not None:
            self.result.jobs.extend(reused)
        else:
            job = self.job(
                "config:6",
                title=LABELS[6],
                unit=brands[0]["brandName"],
                work_type="校招",
                source_url=self.source.url,
                **values,
                field_sources={
                    "duties": "管培生工作内容模块；源站当前缺失时留空",
                    "requirements": "管培生职位要求模块",
                    "education": "职位要求明确学历；未知不猜填",
                    "location": "职位要求明确可接受全国分配；未知不猜填",
                    "published": "source_missing:后台createTime/updateTime不是岗位发布日期",
                    "deadline": "source_missing:公开项目未披露截止时间",
                    "address": "source_missing:全国分配，无逐店详细地址",
                },
            )
            job.evidence = [list_evidence, detail_evidence]
            self.result.jobs.append(job)
            scope.details += 1
            self.remember("job:config:6", fingerprint, [job])
        self.result.warnings.append(
            Issue(
                code="application_portal_unverified",
                message="公开项目正文可读；接入探测时报名二维码目标显示系统维护，未验证每轮投递系统可用性",
                source_id=self.source.source_id,
                url=self.source.url,
            )
        )
        scope.terminal = True
