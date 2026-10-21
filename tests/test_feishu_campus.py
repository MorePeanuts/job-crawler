import json
from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.adapters.feishu import (
    DewuCampus,
    Innolight,
    Jtexpress,
    NineDragons,
    SpiritAICampus,
    Xiaomi,
    YuanqiCampus,
)
from job_crawler.models import Source


class Session:
    last_evidence = "fixture"

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("单页夹具不应请求补充分页")

    def __init__(self, output: Path):
        self.output = output

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url.endswith("/478610/position/list")

    async def observed(self, needle: str) -> dict[str, Any]:
        assert needle.endswith("/api/v1/search/job/posts?")
        return {
            "url": "https://jtexpress.jobs.feishu.cn/api/v1/search/job/posts?"
            "keyword=&limit=10&offset=0&job_category_id_list=&tag_id_list="
            "&location_code_list=&subject_id_list=&recruitment_id_list="
            "&portal_type=6&job_function_id_list=&storefront_id_list="
            "&_signature=verified",
            "status": 200,
            "body": json.dumps(
                {
                    "code": 0,
                    "data": {
                        "count": 1,
                        "job_post_list": [
                            {
                                "id": "123",
                                "title": "算法研究员",
                                "description": "研究算法",
                                "requirement": "硕士及以上",
                                "job_subject": None,
                                "recruit_type": {"name": "实习"},
                                "job_category": {"name": "研发"},
                                "city_list": [{"name": "上海"}],
                                "publish_time": 1791807532227,
                            }
                        ],
                    },
                }
            ),
        }


async def test_custom_feishu_portal_uses_recruit_type_and_detail_route(
    tmp_path: Path, now: datetime
) -> None:
    source = Source(
        source_id="COM0217",
        company_id="COM0217",
        company="极兔速递环球有限公司",
        url="https://jtexpress.jobs.feishu.cn/478610",
    )
    result = await Jtexpress(source, Session(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].work_type == "实习"
    assert result.jobs[0].category_raw == "研发"
    assert (
        result.jobs[0].source_url == "https://jtexpress.jobs.feishu.cn/478610/position/123/detail"
    )


class XiaomiSession(Session):
    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://xiaomi.jobs.f.mioffice.cn/campus/"

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        response["url"] = response["url"].replace(
            "jtexpress.jobs.feishu.cn", "xiaomi.jobs.f.mioffice.cn"
        )
        payload = json.loads(response["body"])
        row = payload["data"]["job_post_list"][0]
        row["recruit_type"]["name"] = "正式"
        row["job_subject"] = {"name": {"zh_cn": "2027届校园招聘计划"}}
        response["body"] = json.dumps(payload)
        return response


async def test_xiaomi_official_linked_campus_tenant(tmp_path: Path, now: datetime) -> None:
    source = Source(
        source_id="COM0058",
        company_id="COM0058",
        company="小米集团",
        url="https://xiaomi.jobs.f.mioffice.cn/campus/",
    )
    result = await Xiaomi(source, XiaomiSession(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].work_type == "校招"
    assert result.jobs[0].batch == "2027届校园招聘计划"
    assert (
        result.jobs[0].source_url == "https://xiaomi.jobs.f.mioffice.cn/campus/position/123/detail"
    )


class InnolightSession(XiaomiSession):
    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://zj-innolight.jobs.feishu.cn/300308/position/list"

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        response["url"] = response["url"].replace(
            "xiaomi.jobs.f.mioffice.cn", "zj-innolight.jobs.feishu.cn"
        )
        return response


async def test_innolight_group_portal_detail_route(tmp_path: Path, now: datetime) -> None:
    source = Source(
        source_id="COM0386",
        company_id="COM0386",
        company="中际旭创股份有限公司",
        url="https://zj-innolight.jobs.feishu.cn/300308/position/list",
    )
    result = await Innolight(source, InnolightSession(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert (
        result.jobs[0].source_url
        == "https://zj-innolight.jobs.feishu.cn/300308/position/123/detail"
    )


class NineDragonsSession(XiaomiSession):
    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://ninedragonspaper.jobs.feishu.cn/502309/position/list"

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        response["url"] = response["url"].replace(
            "xiaomi.jobs.f.mioffice.cn", "ninedragonspaper.jobs.feishu.cn"
        )
        payload = json.loads(response["body"])
        payload["data"]["job_post_list"][0]["job_subject"] = None
        response["body"] = json.dumps(payload)
        return response


async def test_nine_dragons_campus_route_and_formal_type(tmp_path: Path, now: datetime) -> None:
    source = Source(
        source_id="COM0275",
        company_id="COM0275",
        company="玖龙纸业（控股）有限公司",
        url="https://ninedragonspaper.jobs.feishu.cn/502309/position/list",
    )
    result = await NineDragons(source, NineDragonsSession(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].work_type == "校招"
    assert (
        result.jobs[0].source_url
        == "https://ninedragonspaper.jobs.feishu.cn/502309/position/123/detail"
    )


class SpiritAISession(Session):
    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://nwd4iy9rd2s.jobs.feishu.cn/campusofSpiritAI/position/list"

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        response["url"] = response["url"].replace(
            "jtexpress.jobs.feishu.cn", "nwd4iy9rd2s.jobs.feishu.cn"
        )
        payload = json.loads(response["body"])
        row = payload["data"]["job_post_list"][0]
        row["job_subject"] = {"name": {"zh_cn": "【千寻智能2027届秋季校园招聘】"}}
        response["body"] = json.dumps(payload)
        return response


async def test_spirit_ai_campus_portal_identity(tmp_path: Path, now: datetime) -> None:
    source = Source(
        source_id="COM0599",
        company_id="COM0599",
        company="千寻智能",
        url="https://nwd4iy9rd2s.jobs.feishu.cn/campusofSpiritAI/position/list",
    )
    result = await SpiritAICampus(source, SpiritAISession(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].work_type == "实习"
    assert result.jobs[0].batch == "【千寻智能2027届秋季校园招聘】"
    assert (
        result.jobs[0].source_url
        == "https://nwd4iy9rd2s.jobs.feishu.cn/campusofSpiritAI/position/123/detail"
    )


class YuanqiSession(Session):
    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://k11pnjpvz1.jobs.feishu.cn/352020/position/list"

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        response["url"] = response["url"].replace(
            "jtexpress.jobs.feishu.cn", "k11pnjpvz1.jobs.feishu.cn"
        )
        payload = json.loads(response["body"])
        row = payload["data"]["job_post_list"][0]
        row["title"] = "校招-前沿部署工程师-27届"
        row["recruit_type"]["name"] = "正式"
        response["body"] = json.dumps(payload)
        return response


async def test_yuanqi_352020_campus_portal(tmp_path: Path, now: datetime) -> None:
    source = Source(
        source_id="COM0521",
        company_id="COM0521",
        company="元气森林",
        url="https://k11pnjpvz1.jobs.feishu.cn/352020/position/list",
    )
    result = await YuanqiCampus(source, YuanqiSession(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].work_type == "校招"
    assert (
        result.jobs[0].source_url == "https://k11pnjpvz1.jobs.feishu.cn/352020/position/123/detail"
    )


class DewuSession(YuanqiSession):
    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://poizon.jobs.feishu.cn/578078/position/list"

    async def observed(self, needle: str) -> dict[str, Any]:
        response = await super().observed(needle)
        response["url"] = response["url"].replace(
            "k11pnjpvz1.jobs.feishu.cn", "poizon.jobs.feishu.cn"
        )
        return response


async def test_dewu_578078_campus_portal(tmp_path: Path, now: datetime) -> None:
    source = Source(
        source_id="COM0523",
        company_id="COM0523",
        company="得物",
        url="https://poizon.jobs.feishu.cn/578078/position/list",
    )
    result = await DewuCampus(source, DewuSession(tmp_path), now).collect()
    assert not result.coverage_issues()
    assert result.jobs[0].work_type == "校招"
    assert result.jobs[0].source_url == "https://poizon.jobs.feishu.cn/578078/position/123/detail"
