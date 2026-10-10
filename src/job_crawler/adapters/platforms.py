"""Four deterministic campus adapters migrated from observed platform contracts."""

import json
import math
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.filtering import select
from job_crawler.models import Scope
from job_crawler.transport import CrawlError


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CrawlError("source_changed", message)


class Pingan(Adapter):
    name = "pingan"
    host = "campus.pingan.com"
    path = "/freshGraduates"
    scope_description = "应届生 positionType=1；全集团目录，列表已包含职责和要求；不含实习"

    async def harvest(self) -> None:
        observed = await self.session.observed("queryPositionPage")
        payload = json.loads(observed["post_data"])
        check(
            str(payload.get("positionType", payload.get("PositionType", ""))) == "1",
            "无法确认应届生筛选条件",
        )
        scope = Scope(name="fresh-graduates")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                observed["url"], payload={**payload, "PageNum": page}
            )
            check(str(response.get("responseCode")) == "10001", "平安业务响应失败")
            data = response["data"]
            expected, pages = int(data["totalCount"]), int(data["totalPage"])
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "平安源总数变化")
            rows = self.add_page(scope, data["list"], seen, lambda row: str(row["idPosition"]))
            for row in rows:
                try:
                    job = self.job(
                        str(row["idPosition"]),
                        title=text(row["positionName"]),
                        unit=text(row.get("businessUnitName")),
                        location="、".join(
                            filter(
                                None,
                                [
                                    text(row.get("workCity")),
                                    text(
                                        row.get("workCityOverseas") or row.get("overseasWorkCity")
                                    ),
                                ],
                            )
                        ),
                        education=text(row.get("education")),
                        category_raw=text(row.get("positionCategoryName")),
                        published=text(row.get("publishDate")),
                        deadline=text(row.get("endDate")),
                        duties=text(row.get("duty")),
                        requirements=text(row.get("qualification")),
                        source_url="https://campus.pingan.com/positionDetail?"
                        + urlencode({"positionId": row["idPosition"]}),
                        field_sources={
                            "duties": "list[].duty",
                            "requirements": "list[].qualification",
                            "published": "list[].publishDate",
                        },
                    )
                    self.result.jobs.append(job)
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, str(row.get("idPosition")))
            if page >= pages:
                scope.terminal = True
                break
            check(bool(rows), "平安分页提前返回空页")
            page += 1


def ccb_key(row: dict[str, Any]) -> str:
    return ":".join(str(row.get(key, "")) for key in ("planId", "planPost", "orgId", "secondOrgId"))


def ccb_url(row: dict[str, Any]) -> str:
    return "https://job2.ccb.cn/cn/job/job_detail.html?" + urlencode(
        {
            key: row.get(key, "")
            for key in ("planId", "planPost", "planType", "orgId", "secondOrgId")
        }
    )


class CCB(Adapter):
    name = "ccb"
    host = "job2.ccb.cn"
    path = "/cn/job/plan_index.html?planType=XY"
    scope_description = (
        "planType=XY 全校园目录；岗位×单位/分支机构复合键；包含源站可见后由公共层筛选截止时间"
    )

    async def harvest(self) -> None:
        observed = await self.session.observed("TXCODE=NHR104")
        scope = Scope(name="XY")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        detail_url = ""
        while True:
            data = await self.session.request(
                query(observed["url"], PAGE_JUMP=page, REC_IN_PAGE=100)
            )
            check(str(data.get("SUCCESS")).lower() == "true", "建行列表业务失败")
            expected, pages = int(data["TOTAL_REC"]), int(data["TOTAL_PAGE"])
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "建行源总数变化")
            rows = self.add_page(scope, data["planPostList"], seen, ccb_key)
            for row in rows:
                try:
                    listing_job = self.job(
                        ccb_key(row),
                        title=text(row["planPostName"]),
                        unit=text(row.get("orgName")),
                        location=text(row.get("workPlace")),
                        published=text(row.get("postDate")),
                        deadline=text(row.get("endDate")),
                        source_url=ccb_url(row),
                        field_sources={
                            "deadline": "NHR104.endDate",
                            "detail": "仅当列表截止日期明确已过期时跳过详情",
                        },
                    )
                    if select(listing_job, "all", self.as_of).reason == "expired":
                        self.result.jobs.append(listing_job)
                        scope.skipped_expired += 1
                        continue
                    if not detail_url:
                        await self.session.open(ccb_url(row))
                        detail_url = (await self.session.observed("TXCODE=NHR107"))["url"]
                    check(bool(row["planPost"]) and bool(row["planId"]), "建行缺少计划或岗位标识")
                    detail = await self.session.request(
                        query(
                            detail_url,
                            planId=row["planId"],
                            planPost=row["planPost"],
                            planType=row["planType"],
                            orgId=row.get("secondOrgId") or row["orgId"],
                        ),
                        detail=True,
                    )
                    check(
                        str(detail.get("SUCCESS")).lower() == "true"
                        and str(detail.get("planPost")) == str(row["planPost"]),
                        "建行详情关联不一致",
                    )
                    self.result.jobs.append(
                        self.job(
                            ccb_key(row),
                            title=text(detail["planPostName"]),
                            unit=text(detail.get("orgName", row.get("orgName"))),
                            location=text(detail.get("cityName", row.get("workPlace"))),
                            education=text(detail.get("education")),
                            batch=text(detail.get("planName")),
                            published=text(detail.get("postDate")),
                            deadline=text(detail.get("endTime", row.get("endDate"))),
                            duties=text(detail.get("postDesc")),
                            requirements=text(detail.get("PostRequest")),
                            source_url=ccb_url(row),
                            field_sources={
                                "duties": "NHR107.postDesc",
                                "requirements": "NHR107.PostRequest",
                                "published": "NHR107.postDate",
                                "deadline": "NHR107.endTime or NHR104.endDate",
                            },
                        )
                    )
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, ccb_key(row))
                    if isinstance(exc, CrawlError) and exc.code in {
                        "request_budget",
                        "time_budget",
                        "access_denied",
                    }:
                        raise
            if page >= pages:
                scope.terminal = True
                break
            check(bool(rows), "建行分页提前返回空页")
            page += 1


class CNPC(Adapter):
    name = "cnpc"
    host = "zhaopin.cnpc.com.cn"
    path = "/web/recruitInfolist.html"
    scope_description = "高校毕业生 type=1 全部启事，每篇 post 数组展开为岗位；保留公告通用要求"

    async def harvest(self) -> None:
        observed = await self.session.observed("/recruitInfo/listN")
        values = parse_qs(urlsplit(observed["url"]).query)
        check(values.get("type") == ["1"], "中石油入口不是 type=1 高校毕业生")
        size = int(values["max"][0])
        check(size > 0, "无效中石油页大小")
        scope = Scope(name="campus-announcements", unit="招聘启事")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        offset = 0
        detail_url = ""
        while True:
            data = await self.session.request(query(observed["url"], offset=offset))
            expected = int(data["totals"])
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "中石油启事总数变化")
            rows = self.add_page(scope, data["recruitInfo"], seen, lambda row: str(row["id"]))
            if rows and not detail_url:
                await self.session.open(
                    f"https://{self.host}/recruitInfoshow.html?id={rows[0]['id']}"
                )
                detail_url = (await self.session.observed("/recruitInfo/showN"))["url"]
            for row in rows:
                try:
                    data = await self.session.request(
                        query(detail_url, recruitId=row["id"]), detail=True
                    )
                    common = data["recruitInfoObj"]
                    check(str(common["id"]) == str(row["id"]), "中石油公告详情关联不一致")
                    positions = data["post"]
                    check(isinstance(positions, list), "中石油公告岗位数组缺失")
                    ids: set[str] = set()
                    for position in positions:
                        identity = str(position["id"])
                        check(identity not in ids, "中石油同公告岗位 ID 重复")
                        ids.add(identity)
                        self.result.jobs.append(
                            self.job(
                                f"{row['id']}:{identity}",
                                title=text(position["postToString"]),
                                unit=text(data.get("companyIntroduceCompanyInfoCompanyName")),
                                location=text(position.get("workPlace")),
                                education=text(position.get("educationRequiredName")),
                                batch=text(common["recruitTitle"]),
                                published=text(data.get("time1")),
                                deadline=text(data.get("time2")),
                                requirements="\n".join(
                                    filter(
                                        None,
                                        [
                                            text(position.get("remark")),
                                            text(position.get("remark2")),
                                            text(position.get("foreignRequire")),
                                            text(position.get("professionDescribe")),
                                            text(common.get("qualificationDemand")),
                                            text(common.get("recruitStandard")),
                                        ],
                                    )
                                ),
                                source_url=f"https://{self.host}/recruitInfoshow.html?id={row['id']}",
                                field_sources={
                                    "requirements": "post[].remark/remark2/foreignRequire/professionDescribe + recruitInfoObj.qualificationDemand/recruitStandard",
                                    "published": "showN.time1",
                                    "deadline": "showN.time2",
                                },
                            )
                        )
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, str(row["id"]))
                    if isinstance(exc, CrawlError) and exc.code in {
                        "request_budget",
                        "time_budget",
                        "access_denied",
                    }:
                        raise
            offset += size
            if offset >= expected:
                scope.terminal = True
                break
            check(bool(rows), "中石油分页提前返回空页")


class Alibaba(Adapter):
    name = "alibaba"
    host = "campus-talent.alibaba.com"
    path = "/campus/position"
    scope_description = "graduate 正式校招全部批次，并检查阿里星目录是否为已采批次子集；不含实习"

    async def pages(
        self, url: str, payload: dict[str, Any], scope: Scope, *, emit: bool
    ) -> set[str]:
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        while True:
            response = await self.session.request(
                url, payload={**payload, "pageIndex": page, "pageSize": 100}
            )
            check(response.get("success") is True, "阿里列表业务失败")
            data = response["content"]
            expected = int(data["totalCount"])
            check(int(data["pageSize"]) > 0, "阿里分页大小无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "阿里批次岗位总数变化")
            rows = self.add_page(scope, data["datas"], seen, lambda row: str(row["id"]))
            for row in rows:
                try:
                    if emit:
                        self.result.jobs.append(
                            self.job(
                                f"{payload['batchId']}:{row['id']}",
                                title=text(row["name"]),
                                unit=text(row.get("circleNames")),
                                location=text(row.get("workLocations")),
                                education=text(row.get("degree")),
                                category_raw=text(row.get("categoryName")),
                                batch=text(row.get("batchName")),
                                published=text(row.get("publishTime")),
                                deadline=text(row.get("endTime")),
                                duties=text(row.get("description")),
                                requirements=text(row.get("requirement")),
                                source_url=f"https://{self.host}/campus/position/{row['id']}?deptCodes=",
                                field_sources={
                                    "duties": "datas[].description",
                                    "requirements": "datas[].requirement",
                                    "published": "datas[].publishTime",
                                },
                            )
                        )
                    scope.details += 1
                except Exception as exc:
                    self.error(exc, str(row.get("id")))
            if page >= math.ceil(expected / int(data["pageSize"])):
                scope.terminal = True
                break
            check(bool(rows), "阿里分页提前返回空页")
            page += 1
        return seen

    async def harvest(self) -> None:
        observed = await self.session.observed("/position/search?")
        condition = await self.session.observed("/searchCondition/listBatch?")
        batch_data = json.loads(condition["body"])["content"]["graduate"]
        check(isinstance(batch_data, list), "阿里 graduate 批次目录无效")
        catalog = Scope(
            name="graduate-batches",
            expected=len(batch_data),
            listed=len(batch_data),
            unique=len({str(b["id"]) for b in batch_data}),
            terminal=True,
            unit="招聘批次",
            evidence=[self.session.last_evidence],
        )
        self.result.scopes.append(catalog)
        payload = json.loads(observed["post_data"])
        all_ids: set[str] = set()
        for batch in batch_data:
            try:
                all_ids.update(
                    await self.pages(
                        observed["url"],
                        {**payload, "batchId": batch["id"]},
                        Scope(name=f"batch:{batch['id']}"),
                        emit=True,
                    )
                )
                catalog.details += 1
            except Exception as exc:
                self.error(exc, f"batch:{batch['id']}")
                if isinstance(exc, CrawlError) and exc.code in {
                    "request_budget",
                    "time_budget",
                    "access_denied",
                }:
                    raise
        await self.session.open(f"https://{self.host}/campus/alistar")
        config = await self.session.observed("new-campus-alistar/0.0.1/default.json")
        star_url = urljoin(
            f"https://{self.host}/campus/alistar", json.loads(config["body"])["common"]["btnUrl"]
        )
        check(urlsplit(star_url).hostname == self.host, "阿里星跳转到未声明平台")
        await self.session.open(star_url)
        star = await self.session.observed("/position/search?")
        star_ids = await self.pages(
            star["url"], json.loads(star["post_data"]), Scope(name="alistar-subset"), emit=False
        )
        check(star_ids <= all_ids, "阿里星包含普通批次未覆盖的岗位")
