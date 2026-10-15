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
    mobile_mode = False
    scope_description = "Hotjob 公开校园招聘 recruitType=1 全目录；逐条读取详情；不含社会招聘"

    def detail_page(self, post_id: str) -> str:
        if self.mobile_mode:
            return f"https://{self.host}/{self.suite}/mc/detail?" + urlencode(
                {"postId": post_id, "recruitType": "campus", "distance": "0"}
            )
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
        if self.mobile_mode:
            check(
                set(values)
                <= {"recruitType", "pageSize", "currentPage", "coordinateLat", "coordinateLng"}
                and values.get("coordinateLat") == [""]
                and values.get("coordinateLng") == [""],
                "Hotjob 移动目录带有未知筛选或位置坐标",
            )
        else:
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
        self.validate_terms(terms["data"])
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
        size_corrected = False
        detail_api = ""
        first_detail: dict[str, Any] | None = None
        first_detail_id = ""
        while True:
            form = {
                "recruitType": "1",
                "pageSize": str(size),
                "currentPage": str(page),
            }
            if self.mobile_mode:
                form.update({"coordinateLat": "", "coordinateLng": ""})
            else:
                form["isFrompb"] = "true"
            response = await requester.request(observed["url"], form=form)
            check(response.get("state") == "200", "Hotjob 列表业务失败")
            page_form = response["data"]["pageForm"]
            expected = int(page_form["dataCount"])
            pages = int(page_form["totalPage"])
            returned_size = int(page_form.get("pageSize", size))
            check(0 < returned_size <= 100, "Hotjob 返回的分页大小无效")
            if returned_size != size:
                check(
                    page == 1 and scope.expected is None and not size_corrected,
                    "Hotjob 分页大小中途变化或反复变化",
                )
                size = returned_size
                size_corrected = True
                continue
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
                    if not self.include_listing(row):
                        scope.skipped_out_of_scope += 1
                        continue
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

    def validate_terms(self, data: dict[str, Any]) -> None:
        """Tenant-specific institution tree checks, if required."""

    def include_listing(self, row: dict[str, Any]) -> bool:
        """Return false only for a proven, explicitly counted other legal entity."""
        return True

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


class Skyworth(Hotjob):
    name = "hotjob-skyworth"
    host = "skyworth.hotjob.cn"
    suite = "SU668b8b251c240e2e76ea71d8"
    path = f"/{suite}/pb/school.html"
    scope_description = "创维集团 2027 校招 recruitType=1 全目录；核对列表公司字段"

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        check(text(listing.get("company")) == "创维集团有限公司", "创维列表所属公司变化")
        return super()._job(row, listing, evidence, locations, location_evidence)


class Huatai(Hotjob):
    name = "hotjob-huatai"
    suite = "SU6419745cbef57c635fe10142"
    path = f"/{suite}/pb/school.html"
    scope_description = "华泰证券校园目录全量；机构树划分总部与分公司，明确排除子公司"

    def validate_terms(self, data: dict[str, Any]) -> None:
        roots = {str(item["code"]): item for item in data.get("orgList", [])}
        check(
            {code: text(item.get("nameCh")) for code, item in roots.items()}
            == {"0/80": "总部部门", "0/100102": "子公司", "0/100103": "分公司"},
            "华泰机构树法人分支变化",
        )
        self._org_total = sum(int(item["positionsNum"]) for item in roots.values())
        self._other_legal_total = int(roots["0/100102"]["positionsNum"])

    def include_listing(self, row: dict[str, Any]) -> bool:
        code = text(row.get("orgCode"))
        check(
            code in {"0/80", "0/100102", "0/100103"}
            or code.startswith(("0/80/", "0/100102/", "0/100103/")),
            "华泰岗位机构编码超出已核对法人分支",
        )
        return not code.startswith("0/100102/")

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(scope.expected == self._org_total, "华泰机构树与目录总数不符")
        check(
            scope.skipped_out_of_scope == self._other_legal_total,
            "华泰子公司目录计数不符",
        )


class Tbea(Hotjob):
    name = "hotjob-tbea"
    suite = "SU612f55eebef57c0616450aa2"
    path = f"/{suite}/pb/school.html"
    scope_description = "特变电工集团校招目录全量；仅特变总部与明确的股份公司直属岗位归本主体"

    def validate_terms(self, data: dict[str, Any]) -> None:
        roots = {str(item["code"]): item for item in data.get("orgList", [])}
        check(
            "0/3" in roots and text(roots["0/3"].get("nameCh")) == "特变总部",
            "特变机构树缺少上市公司总部",
        )
        self._root_codes = set(roots)
        self._tree_total = sum(int(item["positionsNum"]) for item in roots.values())
        self._other_total = sum(
            int(item["positionsNum"]) for code, item in roots.items() if code != "0/3"
        )
        self._direct_company_count = 0

    def include_listing(self, row: dict[str, Any]) -> bool:
        code = text(row.get("orgCode"))
        root = "/".join(code.split("/")[:2])
        if root == "0/3":
            return True
        if root in self._root_codes:
            return False
        check(
            text(row.get("company")) == "特变电工股份有限公司",
            "特变未知机构岗位未注明上市法人",
        )
        self._direct_company_count += 1
        return True

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(
            scope.expected == self._tree_total + self._direct_company_count,
            "特变机构树与直属上市公司岗位不闭合",
        )
        check(scope.skipped_out_of_scope == self._other_total, "特变其他机构计数不符")


class TclIndustries(Hotjob):
    name = "hotjob-tcl-industries"
    suite = "SU64893571bef57c16d356b99e"
    path = f"/{suite}/pb/school.html"
    scope_description = "TCL 共享校园目录全量；机构树仅 0/41 TCL 实业岗位归本主体"

    def validate_terms(self, data: dict[str, Any]) -> None:
        roots = {str(item["code"]): item for item in data.get("orgList", [])}
        check(
            {code: text(item.get("nameCh")) for code, item in roots.items()}
            == {"0/1": "TCL科技", "0/41": "TCL实业", "0/36": "TCL财务共享中心"},
            "TCL 校招机构树顶层分支变化",
        )
        self._total = sum(int(item["positionsNum"]) for item in roots.values())
        self._other_total = sum(
            int(item["positionsNum"]) for code, item in roots.items() if code != "0/41"
        )

    def include_listing(self, row: dict[str, Any]) -> bool:
        code = text(row.get("orgCode"))
        root = "/".join(code.split("/")[:2])
        check(root in {"0/1", "0/41", "0/36"}, "TCL 岗位机构超出已核对法人分支")
        return root == "0/41"

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(scope.expected == self._total, "TCL 校招机构树与目录总数不符")
        check(scope.skipped_out_of_scope == self._other_total, "TCL 其他机构计数不符")


class Goertek(Hotjob):
    name = "hotjob-goertek"
    host = "goertek.hotjob.cn"
    suite = "SU65dd9ebd1c240e4b11c4f491"
    path = f"/{suite}/pb/school.html"
    scope_description = "歌尔公开校招目录全量；仅列表标明「歌尔股份」的岗位归本主体"

    def include_listing(self, row: dict[str, Any]) -> bool:
        company = text(row.get("company"))
        check(bool(company), "歌尔岗位缺少所属公司")
        return company == "歌尔股份"


class Luxshare(Hotjob):
    name = "hotjob-luxshare"
    suite = "SU601778b25d83dc072073230a"
    path = f"/{suite}/pb/school.html"
    scope_description = "立讯共享校招目录全量；仅机构 0/36 立讯精密工业股份归本主体"

    def validate_terms(self, data: dict[str, Any]) -> None:
        roots = {str(item["code"]): item for item in data.get("orgList", [])}
        self._names = {
            "0/36": "立讯精密工业股份",
            "0/45": "华南园区",
            "0/44": "华东园区",
            "0/210201": "京西国际",
        }
        check(
            {code: text(item.get("nameCh")) for code, item in roots.items()} == self._names,
            "立讯校招机构树分支变化",
        )
        self._total = sum(int(item["positionsNum"]) for item in roots.values())
        self._other_total = sum(
            int(item["positionsNum"]) for code, item in roots.items() if code != "0/36"
        )

    def include_listing(self, row: dict[str, Any]) -> bool:
        code = text(row.get("orgCode"))
        check(code in self._names, "立讯岗位机构编码超出已核对分支")
        check(text(row.get("company")) == self._names[code], "立讯岗位机构名称不一致")
        return code == "0/36"

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(scope.expected == self._total, "立讯机构树与目录总数不符")
        check(scope.skipped_out_of_scope == self._other_total, "立讯其他机构计数不符")


class EveEnergy(Hotjob):
    name = "hotjob-eve-energy"
    suite = "SU630487ca0dcad45aa7768a79"
    path = f"/{suite}/pb/school.html"
    scope_description = "亿纬锂能校招全目录；仅 0/108547 惠州本部岗位归上市主体"

    def include_listing(self, row: dict[str, Any]) -> bool:
        code = text(row.get("orgCode"))
        check(code in {"0", "0/108547", "0/108528/106673"}, "亿纬机构编码变化")
        if code != "0/108547":
            return False
        check(
            text(row.get("company")) == "亿纬锂能" and text(row.get("workPlaceStr")) == "惠州市",
            "亿纬本部岗位主体或地点变化",
        )
        return True

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        if "workContent" in row:
            check(
                text(row.get("orgCode")) == "0/108547"
                and text(row.get("company")) == "亿纬锂能"
                and text(row.get("orgName")) == "亿纬锂能"
                and text(row.get("workPlaceStr")) == "惠州市",
                "亿纬详情机构或地点与本部不符",
            )
        return super()._job(row, listing, evidence, locations, location_evidence)


class Zoomlion2027(Hotjob):
    name = "hotjob-zoomlion-2027"
    suite = "SU661f37091eb8053acd6cdf3d"
    path = f"/{suite}/mc/position/campus"
    mobile_mode = True
    scope_description = "中联重科 2027 移动校招目录；排除中科云谷机器人方向，只收本级岗位"

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(
            text(row.get("projectName")) == "中联重科2027届校招"
            and str(row.get("projectId")) == "128002"
            and text(row.get("company")) == "中联重科股份有限公司"
            and text(row.get("orgCode")) == "0/100001",
            "中联重科列表项目或机构身份变化",
        )
        return "机器人" not in text(row.get("postName"))

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        if "workContent" in row:
            check(
                str(row.get("postId")) == str(listing.get("postId"))
                and text(row.get("postName")) == text(listing.get("postName"))
                and text(row.get("orgName")) == "中联重科股份有限公司"
                and text(row.get("company")) == "中联重科股份有限公司"
                and text(row.get("orgCode")) == "0/100001"
                and str(row.get("projectId")) == "128002",
                "中联重科详情与列表或本级主体不符",
            )
        return super()._job(row, listing, evidence, locations, location_evidence)


class SinomachHeadquarters(Hotjob):
    name = "hotjob-sinomach-headquarters"
    host = "zhaopin.sinomach.com.cn"
    suite = "SU64b60d25bef57c7e363ff1a3"
    path = f"/{suite}/mc/position/campus"
    mobile_mode = True
    scope_description = "国机集团2027届校招全目录；仅国机集团总部 0/2688 分支"
    headquarters_expected = 0

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(
            scope.unique - scope.skipped_out_of_scope == self.headquarters_expected,
            "国机集团总部岗位数与机构树不一致",
        )

    def validate_terms(self, data: dict[str, Any]) -> None:
        orgs = data.get("orgList")
        if not isinstance(orgs, list):
            raise CrawlError("schema_changed", "国机集团机构树缺失")
        headquarters = [
            org for org in orgs if isinstance(org, dict) and str(org.get("code")) == "0/2688"
        ]
        check(
            len(headquarters) == 1
            and text(headquarters[0].get("nameCh")) == "国机集团总部"
            and int(headquarters[0].get("positionsNum", 0)) > 0,
            "国机集团总部机构分支改变或为空",
        )
        self.headquarters_expected = int(headquarters[0]["positionsNum"])

    def include_listing(self, row: dict[str, Any]) -> bool:
        company = text(row.get("company"))
        org_code = text(row.get("orgCode"))
        is_headquarters = company == "国机集团总部"
        check(
            is_headquarters == org_code.startswith("0/2688/"),
            "国机集团列表机构名称与编码不一致",
        )
        return is_headquarters

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        if "workContent" in row:
            check(
                str(row.get("postId")) == str(listing.get("postId"))
                and text(row.get("postName")) == text(listing.get("postName"))
                and text(row.get("company")) == "国机集团总部"
                and text(row.get("orgCode")) == text(listing.get("orgCode"))
                and text(row.get("projectName")) == text(listing.get("projectName")),
                "国机集团总部详情与列表或机构不符",
            )
        return super()._job(row, listing, evidence, locations, location_evidence)


class Wanhua2027(Hotjob):
    name = "hotjob-wanhua-2027"
    suite = "SU6a7ad69c43154813049755d7"
    path = f"/{suite}/pb/school.html"
    scope_description = "万华化学2027校招全目录；逐条验证本级法人和招聘项目"

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(
            text(row.get("company")) == "万华化学集团股份有限公司"
            and text(row.get("orgCode")) == "0"
            and text(row.get("projectName")) == "本硕博招聘"
            and str(row.get("projectId")) == "100001",
            "万华化学列表法人或招聘项目变化",
        )
        return True

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        locations: dict[str, str],
        location_evidence: str,
    ) -> Job:
        if "workContent" in row:
            check(
                str(row.get("postId")) == str(listing.get("postId"))
                and text(row.get("postName")) == text(listing.get("postName"))
                and text(row.get("company")) == "万华化学集团股份有限公司"
                and text(row.get("orgName")) == "万华化学集团股份有限公司"
                and text(row.get("orgCode")) == "0"
                and text(row.get("projectName")) == "本硕博招聘"
                and str(row.get("projectId")) == "100001",
                "万华化学详情与列表或本级主体不符",
            )
        return super()._job(row, listing, evidence, locations, location_evidence)


TENANTS = (
    SinomachHeadquarters,
    Wanhua2027,
    Zoomlion2027,
    EveEnergy,
    Luxshare,
    Goertek,
    TclIndustries,
    Tbea,
    Huatai,
    Skyworth,
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
