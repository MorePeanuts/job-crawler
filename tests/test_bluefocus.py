import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.bluefocus import BlueFocus
from job_crawler.models import Source
from job_crawler.transport import Session


class Replay:
    last_evidence = "fixture"

    def __init__(self, output: Path, kind: str = "201", identity: bool = True):
        self.output = output
        self.page = self
        self.kind = kind
        self.identity = identity

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == "https://bluefocus.jobs.feishu.cn/066083/position/list"

    async def content(self) -> str:
        return "加入蓝色光标集团" if self.identity else "未知企业"

    async def observed(self, needle: str) -> dict[str, object]:
        assert needle == "/api/v1/search/job/posts?"
        kind = self.kind
        return {
            "url": "https://bluefocus.jobs.feishu.cn/api/v1/search/job/posts?"
            "limit=10&offset=0&portal_type=6&_signature=fixture",
            "body": json.dumps(
                {
                    "code": 0,
                    "data": {
                        "count": 1,
                        "job_post_list": [
                            {
                                "id": "123",
                                "title": "AI产品",
                                "description": "负责产品设计",
                                "requirement": "本科及以上",
                                "recruit_type": {
                                    "id": kind,
                                    "name": {"201": "正式", "202": "实习", "101": "全职"}[kind],
                                    "parent": {
                                        "id": "1" if kind == "101" else "2",
                                        "name": "社招" if kind == "101" else "校招",
                                    },
                                },
                                "job_post_info": {"address_list": [{"name": "公开办公地址"}]},
                                "city_list": [{"name": "上海"}, {"name": "深圳"}],
                            }
                        ],
                    },
                }
            ),
        }


def adapter(session: Replay, now: datetime) -> BlueFocus:
    return BlueFocus(
        Source(
            source_id="COM0258",
            company_id="COM0258",
            company="北京蓝色光标数据科技集团股份有限公司",
            url="https://bluefocus.jobs.feishu.cn/066083",
        ),
        cast(Session, session),
        now,
    )


@pytest.mark.parametrize("kind,expected", [("201", "校招"), ("202", "实习")])
async def test_type_full_address_and_campus_route(
    tmp_path: Path, now: datetime, kind: str, expected: str
) -> None:
    result = await adapter(Replay(tmp_path, kind), now).collect()
    assert result.coverage_issues() == []
    assert result.scopes[0].unique == result.scopes[0].expected == 1
    job = result.jobs[0]
    assert job.source_url.endswith("/066083/position/123/detail")
    assert job.work_type == expected
    assert job.location == "上海、深圳" and job.address == "公开办公地址"
    assert job.education == "" and job.deadline == "" and job.published == ""


@pytest.mark.parametrize("kind,identity", [("101", True), ("201", False)])
async def test_social_type_and_wrong_identity_never_succeed(
    tmp_path: Path, now: datetime, kind: str, identity: bool
) -> None:
    result = await adapter(Replay(tmp_path, kind, identity), now).collect()
    assert result.coverage_issues() and result.jobs == []
