import json
from datetime import datetime
from pathlib import Path
from typing import Any

from job_crawler.adapters.feishu import Jtexpress
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
