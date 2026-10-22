"""Explicit Beisen tenants sharing a verified public campus API contract."""

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

from job_crawler.adapters.base import Adapter, query, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Job, Scope
from job_crawler.transport import CrawlError


def date_text(value: Any) -> str:
    value = text(value)
    return "" if value.startswith(("0001-01-01", "2222-02-02")) else value


class Zhiye(Adapter):
    path = "/campus/jobs"
    mixed_catalog = False
    detail_path = "/campus/detail"
    regular_only = False
    listing_complete = False
    listing_unit_field = "Org"
    listing_unit_fallback = ""
    category_field = "ClassificationOne"
    expected_org = ""
    page_size = 20
    catalog_payload: dict[str, Any] | None = None
    ready_endpoints = ("/api/Jobad/GetJobAdPageList",)
    scope_description = "北森公开校园招聘 Category=2 全目录；保留实际租户/门户范围，不含社招和实习"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}{self.detail_path}?{urlencode({'jobAdId': job_id})}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        return True

    async def harvest(self) -> None:
        observed = (
            {
                "url": f"https://{self.host}/api/Jobad/GetJobAdPageList",
                "post_data": json.dumps(self.catalog_payload),
            }
            if self.catalog_payload is not None
            else await self.session.observed("/api/Jobad/GetJobAdPageList")
        )
        payload = json.loads(observed["post_data"])
        if self.mixed_catalog:
            check(
                not payload.get("Category")
                and payload.get("SpecialType") == 0
                and payload.get("PortalId") == "",
                "北森混合目录初始筛选异常",
            )
            payload["Category"] = ["2"]
        else:
            check([str(v) for v in payload.get("Category", [])] == ["2"], "不是校招 Category=2")
        check(not payload.get("KeyWords"), "校招目录仍有关键词筛选")
        for key in (
            "LocId",
            "ClassificationOne",
            "ClassificationTwo",
            "Classification3",
            "Classification4",
            "Classification5",
            "Classification6",
        ):
            check(not payload.get(key), f"目录仍有局部筛选 {key}，需接入完整入口")
        scope = Scope(name="campus-category-2")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        page = 0
        size = max(self.page_size, int(payload["PageSize"]))
        detail_url = ""
        limit = asyncio.Semaphore(3)
        detail_lock = asyncio.Lock()
        list_evidence = ""
        abort: CrawlError | None = None

        async def read_job(listed: dict[str, Any]) -> Job | None:
            nonlocal abort
            async with limit:
                if abort is not None:
                    return None
                try:
                    if self.expected_org and (self.listing_complete or listed.get("Org")):
                        check(
                            text(listed.get("Org")) == self.expected_org,
                            "列表岗位所属法人与名录主体不一致",
                        )
                    listing = self.job(
                        str(listed["Id"]),
                        title=text(listed.get("JobAdName")),
                        source_url=self.detail_page(str(listed["Id"])),
                        published=date_text(listed.get("PostDate")),
                        deadline=date_text(listed.get("EndTime")),
                    )
                    listing.evidence = [list_evidence] if list_evidence else []
                    if self.listing_complete:
                        check(str(listed.get("CategoryId")) == "2", "列表岗位混入非校招类别")
                        check("Duty" in listed and "Require" in listed, "列表不再包含完整正文")
                        job = self.job(
                            str(listed["Id"]),
                            title=text(listed["JobAdName"]),
                            work_type=(
                                "实习"
                                if self.regular_only
                                and (
                                    "实习" in text(listed.get("Kind"))
                                    or "实习" in text(listed["JobAdName"])
                                )
                                else "校招"
                            ),
                            source_url=self.detail_page(str(listed["Id"])),
                            unit=text(
                                listed.get(self.listing_unit_field) or self.listing_unit_fallback
                            ),
                            location=text(listed.get("LocNames")),
                            education=text(listed.get("Degree")),
                            address=text(listed.get("DetailAddress")),
                            category_raw=text(listed.get(self.category_field)),
                            duties=text(listed["Duty"]),
                            requirements=text(listed["Require"]),
                            published=date_text(listed.get("PostDate")),
                            deadline=date_text(listed.get("EndTime")),
                            field_sources={
                                "unit": (
                                    "本租户官方公司身份；列表 Org 为空"
                                    if self.listing_unit_fallback
                                    and not listed.get(self.listing_unit_field)
                                    else "GetJobAdPageList.Data[].Org"
                                ),
                                "duties": "GetJobAdPageList.Data[].Duty",
                                "requirements": "GetJobAdPageList.Data[].Require",
                                "published": "PostDate；0001 哨兵为空",
                                "deadline": "EndTime；0001 哨兵为空",
                            },
                        )
                        job.evidence = [list_evidence] if list_evidence else []
                        scope.details += 1
                        return job
                    resolved = self.before_detail(
                        f"job:{listed['Id']}",
                        listed,
                        scope,
                        listing,
                        evidence=list_evidence,
                    )
                    if resolved is not None:
                        return resolved[0]
                    await ensure_detail(listed)
                    data = await self.session.request(
                        query(detail_url, jobAdId=listed["Id"]), detail=True
                    )
                    check(data.get("Code") == 200, "北森详情业务失败")
                    row = data["Data"]
                    check(str(row["Id"]) == str(listed["Id"]), "北森详情与列表 ID 不一致")
                    if self.expected_org:
                        check(
                            text(row.get("Org")) == self.expected_org,
                            "北森详情所属法人与名录主体不一致",
                        )
                    check(str(row["CategoryId"]) == "2", "岗位混入非校招类别")
                    check(bool(row["JobAdName"]), "岗位名称为空")
                    check("Duty" in row and "Require" in row, "详情不再包含职位描述")
                    job = self.job(
                        str(row["Id"]),
                        title=text(row["JobAdName"]),
                        work_type=(
                            "实习"
                            if self.regular_only
                            and (
                                "实习" in text(row.get("Kind")) or "实习" in text(row["JobAdName"])
                            )
                            else "校招"
                        ),
                        source_url=self.detail_page(str(row["Id"])),
                        unit=text(row.get("Org") or listed.get("Org")),
                        location=text(row.get("LocNames") or listed.get("LocNames")),
                        education=text(row.get("Degree") or listed.get("Degree")),
                        address=text(row.get("DetailAddress")),
                        category_raw=text(
                            row.get(self.category_field) or listed.get(self.category_field)
                        ),
                        duties=text(row["Duty"]),
                        requirements=text(row["Require"]),
                        published=date_text(row.get("PostDate"))
                        or date_text(listed.get("PostDate")),
                        deadline=date_text(row.get("EndTime")) or date_text(listed.get("EndTime")),
                        field_sources={
                            "duties": "GetJobAdInfo.Data.Duty",
                            "requirements": "GetJobAdInfo.Data.Require",
                            "published": "PostDate；0001 哨兵为空",
                            "deadline": "EndTime；0001 哨兵为空",
                        },
                    )
                    scope.details += 1
                    self.remember(f"job:{listed['Id']}", listed, [job])
                    return job
                except Exception as exc:
                    self.error(exc, str(listed.get("Id", "")))
                    if isinstance(exc, CrawlError) and exc.code in {
                        "access_denied",
                        "request_budget",
                        "time_budget",
                    }:
                        abort = exc
                    return None

        async def ensure_detail(listed: dict[str, Any]) -> None:
            nonlocal detail_url
            async with detail_lock:
                if not detail_url:
                    await self.session.open(
                        self.detail_page(str(listed["Id"])),
                        ready_endpoints=("/api/JobAd/GetJobAdInfo?",),
                    )
                    detail_url = (await self.session.observed("/api/JobAd/GetJobAdInfo?"))["url"]

        while True:
            result = await self.session.request(
                observed["url"], payload={**payload, "PageIndex": page, "PageSize": size}
            )
            check(result.get("Code") == 200, "北森列表业务失败")
            expected = int(result["Count"])
            check(expected >= 0, "北森目录总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(expected == scope.expected, "北森目录总数变化")
            rows = self.add_page(scope, result["Data"], seen, lambda row: str(row["Id"]))
            list_evidence = self.session.last_evidence
            included = []
            for row in rows:
                if self.in_scope(row):
                    included.append(row)
                else:
                    scope.skipped_out_of_scope += 1
            jobs = await asyncio.gather(*(read_job(row) for row in included))
            self.result.jobs.extend(job for job in jobs if job is not None)
            if abort is not None:
                raise abort
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows), "北森分页提前为空")
            page += 1


class ShenghongCampus(Zhiye):
    name = "zhiye-shenghong-group-campus"
    host = "shenghonggroup.zhiye.com"
    regular_only = True
    scope_description = (
        "盛虹控股集团北森Category=2校园全目录；含印染、化纤、石化等全部板块，"
        "不将石化卡片局部目录或旧51job结束页当作集团范围"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "盛虹校园目录混入其他招聘类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "盛虹岗位性质不明确")
        return True


class BusyMingCampus(Zhiye):
    name = "zhiye-busyming-campus"
    host = "hnlshm4.zhiye.com"
    regular_only = True
    scope_description = "鸣鸣很忙集团官网直连北森Category=2完整校园目录；不含社招、实习和内部推荐"


class SunartCampus(Zhiye):
    name = "zhiye-sunart-campus"
    host = "rt-mart.zhiye.com"
    regular_only = True
    scope_description = (
        "高鑫零售品牌官网统一北森门户Category=2全目录；含全国职位，不以省份卡片代替完整目录"
    )


class YonghuiCampus(Zhiye):
    name = "zhiye-yonghui-campus"
    host = "yhchaoshi.zhiye.com"
    scope_description = "永辉超市官方北森门户Category=2校园全目录；不包含社招或高校独立宣讲简章"


class GrandtradeCampus(Zhiye):
    name = "zhiye-grandtrade-campus"
    host = "grandtrade.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "远大控股官方校园 Category=2 全目录；保留仍展示岗位的实际历史发布日期"


class XaecCampus(Zhiye):
    name = "zhiye-xaec-campus"
    host = "xaec.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "中国航发动力股份有限公司官方校园 Category=2 全目录；不含集团其他门户及实习"


class MediatekCampus(Zhiye):
    name = "zhiye-mediatek-campus"
    host = "mediatek.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "联发科技官方大陆校园门户 Category=2 全地区全类别目录；不含社招和实习"


class TaikangCampus(Zhiye):
    name = "zhiye-taikang-campus"
    host = "jobtaikang.zhiye.com"
    path = "/custom/campuslist"
    listing_complete = True
    regular_only = True
    scope_description = "泰康集团官方校园招聘 Category=2 全目录；保留实际机构，排除社招和实习"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}/custom/gddetail?{urlencode({'hideAll': '1', 'jc': '2', 'jobAdId': job_id})}"


class WingtechCampus(Zhiye):
    name = "zhiye-wingtech-campus"
    host = "jobs.wingtech.com"
    regular_only = True
    scope_description = "闻泰科技官方公开校园招聘 Category=2 无筛选全目录；实习和社招排除"


class Poly(Zhiye):
    name = "zhiye-poly"
    host = "polycareer.zhiye.com"


class Mxbc2027(Zhiye):
    name = "zhiye-mxbc-2027"
    host = "careers.mxbc.com"
    listing_complete = True
    scope_description = "蜜雪集团2027届公开校园招聘 Category=2 全目录；实际招聘单位未公开时留空"


class GenertecCampus(Zhiye):
    name = "zhiye-genertec-campus"
    host = "genertec.zhiye.com"
    listing_complete = True
    scope_description = "通用技术集团公开校园招聘 Category=2 全目录；实际招聘单位未公开时留空"


class Sph2027(Zhiye):
    name = "zhiye-sph-2027"
    host = "sph.zhiye.com"
    listing_complete = True
    scope_description = "上海医药2027秋季校园招聘 Category=2 全目录；保留逐岗实际招聘单位"


class Zhenshi2027(Zhiye):
    name = "zhiye-zhenshi-2027"
    host = "zhenshigroup.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "振石控股集团2027届公开校园招聘 Category=2 全目录；源未给实际招聘法人时留空"


class Xiangyu(Zhiye):
    name = "zhiye-xiangyu"
    host = "xiangyu.zhiye.com"


class Changan(Zhiye):
    name = "zhiye-changan"
    host = "changanqiche.zhiye.com"
    path = "/campus/"


class DigitalChina(Zhiye):
    name = "zhiye-digitalchina"
    host = "digitalchina.zhiye.com"


class Bosc(Zhiye):
    name = "zhiye-bosc"
    host = "bosc.zhiye.com"


class Sinotrans(Zhiye):
    name = "zhiye-sinotrans"
    host = "sinotrans.zhiye.com"
    path = "/campus"


class Sany(Zhiye):
    name = "zhiye-sany"
    host = "sany.zhiye.com"


class Transsion(Zhiye):
    name = "zhiye-transsion"
    host = "transsion.zhiye.com"


class Bocd(Zhiye):
    name = "zhiye-bocd"
    host = "bocd.zhiye.com"


class Cscb(Zhiye):
    name = "zhiye-cscb"
    host = "cscb.zhiye.com"


class Dsbj(Zhiye):
    name = "zhiye-dsbj"
    host = "dsbj.zhiye.com"


class Sailun(Zhiye):
    name = "zhiye-sailun"
    host = "sailuntire.zhiye.com"


class Csc108(Zhiye):
    name = "zhiye-csc108"
    host = "csc108.zhiye.com"


class Tsingtao(Zhiye):
    name = "zhiye-tsingtao"
    host = "tsingtao.zhiye.com"


class Yuhong(Zhiye):
    name = "zhiye-yuhong"
    host = "yuhongzp.zhiye.com"


class Iflytek(Zhiye):
    name = "zhiye-iflytek"
    host = "iflytek.zhiye.com"


class Goldwind(Zhiye):
    name = "zhiye-goldwind"
    host = "goldwind.zhiye.com"


class Mengniu(Zhiye):
    name = "zhiye-mengniu"
    host = "mengniu.zhiye.com"


class Leapmotor(Zhiye):
    name = "zhiye-leapmotor"
    host = "leapmotor.zhiye.com"


class Mywind(Zhiye):
    name = "zhiye-mywind"
    host = "mywind.zhiye.com"


class Popmart(Zhiye):
    name = "zhiye-popmart"
    host = "popmart.zhiye.com"


class Szgas(Zhiye):
    name = "zhiye-szgas"
    host = "szgas.zhiye.com"


class Ovt(Zhiye):
    name = "zhiye-ovt"
    host = "ovt-omnivision.zhiye.com"


class Juhua(Zhiye):
    name = "zhiye-juhua"
    host = "juhua.zhiye.com"


class NewHope(Zhiye):
    name = "zhiye-newhope"
    host = "newhope.zhiye.com"


class CNAF(Zhiye):
    name = "zhiye-cnaf"
    host = "cnaf.zhiye.com"


class Greentown(Zhiye):
    name = "zhiye-gtgroup"
    host = "gtgroup.zhiye.com"


class BankOfBeijing(Zhiye):
    name = "zhiye-bankofbeijing"
    host = "bankofbeijing.zhiye.com"


class ENN(Zhiye):
    name = "zhiye-enn"
    host = "enn.zhiye.com"


class Beike(Zhiye):
    name = "zhiye-ke"
    host = "ke.zhiye.com"


class SMIC(Zhiye):
    name = "zhiye-smics"
    host = "smics.zhiye.com"


class Sunwoda(Zhiye):
    name = "zhiye-sunwoda"
    host = "sunwodacampus.zhiye.com"


class ZhongyuanBank(Zhiye):
    name = "zhiye-zybank"
    host = "zybank.zhiye.com"


class Vital(Zhiye):
    name = "zhiye-vital"
    host = "vital.zhiye.com"


class WuxiApptec(Zhiye):
    name = "zhiye-wuxiapptec-2027"
    host = "wuxiapptec.zhiye.com"
    listing_complete = True
    regular_only = True
    page_size = 100
    scope_description = "药明康德现用北森 Category=2 校招目录；仅 2027 届，未公开逐岗法人名称"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "药明康德目录混入非校招类别")
        return text(row.get("JobAdName")).startswith("2027届")


class WeichaiPower2027(Zhiye):
    name = "zhiye-weichai-power-2027"
    host = "weichai.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = (
        "潍柴动力2027招聘入口北森 Category=2 全目录；多个 OrgId 无公开法人名，单位留空"
    )


class Ctf2027(Zhiye):
    name = "zhiye-ctf-2027"
    host = "hr.ctf.com.cn"
    listing_complete = True
    regular_only = True
    scope_description = "周大福2027校招北森 Category=2 全目录；无逐岗法人名称，单位留空"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(
            str(row.get("OrgId")) == "34100" and "周大福" in text(row.get("JobAdName")),
            "周大福校招组织或品牌改变",
        )
        return True


class Gotion(Zhiye):
    name = "zhiye-gotion"
    host = "gotion.zhiye.com"
    path = "/jobs"
    mixed_catalog = True
    scope_description = "国轩高科 /jobs 混合目录，经 Category=2 过滤的全部校招岗位"


class CALB(Zhiye):
    name = "zhiye-calb"
    host = "calbjs.zhiye.com"


class CICC(Zhiye):
    regular_only = True
    name = "zhiye-cicc"
    host = "cicc.zhiye.com"
    path = "/custom/campus?hideMenu=1"
    detail_path = "/custom/campusxq"


class Jiangling(Zhiye):
    name = "zhiye-jmc"
    host = "jmc.zhiye.com"


class Avary(Zhiye):
    name = "zhiye-avary"
    host = "avaryholding.zhiye.com"


class ChinaStock(Zhiye):
    regular_only = True
    name = "zhiye-chinastock"
    host = "chinastock.zhiye.com"
    path = "/custom/campus"
    detail_path = "/custom/campusxq"


class AUX(Zhiye):
    name = "zhiye-aux"
    host = "auxgroup.zhiye.com"


class Baic(Zhiye):
    regular_only = True
    name = "zhiye-baic"
    host = "baicgroup.zhiye.com"


class Naura(Zhiye):
    regular_only = True
    name = "zhiye-naura"
    host = "career.naura.com"


class Dahua(Zhiye):
    name = "zhiye-dahua"
    host = "dahua.zhiye.com"
    regular_only = True


class Mindray(Zhiye):
    name = "zhiye-mindray"
    host = "career.mindray.com"
    listing_complete = True
    regular_only = True
    scope_description = (
        "迈瑞公开 Category=2 全校园目录，列表提供职责与任职要求；含博士校招，不含实习"
    )


class Shenzhou(Zhiye):
    name = "zhiye-shenzhou"
    host = "career.shenzhouintl.com"
    listing_complete = True
    regular_only = True
    scope_description = "申洲国际公开 Category=2 全校园目录，列表提供职责与任职要求；不含社招和实习"


class LuzhouLaojiao(Zhiye):
    name = "zhiye-luzhou-laojiao"
    host = "job.lzlj.com"
    listing_complete = True
    regular_only = True
    expected_org = "泸州老窖股份有限公司"
    scope_description = (
        "泸州老窖 Category=2 校园目录中 Org 精确匹配股份公司的全部岗位；不含其他法人"
    )


class Huafeng(Zhiye):
    name = "zhiye-huafeng"
    host = "huafeng.zhiye.com"
    path = "/campus"
    listing_complete = True
    regular_only = True
    scope_description = "华峰集团 2027 校招门户 Category=2 无筛选全目录；列表提供完整职责与要求"


class Infore(Zhiye):
    name = "zhiye-infore"
    host = "recruit.infore.com"
    listing_complete = True
    regular_only = True
    scope_description = "盈峰集团招聘门户 Category=2 无筛选校园全目录；实习由公共筛选排除"


class Seres(Zhiye):
    name = "zhiye-seres"
    host = "sokon.zhiye.com"
    listing_complete = True
    scope_description = "赛力斯集团独立 Category=2 正式校招全目录；可实习不等同实习岗位"


class Shrcb(Zhiye):
    name = "zhiye-shrcb"
    host = "shrcb.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "上海农商银行 Category=2 校园目录；长江金租独立入口不纳入本行"


class Haid(Zhiye):
    name = "zhiye-haid"
    host = "haid1.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "海大集团 2027 Category=2 校园全目录；保留业务板块和实际来源字段"


class Chery(Zhiye):
    name = "zhiye-chery"
    host = "chery.zhiye.com"
    listing_complete = True
    regular_only = True
    page_size = 200
    scope_description = "奇瑞汽车北森 Category=2 无筛选目录；仅 OrgId=886961 的奇瑞汽车股份校招"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == "奇瑞汽车股份（校招）" or org_id == "886961":
            check(
                name == "奇瑞汽车股份（校招）" and org_id == "886961",
                "奇瑞汽车本部组织名称和编码不匹配",
            )
            check(str(row.get("CategoryId")) == "2", "奇瑞本部岗位混入非校招类别")
            check(text(row.get("Kind")) == "全职", "奇瑞本部岗位混入非全职")
            return True
        return False


class PICCGroup(Zhiye):
    name = "zhiye-picc-group"
    host = "picc.zhiye.com"
    path = "/custom/campus?hideAll=true"
    listing_complete = True
    regular_only = True
    page_size = 200
    expected_org = "中国人民保险集团股份有限公司"
    scope_description = "中国人保 Category=2 共享目录；仅 OrgId=45182 的集团股份公司本级"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}{self.path}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == self.expected_org or org_id == "45182":
            check(name == self.expected_org and org_id == "45182", "人保集团本级机构编码不匹配")
            check(str(row.get("CategoryId")) == "2", "人保集团本级混入非校招类别")
            check(text(row.get("Kind")) == "全职", "人保集团本级混入非全职岗位")
            check("2027届校招" in text(row.get("JobAdName")), "人保集团本级出现未知项目")
            return True
        return False


class ChinaLifeGroup(Zhiye):
    name = "zhiye-chinalife-group"
    host = "chinalife.zhiye.com"
    path = "/custom/campus?hideMenu=1"
    listing_complete = True
    regular_only = True
    page_size = 200
    expected_org = "中国人寿保险（集团）公司"
    scope_description = "中国人寿 Category=2 共享目录；仅 OrgId=3389294 的集团公司本级"

    def detail_page(self, job_id: str) -> str:
        return f"https://{self.host}{self.path}"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == self.expected_org or org_id == "3389294":
            check(name == self.expected_org and org_id == "3389294", "国寿集团本级机构编码不匹配")
            check(str(row.get("CategoryId")) == "2", "国寿集团本级混入非校招类别")
            check(text(row.get("Kind")) == "全职", "国寿集团本级混入非全职岗位")
            check(
                text(row.get("PostDate")).startswith("2026-09-"),
                "国寿集团本级岗位不属于已验证的 2027 秋招发布时间范围",
            )
            return True
        return False


class YuntianhuaParent(Zhiye):
    name = "zhiye-yuntianhua-parent"
    host = "yythzb3.zhiye.com"
    listing_complete = True
    regular_only = True
    page_size = 200
    scope_description = "云天化 Category=2 共享目录；仅 OrgId=4022958 的云天化股份本部"

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("ClassificationTwo"))
        org_id = str(row.get("OrgId"))
        parent = "云南云天化股份有限公司本部"
        if name == parent or org_id == "4022958":
            check(name == parent and org_id == "4022958", "云天化股份本部机构编码不匹配")
            check(str(row.get("CategoryId")) == "2", "云天化股份本部混入非校招类别")
            check(text(row.get("Kind")) == "全职", "云天化股份本部混入非全职岗位")
            check(
                text(row.get("PostDate")).startswith("2026-09-"),
                "云天化股份本部岗位不属于已验证的 2027 秋招发布时间范围",
            )
            row["Org"] = name
            return True
        return False


class CmhkParent(Zhiye):
    name = "zhiye-cmhk-parent"
    host = "cmhk.zhiye.com"
    page_size = 200
    expected_org = "招商局能源运输股份有限公司"
    scope_description = (
        "招商局集团 Category=2 共享目录；仅详情 OrgId=748690 的招商局能源运输股份本级"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        name = text(row.get("Org"))
        org_id = str(row.get("OrgId"))
        if name == self.expected_org or org_id == "748690":
            check(org_id == "748690", "招商轮船本级机构编码不匹配")
            check(not name or name == self.expected_org, "招商轮船本级列表机构名称不匹配")
            check(str(row.get("CategoryId")) == "2", "招商轮船本级混入非校招类别")
            check(text(row.get("Kind")) == "全职", "招商轮船本级混入非全职岗位")
            check("2027届" in text(row.get("JobAdName")), "招商轮船本级出现未知校招项目")
            return True
        return False


class Cinda2027(Zhiye):
    name = "zhiye-cinda-2027"
    host = "cinda.zhiye.com"
    listing_complete = True
    listing_unit_field = "ClassificationTwo"
    scope_description = (
        "中国信达2027年度校招 Category=2 全目录；官方公告及附件列出总部、后援中心和分公司"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "中国信达目录混入非校招类别")
        unit = text(row.get("ClassificationTwo"))
        check(
            bool(row.get("OrgId"))
            and (unit in {"信达总部", "总部", "后援中心"} or unit.endswith("分公司")),
            "中国信达招聘机构超出公告总部、后援中心及分公司范围",
        )
        published = date_text(row.get("PostDate"))
        check(bool(published), "中国信达岗位缺少源发布日期")
        return published[:10] >= "2026-10-09"


class Vanchen2027(Zhiye):
    name = "zhiye-vanchen-2027"
    host = "vanchen1.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "万辰集团 2027 校招北森 Category=2 全目录；总部与好想来原文保留"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "万辰校招目录混入非校招类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "万辰校招岗位类型改变")
        return True


class XtransferCampus(Zhiye):
    name = "zhiye-xtransfer-campus"
    host = "xtransfer.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "XTransfer"
    scope_description = (
        "XTransfer 官网直链北森 Category=2 全目录；排除实习和标题明确为 2026 校招的旧批次"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "XTransfer 校招类别变化")
        check(text(row.get("Kind")) in {"全职", "实习"}, "XTransfer 职位性质变化")
        return "2026校招" not in text(row.get("JobAdName"))


class TongkunCampus(Zhiye):
    name = "zhiye-tongkun-campus"
    host = "hr-zjtkjt.zhiye.com"
    path = "/campus"
    listing_complete = True
    regular_only = True
    scope_description = "桐昆集团北森 Category=2 公开校招全目录；列表完整正文、未知单位原样留空"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "桐昆校招目录混入其他招聘类别")
        return True


class CcccGroupCampus(Zhiye):
    name = "zhiye-cccc-group-campus"
    host = "zhaopin.ccccltd.cn"
    listing_complete = True
    regular_only = True
    scope_description = "中国交建集团北森 Category=2 校招全目录；保留实际单位，缺失时留空"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "中国交建校招目录混入其他类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "中国交建岗位性质变化")
        return True


class SinosigGroupCampus(Zhiye):
    name = "zhiye-sinosig-group-campus"
    host = "sinosigcampus.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "阳光保险集团 Category=2 校招全目录；保留逐岗来源内容，不猜招聘法人"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "阳光保险校招目录混入其他类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "阳光保险岗位性质变化")
        return True


class GuotaiHuashengCampus(Zhiye):
    name = "zhiye-guotai-huasheng-2027"
    host = "gths.zhiye.com"
    listing_complete = True
    listing_unit_fallback = "江苏国泰华盛实业有限公司"
    scope_description = (
        "国泰华盛官方北森门户 Category=2 的 2027 届全职校园目录；国泰集团其他子公司不在此源范围"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "国泰华盛目录混入非校园类别")
        check(text(row.get("JobAdName")).startswith("2027校招-"), "国泰华盛目录混入异年岗位")
        return True


class YmtcCampus(Zhiye):
    name = "zhiye-ymtc-campus"
    host = "ymtc.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "长江存储北森 Category=2 公开校园全目录；排除实习与社会招聘"


class CxmtCampus(Zhiye):
    name = "zhiye-cxmt-campus"
    host = "cxmt.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "长鑫存储技术有限公司北森 Category=2 公开校园全目录；排除实习与社会招聘"


class DreameCampus(Zhiye):
    name = "zhiye-dreame-campus"
    host = "dreame.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "追觅招聘北森 Category=2 公开校园全目录；首页混合社招不在范围"


class AescCampus(Zhiye):
    name = "zhiye-aesc-campus"
    host = "aesc-group.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "远景动力北森 Category=2 公开校园全目录；以无筛选列表和源总数核对"


class GalaxyCampus(Zhiye):
    name = "zhiye-galaxy-campus"
    host = "galaxy.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "银河航天北森 Category=2 公开校园全目录；排除实习与社招"


class LeheCampus(Zhiye):
    name = "zhiye-lehe-campus"
    host = "lehe.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "乐禾集团北森 Category=2 公开校园全目录；来源无发布日期时保留空值"


class AispeechCampus(Zhiye):
    name = "zhiye-aispeech-campus"
    host = "aispeech.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "思必驰科技北森 Category=2 公开校园全目录；排除实习与社招"


class ZhihuiyaCampus(Zhiye):
    name = "zhiye-zhihuiya-campus"
    host = "zhihuiya.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "智慧芽北森 Category=2 公开校园全目录；排除实习与社招"


class HellobikeCampus(Zhiye):
    name = "zhiye-hellobike-campus"
    host = "hellobike.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "哈啰北森 Category=2 公开校园全目录；实习有独立入口"


class CasSpaceCampus(Zhiye):
    name = "zhiye-cas-space-campus"
    host = "cas-space.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "中科宇航北森 Category=2 公开校园全目录；排除实习与社招"


class IrootechCampus(Zhiye):
    name = "zhiye-irootech-campus"
    host = "irootech.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "树根互联北森 Category=2 公开校园全目录；排除实习与社招"


class JunlebaoCampus(Zhiye):
    name = "zhiye-junlebao-campus"
    host = "junlebaoruye.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "君乐宝乳业北森 Category=2 公开校园全目录；排除实习与社招"


class SvoltCampus(Zhiye):
    name = "zhiye-svolt-campus"
    host = "svolt.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "蜂巢能源北森 Category=2 应届生公开全目录；排除实习与社招"


class HairoboticsCampus(Zhiye):
    name = "zhiye-hairobotics-campus"
    host = "hairobotics.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "海柔创新北森 Category=2 公开校园全目录；海外地点保留原文"


class FoxEssCampus(Zhiye):
    name = "zhiye-fox-ess-campus"
    host = "fox-ess.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "麦田能源北森 Category=2 公开校园全目录；排除实习与社招"


class GalaxeaCampus(Zhiye):
    name = "zhiye-galaxea-campus"
    host = "galaxea.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "星海图北森 Category=2 公开校园全目录；排除实习与社招"


class HuiceCampus(Zhiye):
    name = "zhiye-huice-campus"
    host = "huicecom.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "慧策北森 Category=2 校招/实习共享全目录；按源性质及标题排除实习"


class SpacesailCampus(Zhiye):
    name = "zhiye-spacesail-campus"
    host = "spacesail.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "垣信卫星北森 Category=2 公开校园全目录；排除实习与社招"


class NarwalCampus(Zhiye):
    name = "zhiye-narwal-campus"
    host = "careers.narwal.com"
    path = "/jobs"
    mixed_catalog = True
    listing_complete = True
    regular_only = True
    scope_description = "云鲸智能北森混合目录精确筛 Category=2 后完整遍历；排除实习"


class XagCampus(Zhiye):
    name = "zhiye-xag-campus"
    host = "zhaopin.xa.com"
    listing_complete = True
    regular_only = True
    scope_description = "极飞科技北森 Category=2 校招全目录；性质与标题双重排除实习"


class CixinCampus(Zhiye):
    name = "zhiye-cixin-campus"
    host = "cixin.zhiye.com"
    listing_complete = True
    regular_only = True
    scope_description = "此芯科技官网所链北森 Category=2 公开校园全目录；排除实习"


class Vivo2027(Zhiye):
    name = "zhiye-vivo-2027"
    host = "hr-campus.vivo.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "vivo"
    scope_description = "vivo 官网所链独立北森校园门户 Category=2 全目录；仅纳入 2027 届正式岗位"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "vivo 校园目录混入其他类别")
        title = text(row.get("JobAdName"))
        return "27届" in title and "实习" not in title


class Weidian2027(Zhiye):
    name = "zhiye-weidian-2027"
    host = "hr.weidian.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "微店"
    scope_description = "微店官网 2027 届北森 Category=2 校园全目录；排除实习"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "微店校园目录混入其他类别")
        return "2027" in text(row.get("JobAdName"))


class KkGroup2027(Zhiye):
    name = "zhiye-kkgroup-2027"
    host = "kkguan.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "KK集团"
    scope_description = (
        "KK集团官网所链北森 Category=2 公开校园全目录；仅纳入标题明确的 27 届正式岗位"
    )

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "KK集团校园目录混入其他类别")
        title = text(row.get("JobAdName"))
        return title.startswith("【27") and "实习" not in title


class ZhuanzhuanCampus(Zhiye):
    name = "zhiye-zhuanzhuan-campus"
    host = "zhuanzhuan.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "转转"
    scope_description = "转转官网招聘菜单直链的独立北森 Category=2 校园全目录；实习按源性质排除"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "转转目录混入非校招类别")
        return True


class AdoptACow2027(Zhiye):
    name = "zhiye-adopt-a-cow-2027"
    host = "ryytn.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "认养一头牛"
    scope_description = "认养一头牛驿站独立北森 Category=2 校园全目录，仅纳入明确 2027 届正式岗位"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "认养一头牛目录混入非校招类别")
        return "2027" in (text(row.get("Duty")) + text(row.get("Require")))


class StarChargeCampus(Zhiye):
    name = "zhiye-star-charge-campus"
    host = "talent.wbstar.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "星星充电"
    scope_description = "星星充电招聘官网北森 Category=2 正式校园岗位无筛选全目录"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "星星充电目录混入非校招类别")
        return True


class Megarobo2027(Zhiye):
    name = "zhiye-megarobo-2027"
    host = "megarobo.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "镁伽"
    scope_description = "镁伽科技招聘简章所列独立北森 Category=2 的 2027 校园全目录"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "镁伽目录混入非校招类别")
        return "2027校招" in text(row.get("JobAdName"))


class Esign2027(Zhiye):
    name = "zhiye-esign-2027"
    host = "esign.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "e签宝"
    scope_description = "e签宝官网直链独立北森 Category=2 的 27 届正式校园全目录"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "e签宝目录混入非校招类别")
        return "27届" in text(row.get("JobAdName"))


class ShukunCampus(Zhiye):
    name = "zhiye-shukun-campus"
    host = "shukun.zhiye.com"
    path = "/campus/detail?jobAdId=24544e10-8954-4ff6-ad43-ae646a4c5c04"
    ready_endpoints = ("/api/JobAd/GetJobAdInfo",)
    regular_only = True
    catalog_payload = {
        "PageIndex": 0,
        "PageSize": 20,
        "Category": ["2"],
        "KeyWords": "",
        "SpecialType": 0,
        "PortalId": "",
        "DisplayFields": ["Category", "Kind", "LocId", "PostDate", "WorkWeChatQrCode"],
    }
    scope_description = "数坤官网所链北森校园 Category=2 全目录；排除实习及无校招标记的旧职位"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "数坤校园目录混入其他类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "数坤岗位性质未知")
        title = text(row.get("JobAdName"))
        return "校招" in title or "实习" in title


class Cansemi2027(Zhiye):
    name = "zhiye-cansemi-2027"
    host = "cansemitech.zhiye.com"
    path = "/campus/detail?jobAdId=9df5cf8b-2cd1-4939-87f6-4defda533e4b"
    ready_endpoints = ("/api/JobAd/GetJobAdInfo",)
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "粤芯半导体技术股份有限公司"
    catalog_payload = ShukunCampus.catalog_payload
    scope_description = "粤芯官方北森 2027 校园 Category=2 公开全目录；排除实习"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "粤芯目录混入非校招类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "粤芯岗位性质未知")
        return True


class UnitreeCampus(Zhiye):
    name = "zhiye-unitree-campus"
    host = "unitree.zhiye.com"
    path = "/campus/detail?jobAdId=37e315eb-3314-4b35-9680-3876c5d19221"
    ready_endpoints = ("/api/JobAd/GetJobAdInfo",)
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "杭州宇树科技股份有限公司"
    catalog_payload = ShukunCampus.catalog_payload
    scope_description = "宇树科技官方北森校园 Category=2 无筛选公开全目录；保留源发布日期"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "宇树目录混入非校招类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "宇树岗位性质未知")
        return True


class Bananain2027(Zhiye):
    name = "zhiye-bananain-2027"
    host = "bananain.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "蕉内"
    scope_description = "蕉内 2027 官方北森校园 Category=2 无筛选公开全目录；排除实习"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "蕉内目录混入非校招类别")
        check(text(row.get("Kind")) in {"全职", "实习"}, "蕉内岗位性质未知")
        return True


class JlcEhr2027(Zhiye):
    name = "zhiye-jlcehr-2027"
    host = "jlcehr.zhiye.com"
    listing_complete = True
    regular_only = True
    listing_unit_fallback = "嘉立创"
    scope_description = "嘉立创独立北森校园 Category=2 全目录；仅 2027 届全职岗位"

    def in_scope(self, row: dict[str, Any]) -> bool:
        check(str(row.get("CategoryId")) == "2", "嘉立创目录混入非校招类别")
        kind = text(row.get("Kind"))
        check(kind in {"全职", "实习", "其他"}, "嘉立创岗位性质未知")
        if kind != "全职":
            return False
        body = text(row.get("JobAdName")) + " " + text(row.get("Require"))
        return "2027" in body or "27届" in body


TENANTS = (
    JlcEhr2027,
    Bananain2027,
    UnitreeCampus,
    Cansemi2027,
    ShukunCampus,
    XtransferCampus,
    Esign2027,
    Megarobo2027,
    StarChargeCampus,
    AdoptACow2027,
    ZhuanzhuanCampus,
    KkGroup2027,
    Weidian2027,
    Vivo2027,
    CixinCampus,
    YmtcCampus,
    CxmtCampus,
    DreameCampus,
    AescCampus,
    GalaxyCampus,
    LeheCampus,
    AispeechCampus,
    ZhihuiyaCampus,
    HellobikeCampus,
    CasSpaceCampus,
    IrootechCampus,
    JunlebaoCampus,
    SvoltCampus,
    HairoboticsCampus,
    FoxEssCampus,
    GalaxeaCampus,
    HuiceCampus,
    SpacesailCampus,
    NarwalCampus,
    XagCampus,
    ShenghongCampus,
    BusyMingCampus,
    SunartCampus,
    YonghuiCampus,
    GrandtradeCampus,
    MediatekCampus,
    XaecCampus,
    TaikangCampus,
    WingtechCampus,
    Vanchen2027,
    TongkunCampus,
    CcccGroupCampus,
    SinosigGroupCampus,
    GuotaiHuashengCampus,
    Mxbc2027,
    GenertecCampus,
    Sph2027,
    Zhenshi2027,
    Cinda2027,
    CmhkParent,
    YuntianhuaParent,
    ChinaLifeGroup,
    PICCGroup,
    Chery,
    Mindray,
    Shenzhou,
    LuzhouLaojiao,
    Huafeng,
    Infore,
    Seres,
    Shrcb,
    Haid,
    Dahua,
    Baic,
    Naura,
    Poly,
    Xiangyu,
    Changan,
    DigitalChina,
    Bosc,
    Sinotrans,
    Sany,
    Transsion,
    Bocd,
    Cscb,
    Dsbj,
    Sailun,
    Csc108,
    Tsingtao,
    Yuhong,
    Iflytek,
    Goldwind,
    Mengniu,
    Leapmotor,
    Mywind,
    Popmart,
    Szgas,
    Ovt,
    Juhua,
    NewHope,
    CNAF,
    Greentown,
    BankOfBeijing,
    ENN,
    Beike,
    SMIC,
    Sunwoda,
    ZhongyuanBank,
    Vital,
    WuxiApptec,
    Gotion,
    CALB,
    CICC,
    Jiangling,
    Avary,
    ChinaStock,
    AUX,
)
