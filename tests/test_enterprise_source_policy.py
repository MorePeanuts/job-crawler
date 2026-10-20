"""School and public talent pages cannot stand in for company recruitment sites."""

from pathlib import Path

import pytest

from job_crawler.config import Settings, load_bindings
from job_crawler.models import Binding, Source
from job_crawler.runner import preflight
from job_crawler.source_policy import is_non_enterprise_source
from job_crawler.sources import read_sources


@pytest.mark.parametrize(
    "url",
    [
        "https://career.csu.edu.cn/largefairs/company/id/1312",
        "https://job.xasyxy.com/news/view/aid/408964",
        "https://kmust.uat.bysjy.com.cn/detail/career?id=714546",
        "https://qz.hnrcsc.com/ptemp/#/positionB/consultdetailss",
    ],
)
def test_non_enterprise_pages_cannot_be_bound(url: str) -> None:
    assert is_non_enterprise_source(url)
    source = Source(source_id="TEST", company_id="TEST", company="测试企业", url=url)
    with pytest.raises(ValueError, match="非企业招聘入口"):
        preflight([source], {"TEST": Binding(adapter="hotjob-lining-2027")}, Settings())


def test_official_platform_stays_eligible() -> None:
    assert not is_non_enterprise_source("https://wecruit.hotjob.cn/SU123/pb/school.html")


def test_default_bindings_exclude_known_non_enterprise_sources() -> None:
    sources = {source.source_id: source for source in read_sources(Path("sites/sources.csv"))[0]}
    bindings = load_bindings(Path("sites/bindings.toml"))
    assert not [
        source_id
        for source_id, binding in bindings.items()
        if binding.enabled and is_non_enterprise_source(sources[source_id].url)
    ]
