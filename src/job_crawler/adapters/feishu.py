"""Feishu campus catalog pagination through the site's signed browser requests."""

import asyncio
import json
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.storage import write_json
from job_crawler.transport import BrowserSession, CrawlError

LIST_PATH = "/api/v1/search/job/posts"


def page_payload(response: dict[str, Any], host: str, offset: int) -> dict[str, Any]:
    url = urlsplit(response["url"])
    query = parse_qs(url.query, keep_blank_values=True)
    check(url.hostname == host and url.path == LIST_PATH, "飞书岗位响应来自未知接口")
    check(query.get("offset") == [str(offset)], "飞书岗位响应偏移量错误")
    check(query.get("portal_type") == ["6"], "飞书入口不是校园招聘")
    check(query.get("_signature", [""])[0] != "", "飞书分页签名缺失")
    for key in (
        "keyword",
        "job_category_id_list",
        "tag_id_list",
        "location_code_list",
        "subject_id_list",
        "recruitment_id_list",
        "job_function_id_list",
        "storefront_id_list",
    ):
        check(not query.get(key, [""])[0], f"飞书目录带有筛选 {key}")
    payload = json.loads(response["body"])
    check(payload.get("code") == 0, "飞书岗位接口失败")
    return payload["data"]


class Desaysv(Adapter):
    name = "feishu-desaysv"
    host = "yesv-desaysv.jobs.feishu.cn"
    path = "/campus/"
    detail_prefix = "/campus/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "德赛西威飞书校招门户公开全目录；由站点 UI 签名分页，实习由公共筛选排除"

    def in_scope(self, row: dict[str, Any], subject_name: str) -> bool:
        return True

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        observed = await self.session.observed(f"{LIST_PATH}?")
        size = int(parse_qs(urlsplit(observed["url"]).query)["limit"][0])
        check(0 < size <= 50, "飞书分页大小无效")
        scope = Scope(name="campus-portal-all-projects")
        self.result.scopes.append(scope)
        seen: set[str] = set()
        offset = 0
        response = observed
        while True:
            data = page_payload(response, self.host, offset)
            expected = int(data["count"])
            check(expected >= 0, "飞书岗位总数无效")
            if scope.expected is None:
                scope.expected = expected
            check(scope.expected == expected, "飞书分页期间岗位总数变化")
            evidence = session.output / f"feishu-list-offset-{offset}.json"
            write_json(evidence, {"url": response["url"], "data": data})
            session.last_evidence = str(evidence)
            rows = self.add_page(scope, data["job_post_list"], seen, lambda row: str(row["id"]))
            for row in rows:
                key = str(row["id"])
                subject = row.get("job_subject") or {}
                subject_name = text((subject.get("name") or {}).get("zh_cn"))
                if not self.in_scope(row, subject_name):
                    scope.skipped_out_of_scope += 1
                    continue
                recruit_type = row.get("recruit_type") or {}
                recruit_name = text(recruit_type.get("name"))
                title = text(row.get("title"))
                duties = text(row.get("description"))
                requirements = text(row.get("requirement"))
                internship = any("实习" in value for value in (subject_name, recruit_name, title))
                check(bool(title) and (bool(duties) or internship), "飞书正式岗位标题或职责缺失")
                cities = row.get("city_list") or []
                check(isinstance(cities, list), "飞书岗位城市结构改变")
                location = "、".join(
                    dict.fromkeys(text(city.get("name")) for city in cities if city.get("name"))
                )
                function = row.get("job_function") or {}
                category = row.get("job_category") or {}
                page = f"https://{self.host}{self.detail_prefix}/{key}/detail"
                job = self.job(
                    key,
                    title=title,
                    source_url=page,
                    apply_url=page,
                    work_type="实习" if internship else "校招",
                    batch=subject_name,
                    category_raw=text(function.get("name") or category.get("name")),
                    location=location,
                    duties=duties,
                    requirements=requirements,
                    published=text(row.get("publish_time")),
                    field_sources={
                        "duties": "search/job/posts.data.job_post_list[].description",
                        "requirements": "search/job/posts.data.job_post_list[].requirement",
                        "published": "search/job/posts.data.job_post_list[].publish_time",
                        "location": "search/job/posts.data.job_post_list[].city_list[].name",
                        "deadline": "source_missing",
                    },
                )
                job.evidence = [str(evidence)]
                resolved = self.before_detail(f"job:{key}", row, scope, job, evidence=str(evidence))
                if resolved is not None:
                    self.result.jobs.extend(resolved)
                    continue
                self.result.jobs.append(job)
                scope.details += 1
                self.remember(f"job:{key}", row, [job])
            if scope.unique >= expected:
                scope.terminal = True
                break
            check(bool(rows) and len(rows) <= size, "飞书分页提前为空或超出页大小")
            offset += len(rows)
            check(session.page is not None, "飞书浏览器页面丢失")
            assert session.page is not None
            session.consume_request()
            await session.page.locator('li[title="下一页"]').click(timeout=10000)
            response = await self._wait_page(session, offset)

    async def _wait_page(self, session: BrowserSession, offset: int) -> dict[str, Any]:
        for _ in range(40):
            if session.pending:
                await asyncio.gather(*list(session.pending), return_exceptions=True)
            matches = [
                item
                for item in session.responses
                if urlsplit(item["url"]).path == LIST_PATH
                and parse_qs(urlsplit(item["url"]).query).get("offset") == [str(offset)]
                and item["status"] == 200
            ]
            if matches:
                return matches[-1]
            await asyncio.sleep(0.5)
        raise CrawlError("api_not_observed", f"飞书分页 offset={offset} 的签名响应未出现")


class Xpeng(Desaysv):
    name = "feishu-xpeng"
    host = "xiaopeng.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)


class Nio(Desaysv):
    name = "feishu-nio"
    host = "nio.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)


class Jtexpress(Desaysv):
    name = "feishu-jtexpress"
    host = "jtexpress.jobs.feishu.cn"
    path = "/478610/position/list"
    detail_prefix = "/478610/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)


class Xiaomi(Desaysv):
    name = "feishu-xiaomi"
    host = "xiaomi.jobs.f.mioffice.cn"
    path = "/campus/"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "小米集团官方 2027 校园门户公开全目录；实习由公共筛选排除"


class Aac(Desaysv):
    name = "feishu-aac"
    host = "talent.aactechnologies.com"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "瑞声科技官方 2027 校园门户公开全目录；实习由公共筛选排除"


class Innolight(Desaysv):
    name = "feishu-innolight"
    host = "zj-innolight.jobs.feishu.cn"
    path = "/300308/position/list"
    detail_prefix = "/300308/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "中际旭创官方 2027 校园门户公开全目录；实习由公共筛选排除"


class NineDragons(Desaysv):
    name = "feishu-nine-dragons"
    host = "ninedragonspaper.jobs.feishu.cn"
    path = "/502309/position/list"
    detail_prefix = "/502309/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "玖龙纸业飞书校招 portal_type=6 无筛选全目录；实习由公共筛选排除"


class SpiritAICampus(Desaysv):
    name = "feishu-spirit-ai-campus"
    host = "nwd4iy9rd2s.jobs.feishu.cn"
    path = "/campusofSpiritAI/position/list"
    detail_prefix = "/campusofSpiritAI/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "千寻智能飞书校招 portal_type=6 无筛选全目录；实习由公共筛选排除"


class YuanqiCampus(Desaysv):
    name = "feishu-yuanqi-campus"
    host = "k11pnjpvz1.jobs.feishu.cn"
    path = "/352020/position/list"
    detail_prefix = "/352020/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "元气森林 352020 校园项目 portal_type=6 全目录；另一个实习门户不在范围"


class DewuCampus(Desaysv):
    name = "feishu-dewu-campus"
    host = "poizon.jobs.feishu.cn"
    path = "/578078/position/list"
    detail_prefix = "/578078/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "得物飞书校园项目 portal_type=6 全目录；按源招聘类型排除实习"


class ZeronCampus(Desaysv):
    name = "feishu-zeron-campus"
    host = "zeron.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "零一汽车飞书 2027 校园门户 portal_type=6 全目录；按源类型排除实习"


class AgibotCampus(Desaysv):
    name = "feishu-agibot-campus"
    host = "agirobot.jobs.feishu.cn"
    path = "/campusrecruitment/position/list"
    detail_prefix = "/campusrecruitment/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "智元机器人官网链接的集团飞书校园门户全目录；含官网披露的旗下业务，实习排除"


class KuroCampus(Desaysv):
    name = "feishu-kuro-campus"
    host = "kurogame.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "库洛游戏 2027 校园门户全目录；按项目和标题排除日常实习"


class DcarCampus(Desaysv):
    name = "feishu-dcar-campus"
    host = "dcar.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "懂车帝官方飞书 campus 门户无筛选全目录；按项目与标题排除实习"


class MomentaCampus(Desaysv):
    name = "feishu-momenta-campus"
    host = "momenta.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "Momenta 飞书校园门户全目录；按项目与标题排除日常实习"


class NeolixCampus(Desaysv):
    name = "feishu-neolix-campus"
    host = "r3c0qt6yjw.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "新石器 2027 飞书校园门户全目录；按源招聘类型和项目排除实习"


class X2RobotCampus(Desaysv):
    name = "feishu-x2robot-campus"
    host = "x2-robot.jobs.feishu.cn"
    path = "/912130/position/list"
    detail_prefix = "/912130/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "自变量机器人官网所链飞书 27 届校园门户全目录；排除实习项目"


class BaichuanOriginCampus(Desaysv):
    name = "feishu-baichuan-origin-campus"
    host = "cq6qe6bvfr6.jobs.feishu.cn"
    path = "/646926/"
    detail_prefix = "/646926/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "百川智能源点顶尖人才计划公开全目录；只纳入应届正式岗位"


class DuxiaomanCampus(Desaysv):
    name = "feishu-duxiaoman-campus"
    host = "campus.duxiaoman.com"
    path = "/051736/position/list"
    detail_prefix = "/051736/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "度小满独立校园站飞书 portal_type=6 全目录；排除实习标题"


class EcoflowCampus(Desaysv):
    name = "feishu-ecoflow-campus"
    host = "jobs.ecoflow.com"
    path = "/602892/position/list"
    detail_prefix = "/602892/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "正浩创新官网所链飞书 2027 校招全目录；排除日常及校招实习"


class LilithCampus(Desaysv):
    name = "feishu-lilith-campus"
    host = "lilithgames.jobs.feishu.cn"
    path = "/campus"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "莉莉丝官网所链飞书 2027 秋招正式校园门户全目录"


class LandspaceCampus(Desaysv):
    name = "feishu-landspace-campus"
    host = "uq1h428xyc.jobs.feishu.cn"
    path = "/522146/position/list"
    detail_prefix = "/522146/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "蓝箭航天官网所链 2027 届飞书校园门户全目录；实习标题排除"


class ZkjCampus(Desaysv):
    name = "feishu-zkj-campus"
    host = "weikezhijia.jobs.feishu.cn"
    path = "/952383/position/list"
    detail_prefix = "/952383/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "中关村科金官网所链 952383 飞书校园门户无筛选全目录"


class BokeCampus(Desaysv):
    name = "feishu-boke-campus"
    host = "boke.jobs.feishu.cn"
    path = "/581609/position/list"
    detail_prefix = "/581609/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "波克官网所链飞书 581609 校园门户公开无筛选全目录；实习按源性质排除"


class SmartlogicCampus(Desaysv):
    name = "feishu-smartlogic-campus"
    host = "smartlogictech.jobs.feishu.cn"
    path = "/xiaozhao/position/list"
    detail_prefix = "/xiaozhao/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "思朗科技 2027 飞书校园门户 portal_type=6 无筛选全目录；实习按源性质排除"


class Ai2RoboticsCampus(Desaysv):
    name = "feishu-ai2robotics-campus"
    host = "ai2robotics.jobs.feishu.cn"
    path = "/094992/position/list"
    detail_prefix = "/094992/position"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "智平方独立飞书校园门户 portal_type=6 全目录；实习按源性质排除"


class RigolCampus(Desaysv):
    name = "feishu-rigol-campus"
    host = "rigolportal.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "普源精电独立飞书校园门户 portal_type=6 无筛选全目录；实习排除"


class Moonton2027(Desaysv):
    name = "feishu-moonton-2027"
    host = "moonton.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "沐瞳科技 2027 飞书校园门户 portal_type=6 全目录；排除实习"


class Modelbest2027(Desaysv):
    name = "feishu-modelbest-2027"
    host = "modelbest.jobs.feishu.cn"
    path = "/campus/position/list"
    ready_endpoints = (f"https://{host}{LIST_PATH}?",)
    scope_description = "面壁智能飞书校园门户 portal_type=6 全目录；只纳入 2027 校园项目正式岗位"

    def in_scope(self, row: dict[str, Any], subject_name: str) -> bool:
        return "2027" in subject_name


TENANTS = (
    RigolCampus,
    Moonton2027,
    Modelbest2027,
    Ai2RoboticsCampus,
    SmartlogicCampus,
    BokeCampus,
    ZkjCampus,
    LilithCampus,
    LandspaceCampus,
    Desaysv,
    Xpeng,
    Nio,
    Jtexpress,
    Xiaomi,
    Aac,
    Innolight,
    NineDragons,
    SpiritAICampus,
    YuanqiCampus,
    DewuCampus,
    ZeronCampus,
    AgibotCampus,
    KuroCampus,
    DcarCampus,
    MomentaCampus,
    NeolixCampus,
    X2RobotCampus,
    BaichuanOriginCampus,
    DuxiaomanCampus,
    EcoflowCampus,
)
