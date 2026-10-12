"""Public Moka campus pages and their documented-in-page response format."""

import base64
import json
import re
from typing import Any, Protocol, cast

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.filtering import select
from job_crawler.models import Issue, Job, Scope
from job_crawler.transport import CrawlError


class Page(Protocol):
    async def evaluate(self, script: str) -> Any: ...


class PageSession(Protocol):
    page: Page


class ExactObserver(Protocol):
    async def observed_path(self, path: str) -> dict[str, Any]: ...


def decode(response: dict[str, Any], iv: str) -> dict[str, Any]:
    if "necromancer" not in response:
        result = response
    else:
        key = response["necromancer"]
        data = response.get("data")
        check(isinstance(iv, str) and len(iv.encode()) == 16, "Moka 页面缺少有效解密 IV")
        check(isinstance(key, str) and len(key.encode()) in {16, 24, 32}, "Moka 响应密钥无效")
        if not isinstance(data, str):
            raise CrawlError("schema_changed", "Moka 加密响应结构改变")
        try:
            cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()))
            decryptor = cipher.decryptor()
            padded = decryptor.update(base64.b64decode(data, validate=True)) + decryptor.finalize()
            unpadder = PKCS7(128).unpadder()
            result = json.loads((unpadder.update(padded) + unpadder.finalize()).decode())
        except (ValueError, UnicodeDecodeError, KeyError) as exc:
            raise CrawlError("decode_failed", "Moka 公共响应解码失败；页面版本可能改变") from exc
    check(isinstance(result, dict) and result.get("code") == 0, "Moka 业务响应失败")
    return result


def sections(html: str) -> tuple[str, str]:
    lines = [line.strip() for line in text(html).splitlines()]
    duties: list[str] = []
    requirements: list[str] = []
    mode = "duties"
    for line in lines:
        heading = re.sub(r"[：:\s【】]", "", line)
        heading = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]", "", heading)
        if heading in {"岗位职责", "工作职责", "职位职责", "职位描述"}:
            mode = "duties"
            continue
        if heading in {"任职要求", "岗位要求", "任职资格", "职位要求", "应聘要求", "基本要求"}:
            mode = "requirements"
            continue
        if line in {"：", ":"}:
            continue
        (requirements if mode == "requirements" else duties).append(line)
    return "\n".join(duties), "\n".join(requirements)


def location_text(rows: object) -> tuple[str, str]:
    if not isinstance(rows, list):
        raise CrawlError("schema_changed", "Moka 地点不是数组")
    names: list[str] = []
    paths: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            raise CrawlError("schema_changed", "Moka 地点结构改变")
        city = text(item.get("cityName"))
        province = text(item.get("provinceName"))
        if city and city not in names:
            names.append(city)
        if city and province:
            path = f"{province}/{city}"
            if path not in paths:
                paths.append(path)
    return (paths[0] if len(paths) == len(names) == 1 else "、".join(names), "")


class Moka(Adapter):
    host = "app.mokahr.com"
    org = ""
    site_id = 0
    route = "campus-recruitment"
    path = ""
    ready_endpoints = ("/api/outer/ats-apply/website/jobs/v2",)
    scope_description = (
        "Moka campus-recruitment 单站点公开无筛选全目录；实习/兼职保留原类型供公共层排除"
    )

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/{self.route}/{self.org}/{self.site_id}#/job/{job_id}"

    async def harvest(self) -> None:
        page = cast(PageSession, self.session).page
        iv = await page.evaluate("() => window.TurboApply?.data?.aesIv")
        check(isinstance(iv, str) and len(iv.encode()) == 16, "Moka 页面 IV 无效")
        observer = cast(ExactObserver, self.session)
        observed = await observer.observed_path("/api/outer/ats-apply/website/jobs/v2")
        payload = json.loads(observed["post_data"])
        check(payload.get("orgId") == self.org, "Moka 组织不匹配")
        check(str(payload.get("siteId")) == str(self.site_id), "Moka 站点不匹配")
        check(payload.get("site") == "campus", "Moka 入口不是校园站点")
        check(int(payload.get("offset", -1)) == 0, "Moka 列表不是第一页")
        check(
            not payload.get("jobIdTopList") and not payload.get("customFields"), "Moka 目录带有筛选"
        )
        for key in ("keyword", "locations", "zhineng", "commitment", "departmentIds"):
            check(not payload.get(key), f"Moka 目录带有筛选 {key}")
        limit = int(payload["limit"])
        check(0 < limit <= 100, "Moka 分页大小异常")
        scope = Scope(name=f"campus-site-{self.site_id}")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        offset = 0
        detail_api = ""
        while True:
            wrapped = await self.session.request(
                observed["url"], payload={**payload, "offset": offset, "limit": limit}
            )
            data = decode(wrapped, iv)["data"]
            expected = int(data["jobStats"]["total"])
            check(expected > 0, "Moka 公开职位目录为空或总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "Moka 分页期间总数变化")
            rows = self.add_page(scope, data["jobs"], seen, lambda row: str(row["id"]))
            list_evidence = self.session.last_evidence
            for row in rows:
                job_id = str(row["id"])
                try:
                    check(row.get("orgId") == self.org, "Moka 列表混入其他组织")
                    listing = self._job(row, row, list_evidence)
                    if select(listing, "all", self.as_of).reason == "expired":
                        listing.detail_mode = "listing_only"
                        self.result.jobs.append(listing)
                        scope.skipped_expired += 1
                        continue
                    resolved = self.before_detail(
                        f"job:{job_id}", row, scope, listing, evidence=list_evidence
                    )
                    if resolved is not None:
                        self.result.jobs.extend(resolved)
                        continue
                    if not detail_api:
                        await self.session.open(
                            self.detail_page(job_id),
                            ready_endpoints=("/api/outer/ats-apply/website/job",),
                        )
                        observed_detail = await observer.observed_path(
                            "/api/outer/ats-apply/website/job"
                        )
                        detail_api = observed_detail["url"]
                        first_detail = decode(json.loads(observed_detail["body"]), iv)
                        detail_evidence = self.session.last_evidence
                    else:
                        first_detail = None
                        detail_evidence = ""
                    wrapped_detail = (
                        first_detail
                        if first_detail is not None
                        else decode(
                            await self.session.request(
                                detail_api,
                                payload={
                                    "orgId": self.org,
                                    "jobId": job_id,
                                    "siteId": self.site_id,
                                    "locale": payload.get("locale", "zh-CN"),
                                },
                                detail=True,
                            ),
                            iv,
                        )
                    )
                    detail = wrapped_detail["data"]
                    check(str(detail["id"]) == job_id, "Moka 详情与列表 ID 不一致")
                    check(detail.get("orgId") == self.org, "Moka 详情组织不一致")
                    job = self._job(
                        detail, row, detail_evidence or self.session.last_evidence, is_detail=True
                    )
                    self.result.jobs.append(job)
                    scope.details += 1
                    self.remember(f"job:{job_id}", row, [job])
                except Exception as exc:
                    self.error(exc, job_id)
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        raise
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "Moka 分页提前为空")
            offset += len(rows)

    def _job(
        self,
        row: dict[str, Any],
        listing: dict[str, Any],
        evidence: str,
        *,
        is_detail: bool = False,
    ) -> Job:
        job_id = str(row["id"])
        description = text(row.get("jobDescription") or listing.get("jobDescription"))
        duties, requirements = sections(description)
        if is_detail and not requirements:
            self.result.warnings.append(
                Issue(
                    code="field_missing",
                    message=(
                        "源站详情没有岗位正文"
                        if not row.get("jobDescription")
                        else "源站详情无可辨认的任职要求段落"
                    ),
                    source_id=self.source.source_id,
                    job_key=job_id,
                    url=self.detail_page(job_id),
                )
            )
        locations = row.get("locations") or listing.get("locations") or []
        location, address = location_text(locations)
        dept = row.get("department") or listing.get("department") or {}
        zhineng = row.get("zhineng") or listing.get("zhineng") or {}
        commitment = text(row.get("commitment") or listing.get("commitment"))
        title = text(row.get("title") or listing.get("title"))
        work_type = (
            "实习"
            if "实习" in title
            else "兼职"
            if "兼职" in title
            else "校招"
            if commitment in {"全职", ""}
            else commitment
        )
        job = self.job(
            job_id,
            title=title,
            work_type=work_type,
            unit=text(dept.get("name")),
            category_raw=text(zhineng.get("name")),
            education=text(row.get("education")),
            location=location,
            address=address,
            duties=duties,
            requirements=requirements,
            published=text(row.get("publishedAt") or listing.get("publishedAt")),
            visible=row.get("status") == "open",
            closed=bool(row.get("closedAt")),
            source_url=self.detail_page(job_id),
            field_sources={
                "duties": (
                    "website/job.data.jobDescription"
                    if row.get("jobDescription") or listing.get("jobDescription")
                    else "source_missing:jobDescription"
                ),
                "requirements": (
                    "website/job.data.jobDescription:可见标题"
                    if requirements
                    else "source_missing:要求段落"
                ),
                "published": "website/job.data.publishedAt or jobs/v2.data.jobs[].publishedAt",
                "location": "website/job.data.locations[].provinceName/cityName",
            },
        )
        job.evidence = [evidence] if evidence else []
        return job


class CATL(Moka):
    name = "moka-catl"
    org = "catlhr"
    site_id = 142020
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Huaqin(Moka):
    name = "moka-huaqin"
    org = "hq"
    site_id = 45417
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Jinko(Moka):
    name = "moka-jinko"
    org = "jinkosolar"
    site_id = 41896
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Sungrow(Moka):
    name = "moka-sungrow"
    org = "sungrow"
    site_id = 94416
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class STO(Moka):
    name = "moka-sto"
    org = "sto"
    site_id = 126265
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Lygend(Moka):
    name = "moka-lygend"
    org = "lygend"
    site_id = 72100
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Digiloong(Moka):
    name = "moka-digiloong"
    org = "digiloong"
    site_id = 126358
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class HFSP(Moka):
    name = "moka-hfsp"
    org = "hfsp"
    site_id = 37149
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Sanhua(Moka):
    name = "moka-sanhua"
    org = "zjshc"
    site_id = 56209
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class EastchinaPharm(Moka):
    name = "moka-eastchinapharm"
    org = "eastchinapharm"
    site_id = 67935
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Yadea(Moka):
    name = "moka-yadea"
    org = "yadea"
    site_id = 26985
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"


class Fehorizon(Moka):
    name = "moka-fehorizon"
    org = "fehorizon01"
    site_id = 68154
    route = "campus_apply"
    path = f"/{route}/{org}/{site_id}#/jobs"


class Dasenlin(Moka):
    name = "moka-dasenlin"
    org = "dslyy"
    site_id = 136052
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Geely(Moka):
    name = "moka-geely"
    host = "campus.geely.com"
    org = "geely"
    site_id = 78436
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/campus-recruitment/{self.org}/{self.site_id}/#/job/{job_id}"


class Chint(Moka):
    name = "moka-chint"
    host = "campus.chint.com"
    org = "chint"
    site_id = 40745
    path = f"/campus-recruitment/{org}/{site_id}/#/jobs"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/campus-recruitment/{self.org}/{self.site_id}/#/job/{job_id}"


class Muyuan(Moka):
    name = "moka-muyuan"
    org = "muyuan"
    site_id = 70116
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class Wens(Moka):
    name = "moka-wens"
    org = "wens"
    site_id = 92366
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


class XCMG(Moka):
    name = "moka-xcmg"
    org = "xcmg"
    site_id = 148091
    path = f"/campus-recruitment/{org}/{site_id}#/jobs"


TENANTS = (
    CATL,
    Huaqin,
    Jinko,
    Sungrow,
    STO,
    Lygend,
    Digiloong,
    HFSP,
    Sanhua,
    EastchinaPharm,
    Yadea,
    Fehorizon,
    Dasenlin,
    Geely,
    Chint,
    Muyuan,
    Wens,
    XCMG,
)
