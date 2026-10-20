"""石药官网链接的 Redsea 公开校园频道。"""

import json
import re
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession, CrawlError

CHANNEL_ID = "623d3b53-0d75-4649-8d4c-df366532fb58"
CHANNEL_PATH = f"/RedseaPlatform/zhaopin/zpChannelQrCode/{CHANNEL_ID}/officeWebsite.mob"
CHANNEL_URL = f"https://ehr.e-cspc.com:8081{CHANNEL_PATH}"
LIST_PATH = "/RedseaPlatform/zhaopin/zpChannelQrCode/queryPostList.mob"


def campus_link(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    links = [
        str(anchor.get("href", ""))
        for anchor in soup.select("a[href]")
        if anchor.get_text(" ", strip=True) == "校园招聘"
    ]
    check(bool(links) and set(links) == {CHANNEL_URL}, "石药官网校园招聘入口改变")
    return CHANNEL_URL


def channel_rows(observed: dict[str, Any]) -> list[dict[str, Any]]:
    url = urlsplit(str(observed.get("url", "")))
    check(
        url.scheme == "https"
        and url.hostname == "ehr.e-cspc.com"
        and url.port == 8081
        and url.path == LIST_PATH,
        "石药公开岗位接口改变",
    )
    params = parse_qs(str(observed.get("post_data") or ""), keep_blank_values=True)
    check(
        params.get("channelQrId") == [CHANNEL_ID]
        and params.get("root_id") == ["cspc"]
        and params.get("sortName") == ["zri.ext_rankNum"]
        and not any(
            any(value for value in values)
            for key, values in params.items()
            if key not in {"channelQrId", "root_id", "sortName", "push_request_id"}
        ),
        "石药校园频道、机构根或筛选条件改变",
    )
    requested = str(params.get("push_request_id", [""])[0]).split(",")
    check(bool(requested[0]) and len(requested) == len(set(requested)), "石药频道岗位集合无效")
    response = json.loads(str(observed.get("body") or ""))
    check(response.get("state") == "1", "石药岗位列表业务失败")
    check(response.get("total") in {"", None}, "石药岗位列表出现未支持的分页计数")
    rows = response.get("jsonList")
    check(isinstance(rows, list) and bool(rows), "石药频道未证明当前完整岗位目录")
    for row in rows:
        check(isinstance(row, dict), "石药岗位行结构改变")
        check(
            text(row.get("REQUEST_ID")) in requested,
            "石药岗位不属于本轮公开频道集合",
        )
    return rows


def location(value: Any) -> str:
    raw = text(value)
    match = re.fullmatch(r"(.+?(?:省|自治区))(.+市)", raw)
    return f"{match[1]}/{match[2]}" if match else raw


class CspcCampus(Adapter):
    name = "cspc-campus"
    host = "www.e-cspc.com"
    path = "/hr/"
    scope_description = "石药集团官网校园频道的全量公开目录；仅应届生全职岗位"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        check(session.page is not None, "石药官网页面未就绪")
        homepage_evidence = self.session.last_evidence
        link = campus_link(await session.page.content())
        await self.session.open(link, ready_endpoints=(f"https://ehr.e-cspc.com:8081{LIST_PATH}",))
        observed = await self.session.observed(LIST_PATH)
        rows = channel_rows(observed)
        evidence = self.session.last_evidence
        scope = Scope(name="cspc-public-campus-channel", expected=len(rows))
        scope.evidence.append(homepage_evidence)
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for row in self.add_page(scope, rows, seen, lambda item: text(item.get("REQUEST_ID"))):
            job_id = text(row["REQUEST_ID"])
            label = text(row.get("item2"))
            work_age = text(row.get("WORK_AGE"))
            if label == "应届生":
                check(work_age == "-2", "石药应届生与经验要求冲突")
            elif label == "在校生" or work_age.lstrip("-").isdigit() and int(work_age) > 0:
                scope.skipped_out_of_scope += 1
                continue
            else:
                raise CrawlError("source_changed", "石药出现未知招聘对象，须核对校园范围")
            if text(row.get("item5")) != "全职":
                scope.skipped_out_of_scope += 1
                continue
            try:
                check(
                    bool(text(row.get("PUBLISH_NAME")))
                    and bool(text(row.get("JOB_DUTY")))
                    and bool(text(row.get("JOB_REQUEST"))),
                    "石药岗位标题、职责或要求缺失",
                )
                deadline = text(row.get("EXPECT_DATE"))
                check(deadline in {"", "无"}, "石药截止日期出现未验证格式")
                job = self.job(
                    job_id,
                    title=text(row["PUBLISH_NAME"]),
                    work_type="校招",
                    source_url=link,
                    unit=text(row.get("ORG_ALIAS_NAME") or row.get("BELONG_UNIT_ORG_NAME")),
                    location=location(row.get("work_place")),
                    education=text(row.get("item1")),
                    duties=text(row["JOB_DUTY"]),
                    requirements=text(row["JOB_REQUEST"]),
                    field_sources={
                        "unit": "queryPostList.jsonList[].ORG_ALIAS_NAME",
                        "location": "queryPostList.jsonList[].work_place；明确省市时按源文本分段",
                        "education": "queryPostList.jsonList[].item1",
                        "duties": "queryPostList.jsonList[].JOB_DUTY",
                        "requirements": "queryPostList.jsonList[].JOB_REQUEST",
                        "published": "source_missing；APPLY_TIME/UPDATE_TIME 语义未证实",
                        "deadline": "EXPECT_DATE=无；未提供明确截止日期",
                    },
                )
                job.evidence = [homepage_evidence, evidence]
                reused = self.before_detail(f"job:{job_id}", row, scope, job, evidence=evidence)
                if reused is not None:
                    self.result.jobs.extend(reused)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{job_id}", row, [job])
            except Exception as exc:
                self.error(exc, job_id)
        scope.terminal = True
