"""Xfusion's public campus catalog, including every direction under main posts."""

import json
import math
from typing import cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import BrowserSession, CrawlError


class XfusionCampus(Adapter):
    name = "xfusion-campus"
    host = "career.xfusion.com"
    path = "/OfficialPortal/#/campusList"
    endpoint = "https://apig.xfusion.com/api/xJob/xjobpostdeliver/osPostpagelist?"
    ready_endpoints = (endpoint,)
    scope_description = "超聚变官方校园招聘频道 2 的无筛选目录、全部岗位方向和逐岗详情"

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        observed = await self.session.observed(self.endpoint)
        payload = json.loads(observed["post_data"])
        check(
            payload.get("pubChannel") == "2"
            and all(
                payload.get(key) == []
                for key in ("postTypeList", "belongDeptList", "workplaceList", "recruitNationList")
            )
            and payload.get("externalNameCH") == ""
            and payload.get("subChannel") == "",
            "超聚变入口不是无筛选校园目录",
        )
        check(
            set(payload)
            == {
                "pubChannel",
                "postTypeList",
                "belongDeptList",
                "workplaceList",
                "recruitNationList",
                "externalNameCH",
                "subChannel",
            },
            "超聚变目录出现未知筛选字段",
        )
        params = parse_qs(urlsplit(observed["url"]).query)
        page_size = int(params["pageSize"][0])
        token = params["X-HW-ID"][0]
        check(0 < page_size <= 100 and params["curPage"] == ["1"], "超聚变起始页异常")
        public_headers = observed["public_headers"]
        check(
            public_headers.get("lang") == "zh_CN"
            and public_headers.get("datasource") == "6"
            and public_headers.get("x-hw-id") == token,
            "超聚变公开请求头与入口不符",
        )
        headers = {"lang": "zh_CN", "datasource": "6", "X-HW-ID": token}
        api = "https://apig.xfusion.com/api/xJob/xjobpostdeliver/"
        scope = Scope(name="pub-channel-2-all")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        leaf_ids: set[str] = set()
        page = 1
        while True:
            listing = await session.request(
                query(observed["url"], curPage=page), payload=payload, headers=headers
            )
            check(
                listing.get("success") is True and listing.get("code") == 200, "超聚变目录业务失败"
            )
            data = listing["data"]
            page_vo = data["pageVO"]
            expected = int(page_vo["totalRows"])
            pages = int(page_vo["totalPages"])
            check(
                expected >= 0
                and pages == max(1, math.ceil(expected / page_size))
                and int(page_vo["curPage"]) == page
                and int(page_vo["pageSize"]) == page_size,
                "超聚变分页元数据异常",
            )
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "超聚变翻页期间总数变化")
            rows = self.add_page(
                scope,
                data["result"],
                seen,
                lambda row: (
                    f"main:{row['mainPostId']}"
                    if int(row.get("postCnt") or 0) > 0
                    else f"post:{row['postIdKey']}"
                ),
            )
            check(len(rows) <= page_size, "超聚变单页超过分页大小")
            for row in rows:
                row_key = (
                    f"main:{row['mainPostId']}"
                    if int(row.get("postCnt") or 0)
                    else f"post:{row['postIdKey']}"
                )
                try:
                    await self._expand(row, api, token, headers, leaf_ids)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, row_key)
            if page == pages:
                check(scope.unique == expected, "超聚变末页数与源总数不符")
                scope.terminal = True
                break
            check(bool(rows) and scope.unique < expected, "超聚变分页提前终止")
            page += 1

    async def _expand(
        self,
        row: dict[str, object],
        api: str,
        token: str,
        headers: dict[str, str],
        leaf_ids: set[str],
    ) -> list[Job]:
        session = cast(BrowserSession, self.session)
        main_id = int(str(row.get("mainPostId") or 0))
        post_count = int(str(row.get("postCnt") or 0))
        check(text(row.get("jobTypeDesc")) == "全职", "超聚变目录混入非正式岗位")
        if post_count:
            check(main_id > 0, "超聚变主岗位缺少身份")
            detail = await session.request(
                f"{api}mainPostDeliverDetail?mainPostId={main_id}&pubChannel=2&X-HW-ID={token}",
                headers=headers,
                detail=True,
            )
            check(
                detail.get("success") is True and detail.get("code") == 200, "超聚变主岗位详情失败"
            )
            data = detail["data"]
            check(int(data["postMain"]["id"]) == main_id, "超聚变主岗位详情身份错配")
            children = data["postList"]
            check(
                isinstance(children, list) and len(children) == post_count, "超聚变岗位方向数量不符"
            )
            ids = [str(child["id"]) for child in children]
            check(str(row["postIdKey"]) in ids, "超聚变卡片 ID 不在方向列表")
        else:
            check(main_id == 0, "超聚变独立岗位的主岗位 ID 异常")
            ids = [str(row["postIdKey"])]
        check(len(ids) == len(set(ids)) and not leaf_ids.intersection(ids), "超聚变岗位方向重复")
        leaf_ids.update(ids)
        jobs: list[Job] = []
        for post_id in ids:
            detail = await session.request(
                f"{api}postDeliverDetail?postId={post_id}&pubChannel=2&X-HW-ID={token}",
                headers=headers,
                detail=True,
            )
            check(detail.get("success") is True and detail.get("code") == 200, "超聚变岗位详情失败")
            data = detail["data"]
            check(int(data["id"]) == int(post_id), "超聚变岗位详情身份错配")
            channels = data.get("postPubChannList") or []
            channel = next((item for item in channels if str(item.get("pubChannel")) == "2"), None)
            if channel is None:
                raise CrawlError("source_changed", "超聚变岗位缺少校园频道")
            check(str(channel.get("pubState")) == "1", "超聚变岗位校园频道未公开")
            check(
                str(channel.get("jobType")) == "1" and channel.get("jobTypeDesc") == "全职",
                "超聚变详情混入非正式岗位",
            )
            check(bool(text(data.get("postNameCh"))), "超聚变岗位标题缺失")
            job = self.job(
                post_id,
                title=text(data["postNameCh"]),
                source_url=f"https://{self.host}/OfficialPortal/#/postDetail?mainPostId={main_id}&postType=2&postId={post_id}",
                work_type="校招",
                unit=text(data.get("orgName")),
                category_raw=text(data.get("postTypeDesc")),
                location=text(data.get("workPlaceDesc")),
                duties=text(channel.get("jobDesc")),
                requirements=text(channel.get("jobRequirement")),
                published=text(data.get("firstPubTime")),
                field_sources={
                    "unit": "postDeliverDetail.data.orgName",
                    "category_raw": "postDeliverDetail.data.postTypeDesc",
                    "location": "postDeliverDetail.data.workPlaceDesc",
                    "duties": "postDeliverDetail.data.postPubChannList[pubChannel=2].jobDesc",
                    "requirements": "postDeliverDetail.data.postPubChannList[pubChannel=2].jobRequirement",
                    "published": "postDeliverDetail.data.firstPubTime",
                    "deadline": "source_missing",
                },
            )
            jobs.append(job)
            self.result.jobs.append(job)
        return jobs
