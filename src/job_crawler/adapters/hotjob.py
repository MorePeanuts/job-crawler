"""Verified public Hotjob campus tenant contract (form POST APIs)."""

import json
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlencode

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections, strip_heading
from job_crawler.filtering import select
from job_crawler.models import Issue, Job, Scope
from job_crawler.transport import CrawlError


def detail_body(row: dict[str, Any]) -> tuple[str, str]:
    duties = text(row.get("workContent"))
    requirements = text(row.get("serviceCondition"))
    if requirements:
        return strip_heading(duties, "duties"), strip_heading(requirements, "requirements")
    return split_sections(duties)


def location_paths(provinces: list[dict[str, Any]]) -> dict[str, str]:
    paths: dict[str, str] = {}
    ambiguous: set[str] = set()
    for province in provinces:
        parent = text(province.get("nameCh"))
        for city in province.get("childNodes", []):
            name = text(city.get("nameCh"))
            if not parent or not name:
                continue
            path = f"{parent}/{name}"
            if name in paths and paths[name] != path:
                ambiguous.add(name)
            paths[name] = path
    return {name: path for name, path in paths.items() if name not in ambiguous}


class FormRequester(Protocol):
    async def request(
        self, url: str, *, form: dict[str, str], detail: bool = False
    ) -> dict[str, Any]: ...


class Hotjob(Adapter):
    host = "wecruit.hotjob.cn"
    suite = ""
    path = ""
    scope_description = "Hotjob 公开校园招聘 recruitType=1 全目录；逐条读取详情；不含社会招聘"

    def detail_page(self, post_id: str) -> str:
        return f"https://{self.host}/{self.suite}/pb/posDetail.html?" + urlencode(
            {"postId": post_id, "postType": "campus"}
        )

    async def harvest(self) -> None:
        requester = cast(FormRequester, self.session)
        observed = await self.session.observed("/positionInfo/listPosition/")
        check(f"/{self.suite}?" in observed["url"], "Hotjob 租户与列表接口不一致")
        values = parse_qs(observed.get("post_data") or "", keep_blank_values=True)
        check(values.get("recruitType") == ["1"], "Hotjob 目录不是校招")
        check(values.get("currentPage") == ["1"], "Hotjob 目录不是第一页")
        check(values.get("isFrompb") == ["true"], "Hotjob 门户类型改变")
        check(
            set(values) <= {"isFrompb", "recruitType", "pageSize", "currentPage"},
            "Hotjob 目录带有未知筛选",
        )
        size = int(values["pageSize"][0])
        check(0 < size <= 100, "Hotjob 分页大小异常")
        terms_observed = await self.session.observed("/positionInfo/listSearchTerm/")
        check(f"/{self.suite}?" in terms_observed["url"], "Hotjob 租户与地点树接口不一致")
        terms = json.loads(terms_observed["body"])
        check(terms.get("state") == "200", "Hotjob 地点树业务失败")
        provinces = terms["data"].get("provinceList", [])
        check(isinstance(provinces, list), "Hotjob 地点树结构改变")
        locations = location_paths(provinces)
        location_evidence = self.session.last_evidence
        if not provinces:
            self.result.warnings.append(
                Issue(
                    code="location_tree_missing",
                    message="源站未提供省市树；地点保留原文，单城市也不猜省份",
                    source_id=self.source.source_id,
                    url=self.source.url,
                )
            )
        scope = Scope(name="campus-recruit-type-1")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        detail_api = ""
        first_detail: dict[str, Any] | None = None
        first_detail_id = ""
        while True:
            response = await requester.request(
                observed["url"],
                form={
                    "isFrompb": "true",
                    "recruitType": "1",
                    "pageSize": str(size),
                    "currentPage": str(page),
                },
            )
            check(response.get("state") == "200", "Hotjob 列表业务失败")
            page_form = response["data"]["pageForm"]
            expected = int(page_form["dataCount"])
            pages = int(page_form["totalPage"])
            if expected == 0:
                check(
                    pages == 0
                    and not page_form["pageData"]
                    and int(page_form["currentPage"]) in {0, 1},
                    "Hotjob 空目录计数不一致",
                )
                scope.expected = 0
                scope.terminal = True
                break
            check(expected > 0 and pages > 0, "Hotjob 校招目录计数无效")
            check(int(page_form["currentPage"]) == page, "Hotjob 返回了错误页码")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "Hotjob 分页期间总数变化")
            rows = self.add_page(scope, page_form["pageData"], seen, lambda row: str(row["postId"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                post_id = str(row["postId"])
                try:
                    check(str(row["recruitType"]) == "1", "Hotjob 混入非校招岗位")
                    listing = self._job(row, row, list_evidence, locations, location_evidence)
                    if select(listing, "all", self.as_of).reason == "expired":
                        listing.detail_mode = "listing_only"
                        self.result.jobs.append(listing)
                        scope.skipped_expired += 1
                        continue
                    resolved = self.before_detail(
                        f"job:{post_id}", row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    if not detail_api:
                        await self.session.open(
                            self.detail_page(post_id),
                            ready_endpoints=("/wecruit/positionInfo/listPositionDetail/",),
                        )
                        detail_observed = await self.session.observed(
                            "/positionInfo/listPositionDetail/"
                        )
                        check(
                            f"/{self.suite}?" in detail_observed["url"],
                            "Hotjob 租户与详情接口不一致",
                        )
                        detail_api = detail_observed["url"]
                        first_detail = json.loads(detail_observed["body"])
                        first_detail_id = post_id
                        detail_evidence = self.session.last_evidence
                    else:
                        first_detail = None
                        detail_evidence = ""
                    detail = (
                        first_detail
                        if first_detail is not None and first_detail_id == post_id
                        else await requester.request(
                            detail_api,
                            form={"postId": post_id, "recruitType": "1"},
                            detail=True,
                        )
                    )
                    check(detail.get("state") == "200", "Hotjob 详情业务失败")
                    item = detail["data"]
                    check(str(item["postId"]) == post_id, "Hotjob 详情与列表 ID 不一致")
                    check(str(item["recruitType"]) == "1", "Hotjob 详情不是校招")
                    check("workContent" in item, "Hotjob 缺少详情正文")
                    job = self._job(
                        item,
                        row,
                        detail_evidence or self.session.last_evidence,
                        locations,
                        location_evidence,
                    )
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{post_id}", row, [job])
                except Exception as exc:
                    self.error(exc, post_id)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if page >= pages:
                scope.terminal = True
                break
            check(bool(rows), "Hotjob 分页提前为空")
            page += 1

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        post_id = str(row["postId"])
        is_detail = "workContent" in row
        duties, requirements = detail_body(row) if is_detail else ("", "")
        if is_detail and not requirements:
            self.result.warnings.append(
                Issue(
                    code="field_missing",
                    message="源站详情未提供任职要求",
                    source_id=self.source.source_id,
                    job_key=post_id,
                    url=self.detail_page(post_id),
                )
            )
        place = text(row.get("workPlaceStr") or listing.get("workPlaceStr"))
        mapped = locations.get(place)
        job = self.job(
            post_id,
            title=text(row.get("postName") or listing.get("postName")),
            unit=text(row.get("orgName") or row.get("company") or listing.get("company")),
            location=mapped or place,
            education=text(
                row.get("education") or row.get("educationStr") or listing.get("educationStr")
            ),
            category_raw=text(row.get("postTypeName") or listing.get("postTypeName")),
            batch=text(row.get("projectName") or listing.get("projectName")),
            duties=duties,
            requirements=requirements,
            published=text(
                row.get("publishFirstDate")
                or listing.get("publishFirstDate")
                or row.get("publishDate")
                or listing.get("publishDate")
            ),
            deadline=text(row.get("endDate") or listing.get("endDate")),
            source_url=self.detail_page(post_id),
            field_sources={
                "published": "publishFirstDate（首次发布时间）；缺失时回退 publishDate",
                "deadline": "listPositionDetail.data.endDate or listPosition.pageData[].endDate",
                "location": (
                    "listSearchTerm.data.provinceList + workPlaceStr"
                    if mapped
                    else "workPlaceStr；多城市或未确定省市路径，保留原文"
                ),
                **(
                    {
                        "duties": "listPositionDetail.data.workContent",
                        "requirements": (
                            "listPositionDetail.data.serviceCondition"
                            if text(row.get("serviceCondition"))
                            else (
                                "listPositionDetail.data.workContent:【任职资格/任职要求】"
                                if requirements
                                else "source_missing:serviceCondition"
                            )
                        ),
                    }
                    if is_detail
                    else {"detail": "listing_only"}
                ),
            },
        )
        job.evidence = [path for path in (evidence, location_evidence if mapped else "") if path]
        return job


class HuaXia(Hotjob):
    name = "hotjob-huaxia"
    suite = "SU645b0d18bef57c0907e9fbc8"
    path = f"/{suite}/pb/school.html"


class JinTian(Hotjob):
    name = "hotjob-jintian"
    suite = "SU61d79b670dcad45571bada7b"
    path = f"/{suite}/pb/school.html"


class GF(Hotjob):
    name = "hotjob-gf"
    suite = "SU625527c30dcad4021443cdda"
    path = f"/{suite}/pb/school.html"


class LiuGong(Hotjob):
    name = "hotjob-liugong"
    suite = "SU6132e87abef57c3b637dcb71"
    path = f"/{suite}/pb/school.html"


class HaiTian(Hotjob):
    name = "hotjob-haitian"
    suite = "SU6322dfb70dcad46a862da4c5"
    path = f"/{suite}/pb/school.html"


class Minth(Hotjob):
    name = "hotjob-minth"
    suite = "SU61304acdbef57c061649be2e"
    path = f"/{suite}/pb/school.html"


class Yutong(Hotjob):
    name = "hotjob-yutong"
    suite = "SU64e7157a1eb80519a8e4efcf"
    path = f"/{suite}/mc/position/campus"


class ZhengzhouBank(Hotjob):
    name = "hotjob-zzbank"
    host = "zzbankcampus.hotjob.cn"
    suite = "SU64f952b41eb8051fabaed066"
    path = f"/{suite}/pb/school.html"


class Cmoc(Hotjob):
    name = "hotjob-cmoc"
    suite = "SU67e513c01c240e188726a2e9"
    path = f"/{suite}/pb/school.html"

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        job = super()._job(row, listing, evidence, locations, location_evidence)
        if "实习" in job.title or "实习" in job.batch:
            job.work_type = "实习"
        return job


class CountryGarden(Hotjob):
    name = "hotjob-countrygarden"
    suite = "SU5fe5ad319b0d78e6f422f6f8"
    path = f"/{suite}/pb/school.html"


class Baiyao(Cmoc):
    name = "hotjob-baiyao"
    suite = "SU6136b970bef57c3b638162c4"
    path = f"/{suite}/pb/school.html"


class Huayou(Cmoc):
    name = "hotjob-huayou"
    suite = "SU6465f3d9bef57c0907f3bb58"
    path = f"/{suite}/pb/school.html"
    scope_description = "华友钴业校园 recruitType=1 全目录；实习生和校园大使项目由公共筛选排除"

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        job = super()._job(row, listing, evidence, locations, location_evidence)
        if "校园大使" in job.title or "校园大使" in job.batch:
            job.work_type = "校园大使"
        return job


TENANTS = (
    Huayou,
    Baiyao,
    HuaXia,
    JinTian,
    GF,
    LiuGong,
    HaiTian,
    Minth,
    Yutong,
    ZhengzhouBank,
    CountryGarden,
    Cmoc,
)
