from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest

from job_crawler.adapters.hotjob import ChanghongListed
from job_crawler.models import Source
from job_crawler.transport import CrawlError


def adapter(now: datetime) -> ChanghongListed:
    return ChanghongListed(
        Source(
            source_id="COM0194",
            company_id="COM0194",
            company="四川长虹电器股份有限公司",
            url=f"https://{ChanghongListed.host}/",
        ),
        Mock(),
        now,
    )


def tree() -> dict[str, Any]:
    return {
        "orgList": [
            {
                "code": "0/100201",
                "nameCh": "四川长虹电子控股集团有限公司",
                "positionsNum": 5,
                "childNodes": [
                    {
                        "code": "0/100201/103713",
                        "nameCh": "四川长虹电器股份有限公司",
                        "positionsNum": 3,
                        "childNodes": [
                            {
                                "code": "0/100201/103713/103922",
                                "nameCh": "消费者BG",
                                "positionsNum": 2,
                                "childNodes": [],
                            }
                        ],
                    },
                    {
                        "code": "0/100201/1037130",
                        "nameCh": "其他板块",
                        "positionsNum": 2,
                        "childNodes": [],
                    },
                ],
            }
        ]
    }


def test_listed_root_descendants_and_neighbor_prefix(now: datetime) -> None:
    a = adapter(now)
    a.validate_terms(tree())
    assert a.include_listing({"orgCode": "0/100201/103713", "company": "四川长虹电器股份有限公司"})
    assert a.include_listing(
        {"orgCode": "0/100201/103713/103922/department", "company": "消费者BG"}
    )
    assert not a.include_listing({"orgCode": "0/100201/1037130", "company": "其他板块"})
    assert a.tree_expected == 5 and a.own_expected == 3
    with pytest.raises(CrawlError):
        a.include_listing({"orgCode": "0/100201/unknown", "company": "未知"})


@pytest.mark.parametrize("failure", ["root", "listed", "count"])
def test_changed_entity_tree_fails(now: datetime, failure: str) -> None:
    data = tree()
    if failure == "root":
        data["orgList"][0]["nameCh"] = "另一集团"
    elif failure == "listed":
        data["orgList"][0]["childNodes"][0]["nameCh"] = "同名其他主体"
    else:
        data["orgList"][0]["childNodes"][0]["positionsNum"] = 6
    with pytest.raises(CrawlError):
        adapter(now).validate_terms(data)
