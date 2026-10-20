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
    recruit_type = "1"
    route_type = "campus"
    scope_description = "Hotjob 公开校园招聘 recruitType=1 全目录；逐条读取详情；不含社会招聘"

    def detail_page(self, post_id: str) -> str:
        if self.mobile_mode:
            return f"https://{self.host}/{self.suite}/mc/detail?" + urlencode(
                {"postId": post_id, "recruitType": self.route_type, "distance": "0"}
            )
        return f"https://{self.host}/{self.suite}/pb/posDetail.html?" + urlencode(
            {"postId": post_id, "postType": "campus"}
        )

    async def harvest(self) -> None:
        requester = cast(FormRequester, self.session)
        observed = await self.session.observed("/positionInfo/listPosition/")
        check(f"/{self.suite}?" in observed["url"], "Hotjob 租户与列表接口不一致")
        values = parse_qs(observed.get("post_data") or "", keep_blank_values=True)
        check(values.get("recruitType") == [self.recruit_type], "Hotjob 目录不是校招")
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
        scope = Scope(name=f"campus-recruit-type-{self.recruit_type}")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 1
        size_corrected = False
        detail_api = ""
        first_detail: dict[str, Any] | None = None
        first_detail_id = ""
        while True:
            form = {
                "recruitType": self.recruit_type,
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
            if expected == 0:
                check(
                    pages == 0
                    and 0 <= returned_size <= 100
                    and not page_form["pageData"]
                    and int(page_form["currentPage"]) in {0, 1},
                    "Hotjob 空目录计数不一致",
                )
                scope.evidence.extend([location_evidence, self.session.last_evidence])
                scope.expected = 0
                scope.terminal = True
                break
            check(0 < returned_size <= 100, "Hotjob 返回的分页大小无效")
            if returned_size != size:
                check(
                    page == 1 and scope.expected is None and not size_corrected,
                    "Hotjob 分页大小中途变化或反复变化",
                )
                size = returned_size
                size_corrected = True
                continue
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
                    check(str(row["recruitType"]) == self.recruit_type, "Hotjob 混入非校招岗位")
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
                            form={"postId": post_id, "recruitType": self.recruit_type},
                            detail=True,
                        )
                    )
                    check(detail.get("state") == "200", "Hotjob 详情业务失败")
                    item = detail["data"]
                    check(str(item["postId"]) == post_id, "Hotjob 详情与列表 ID 不一致")
                    check(str(item["recruitType"]) == self.recruit_type, "Hotjob 详情不是校招")
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
    mobile_mode = True
    scope_description = (
        "宇通官方移动校园 recruitType=1 与博士 recruitType=12 双目录；不含独立实习目录"
    )

    async def harvest(self) -> None:
        for recruit_type, route_type in (("1", "campus"), ("12", "intern")):
            self.recruit_type = recruit_type
            self.route_type = route_type
            try:
                await self.session.open(
                    f"https://{self.host}/{self.suite}/mc/position/{route_type}",
                    ready_endpoints=("/positionInfo/listPosition/",),
                )
                await super().harvest()
            except Exception as exc:
                self.error(exc, f"recruit-type:{recruit_type}")


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


class SinomachGroup(Hotjob):
    name = "hotjob-sinomach-group"
    version = "3"
    host = "zhaopin.sinomach.com.cn"
    suite = "SU64b60d25bef57c7e363ff1a3"
    path = f"/{suite}/mc/position/campus"
    mobile_mode = True
    scope_description = "国机集团2027届校招门户全目录，含总部及成员企业；实际招聘单位保留在 unit"
    tree_expected = 0
    org_codes: set[str]

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(
            scope.expected == self.tree_expected and scope.unique == self.tree_expected,
            "国机集团校招目录与机构树岗位数不一致",
        )

    def validate_terms(self, data: dict[str, Any]) -> None:
        orgs = data.get("orgList")
        if not isinstance(orgs, list):
            raise CrawlError("schema_changed", "国机集团机构树缺失")
        self.org_codes = set()
        self.tree_expected = 0

        def add_node(node: dict[str, Any]) -> None:
            code = text(node.get("code"))
            check(bool(code) and code not in self.org_codes, "国机集团机构编码缺失或重复")
            self.org_codes.add(code)
            children = node.get("childNodes", [])
            check(isinstance(children, list), "国机集团机构子节点结构变化")
            for child in children:
                check(isinstance(child, dict), "国机集团机构子节点结构变化")
                add_node(child)

        for root in orgs:
            check(isinstance(root, dict), "国机集团顶层机构结构变化")
            code = text(root.get("code"))
            check(code.startswith("0/") and code.count("/") == 1, "国机集团顶层机构编码变化")
            check(bool(text(root.get("nameCh"))), "国机集团顶层机构名称缺失")
            count = int(root.get("positionsNum", -1))
            check(count >= 0, "国机集团顶层机构岗位数无效")
            self.tree_expected += count
            add_node(root)
        check(bool(orgs) and self.tree_expected > 0, "国机集团机构树为空")

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(bool(text(row.get("company"))), "国机集团岗位缺少实际招聘单位")
        check(text(row.get("orgCode")) in self.org_codes, "国机集团岗位机构超出门户机构树")
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
                and text(row.get("company")) == text(listing.get("company"))
                and text(row.get("orgCode")) == text(listing.get("orgCode"))
                and text(row.get("projectName")) == text(listing.get("projectName")),
                "国机集团详情与列表或招聘单位不符",
            )
        job = super()._job(row, listing, evidence, locations, location_evidence)
        company = text(row.get("company") or listing.get("company"))
        department = text(row.get("orgName"))
        job.unit = f"{company} / {department}" if department and department != company else company
        job.field_sources["unit"] = "listPosition.company + listPositionDetail.orgName"
        project = text(row.get("projectName") or listing.get("projectName"))
        work_type = text(row.get("workTypeStr") or listing.get("workTypeStr"))
        job.work_type = (
            "实习"
            if "实习" in project or "见习" in project or "实习" in work_type
            else "兼职"
            if "兼职" in work_type
            else "校招"
        )
        job.field_sources["work_type"] = "listPosition.projectName + workTypeStr"
        return job


class MinmetalsGroup(SinomachGroup):
    name = "hotjob-minmetals-group"
    version = "1"
    host = "wecruit.hotjob.cn"
    suite = "SU62f37858bef57c29ead8adab"
    path = f"/{suite}/pb/school.html"
    mobile_mode = False
    scope_description = "中国五矿集团2027届校招门户全目录，含总部及成员企业；逐岗保留实际招聘单位"

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(bool(text(row.get("company"))), "中国五矿岗位缺少实际招聘单位")
        code = text(row.get("orgCode"))
        root = "/".join(code.split("/")[:2])
        check(root in self.org_codes, "中国五矿岗位不属于招聘门户顶层机构")
        return True


class HengyiGroup(SinomachGroup):
    name = "hotjob-hengyi-group"
    version = "1"
    host = "wecruit.hotjob.cn"
    suite = "SU64a650e3bef57c3af72089fb"
    path = f"/{suite}/mc/position/campus"
    mobile_mode = True
    scope_description = "恒逸集团2027届校招完整目录，含集团本部及成员企业；保留实际招聘单位"

    def validate_terms(self, data: dict[str, Any]) -> None:
        super().validate_terms(data)
        roots = {text(row.get("code")): text(row.get("nameCh")) for row in data["orgList"]}
        check(
            roots == {"0/3": "浙江恒逸集团有限公司", "0/4": "恒逸石化股份有限公司"},
            "恒逸集团机构树顶层法人变化",
        )

    def include_listing(self, row: dict[str, Any]) -> bool:
        project = (str(row.get("projectId")), text(row.get("projectName")))
        check(
            project
            in {
                ("100901", "2027届校园招聘"),
                ("100001", "校园招聘"),
                ("100701", "新疆项目"),
                ("101801", "文莱二期项目"),
                ("0", "日常招聘"),
            },
            "恒逸集团校招项目变化",
        )
        return super().include_listing(row) and project != ("0", "日常招聘")


class CrrcGroup(MinmetalsGroup):
    name = "hotjob-crrc-group"
    version = "1"
    host = "crrc.hotjob.cn"
    suite = "SU64d47c466202cc36e27a52d4"
    path = f"/{suite}/pb/school.html"
    scope_description = "中国中车集团2027届校招门户全目录，含55个顶层招聘机构；逐岗保留实际单位"


class ChanghongListed(MinmetalsGroup):
    name = "hotjob-changhong-listed-campus"
    host = "zhaopin.changhong.com"
    suite = "SU6886eae30287e94ac767de53"
    path = f"/{suite}/pb/school.html"
    own_root = "0/100201/103713"
    scope_description = "长虹官方集团全校招目录，仅四川长虹电器股份有限公司机构树分支及其后代"

    def validate_terms(self, data: dict[str, Any]) -> None:
        super().validate_terms(data)
        roots = data["orgList"]
        check(
            len(roots) == 1
            and roots[0]["code"] == "0/100201"
            and text(roots[0]["nameCh"]) == "四川长虹电子控股集团有限公司",
            "长虹集团根机构身份变化",
        )
        nodes = [node for node in roots[0]["childNodes"] if node["code"] == self.own_root]
        check(
            len(nodes) == 1 and text(nodes[0]["nameCh"]) == "四川长虹电器股份有限公司",
            "四川长虹股份机构树节点缺失或身份变化",
        )
        self.own_expected = int(nodes[0]["positionsNum"])
        check(0 <= self.own_expected <= self.tree_expected, "长虹股份分支岗位数量异常")

    def include_listing(self, row: dict[str, Any]) -> bool:
        super().include_listing(row)
        code = text(row.get("orgCode"))
        check("/".join(code.split("/")[:3]) in self.org_codes, "长虹岗位所属一级板块未知")
        return code == self.own_root or code.startswith(self.own_root + "/")

    async def harvest(self) -> None:
        await super().harvest()
        scope = self.result.scopes[0]
        check(
            scope.skipped_out_of_scope == self.tree_expected - self.own_expected,
            "长虹股份与集团其他单位的岗位数量未闭合",
        )


class GwmListed(MinmetalsGroup):
    name = "hotjob-gwm-listed"
    version = "1"
    host = "zhaopin.gwm.cn"
    suite = "SU692d37b4ea11b01b6c54e0e5"
    path = f"/{suite}/pb/school.html"
    scope_description = "长城汽车集团门户完整校招目录；仅提取机构树 0/14 上市主体岗位"

    def validate_terms(self, data: dict[str, Any]) -> None:
        super().validate_terms(data)
        roots = data["orgList"]
        check(
            any(
                text(row.get("code")) == "0/14"
                and text(row.get("nameCh")) == "长城汽车股份有限公司"
                and int(row.get("positionsNum", 0)) > 0
                for row in roots
            ),
            "长城汽车上市主体机构树缺失",
        )

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(bool(text(row.get("company"))), "长城汽车岗位缺少实际招聘单位")
        code = text(row.get("orgCode"))
        root = "/".join(code.split("/")[:2])
        check(root in self.org_codes, "长城汽车岗位超出机构树")
        return root == "0/14"


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


class HualuHengshengCampus(Hotjob):
    name = "hotjob-hualuhengsheng-campus"
    suite = "SU69b20f3e10919a570b6a96a0"
    path = f"/{suite}/pb/school.html"
    scope_description = "华鲁恒升股份及荆州子公司官方校园门户完整目录；不含华鲁集团其他兄弟单位"


class BbmgCampus(Hotjob):
    name = "hotjob-bbmg-campus"
    suite = "SU62d139692f9d2470a6e6e052"
    path = f"/{suite}/pb/school.html"


class DbnCampus(Hotjob):
    name = "hotjob-dbn-campus"
    suite = "SU66ab37a71c240e2e76256280"
    path = f"/{suite}/pb/school.html"
    scope_description = "大北农官网统一校园招聘（应届生）全目录；保留分子公司及区域单位原名"

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(
            bool(text(row.get("company"))) and bool(text(row.get("orgCode"))),
            "大北农列表缺少招聘单位或组织编码",
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
                text(row.get("postName")) == text(listing.get("postName"))
                and text(row.get("orgCode")) == text(listing.get("orgCode"))
                and text(row.get("company")) == text(listing.get("company")),
                "大北农详情标题、招聘单位或组织编码与列表不一致",
            )
        job = super()._job(row, listing, evidence, locations, location_evidence)
        company = text(listing.get("company"))
        department = text(row.get("orgName"))
        job.unit = f"{company} / {department}" if department and department != company else company
        job.field_sources["unit"] = "company为招聘公司；不同的orgName作为所属部门一并保留"
        job.published = text(row.get("publishFirstDate") or listing.get("publishFirstDate"))
        job.field_sources["published"] = "publishFirstDate；缺失保留未知，不使用publishDate更新日期"
        return job


class FarEastListedCampus(Hotjob):
    name = "hotjob-fareast-listed-campus"
    suite = "SU641d034b2f9d246c37bb1704"
    path = f"/{suite}/pb/school.html"
    scope_description = "远东集团校园全目录；仅机构树0/9/39远东智慧能源上市分支及所属单位"
    own_root = "0/9/39"

    def validate_terms(self, data: dict[str, Any]) -> None:
        roots = data.get("orgList", [])
        check(
            len(roots) == 1
            and roots[0].get("code") == "0/9"
            and roots[0].get("nameCh") == "远东控股集团有限公司",
            "远东集团根机构身份变化",
        )
        self._nodes: dict[str, tuple[str, int]] = {}

        def visit(node: dict[str, Any], parent: str = "") -> None:
            code, name = text(node.get("code")), text(node.get("nameCh"))
            check(
                bool(name)
                and code not in self._nodes
                and (not parent or code.startswith(parent + "/")),
                "远东机构树身份重复或层级异常",
            )
            count = int(node["positionsNum"])
            check(count >= 0, "远东机构岗位数量异常")
            self._nodes[code] = name, count
            for child in node.get("childNodes", []):
                visit(child, code)

        visit(roots[0])
        check(
            self.own_root in self._nodes
            and self._nodes[self.own_root][0] == "远东智慧能源股份有限公司",
            "远东上市分支缺失或身份变化",
        )
        self._counts = dict.fromkeys(self._nodes, 0)

    def include_listing(self, row: dict[str, Any]) -> bool:
        code = text(row.get("orgCode"))
        ancestors = [key for key in self._nodes if code == key or code.startswith(key + "/")]
        check(bool(ancestors), "远东岗位超出机构树")
        nearest = max(ancestors, key=len)
        check(text(row.get("company")) == self._nodes[nearest][0], "远东岗位所属公司不符")
        for key in ancestors:
            self._counts[key] += 1
        return self.own_root in ancestors

    async def harvest(self) -> None:
        await super().harvest()
        check(
            all(self._counts[key] == count for key, (_, count) in self._nodes.items()),
            "远东机构树各级岗位计数不闭合",
        )
        scope = self.result.scopes[0]
        check(
            scope.expected == self._nodes["0/9"][1]
            and scope.skipped_out_of_scope == self._nodes["0/9"][1] - self._nodes[self.own_root][1],
            "远东上市分支与母集团排除计数不符",
        )

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
                all(
                    text(row.get(key)) == text(listing.get(key))
                    for key in ("postName", "company", "orgCode")
                ),
                "远东详情标题、公司或机构编码与列表不符",
            )
        job = super()._job(row, listing, evidence, locations, location_evidence)
        company = text(listing.get("company"))
        department = text(row.get("orgName") or listing.get("department"))
        job.unit = f"{company} / {department}" if department and department != company else company
        job.field_sources["unit"] = "company为招聘公司，orgName/department为所属部门"
        job.published = text(row.get("publishFirstDate") or listing.get("publishFirstDate"))
        job.field_sources["published"] = "publishFirstDate；缺失保留未知，不使用publishDate更新日期"
        return job


class Lining2027(Hotjob):
    name = "hotjob-lining-2027"
    suite = "SU6018f8695d83dc072073e990"
    path = f"/{suite}/pb/school.html"
    scope_description = "李宁官方 Hotjob 校园频道全目录；仅纳入 2027校园招聘项目"

    def include_listing(self, row: dict[str, Any]) -> bool:
        check(bool(text(row.get("company"))), "李宁岗位缺少所属业务单元")
        project = text(row.get("projectName"))
        check(bool(project), "李宁岗位缺少校招项目名称")
        return project == "2027校园招聘"

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
                all(
                    text(row.get(key)) == text(listing.get(key))
                    for key in ("postId", "postName", "company", "projectName")
                ),
                "李宁详情 ID、标题、业务单元或项目与列表不符",
            )
        job = super()._job(row, listing, evidence, locations, location_evidence)
        job.published = text(row.get("publishFirstDate") or listing.get("publishFirstDate"))
        job.field_sources["published"] = "首次发布日期 publishFirstDate；不使用更新日 publishDate"
        return job


class GpcHeadquarters2027(Hotjob):
    name = "hotjob-gpc-headquarters-2027"
    suite = "SU6a94e5b85e09b14b274b6888"
    path = f"/{suite}/pb/school.html"
    scope_description = "广药集团官方校园频道全目录；只纳入广州医药集团总部法人岗位"
    headquarters = "广州医药集团有限公司（总部）"
    headquarters_code = "0/122736"

    def validate_terms(self, data: dict[str, Any]) -> None:
        roots = data.get("orgList")
        check(isinstance(roots, list), "广药校园招聘机构树缺失")
        assert isinstance(roots, list)
        headquarters = [root for root in roots if root.get("code") == self.headquarters_code]
        check(
            len(headquarters) == 1
            and headquarters[0].get("nameCh") == self.headquarters
            and int(headquarters[0].get("positionsNum", 0)) > 0,
            "广药集团总部机构代码或岗位数变化",
        )

    def include_listing(self, row: dict[str, Any]) -> bool:
        company = text(row.get("company"))
        code = text(row.get("orgCode"))
        check(bool(company and code), "广药校园岗位缺少所属公司或机构编码")
        if company != self.headquarters:
            check(not code.startswith(self.headquarters_code + "/"), "广药总部机构混入其他公司")
            return False
        check(code.startswith(self.headquarters_code + "/"), "广药总部岗位机构代码错配")
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
                all(
                    text(row.get(key)) == text(listing.get(key))
                    for key in ("postName", "company", "orgCode")
                ),
                "广药详情标题、公司或机构编码与列表不符",
            )
        job = super()._job(row, listing, evidence, locations, location_evidence)
        department = text(row.get("orgName") or listing.get("department"))
        job.unit = (
            f"{self.headquarters} / {department}"
            if department and department != self.headquarters
            else self.headquarters
        )
        job.work_type = "校招"
        job.field_sources["unit"] = "高校招聘列表 company 为集团总部；orgName 为部门"
        job.published = text(row.get("publishFirstDate") or listing.get("publishFirstDate"))
        job.field_sources["published"] = "首次发布日期 publishFirstDate；不使用更新日 publishDate"
        if job.deadline.startswith("3000-"):
            job.deadline = ""
            job.field_sources["deadline"] = "source_missing:3000-01-01 为站点占位值"
        return job


TENANTS = (
    Lining2027,
    GpcHeadquarters2027,
    FarEastListedCampus,
    HualuHengshengCampus,
    DbnCampus,
    BbmgCampus,
    ChanghongListed,
    SinomachGroup,
    MinmetalsGroup,
    HengyiGroup,
    CrrcGroup,
    GwmListed,
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
