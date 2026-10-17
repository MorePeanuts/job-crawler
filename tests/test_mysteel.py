from datetime import datetime

import pytest

from job_crawler.adapters.mysteel import MysteelCampus
from job_crawler.models import Source


def html() -> str:
    def card(title: str) -> str:
        return f"<dl><dt>{title}</dt><dd><p>岗位职责：</p><p>研究市场</p><p>任职要求：</p><p>本科应届生</p></dd></dl>"

    main = (
        '<ul id="main-nav">'
        + "".join(
            f'<li id="{key}">{label}</li>'
            for key, label in [
                ("position", "职业发展"),
                ("team", "团队风采"),
                ("bidding", "社会招聘"),
                ("recruit", "校园招聘"),
            ]
        )
        + "</ul>"
    )
    return (
        main
        + f"""<footer>上海钢联电子商务股份有限公司 版权所有</footer>
    <div id="recruit-box"><li id="business">业务板块</li><li id="recruit-role">职能板块</li><li id="recruit-application">应聘须知</li></div>
    <div id="recruit-content"><div class="wanted__item">{card("资讯实习生")}{card("海外实习生")}</div>
    <div class="wanted__item" style="display:none">{card("人力实习生")}{card("法务实习生")}</div>
    <div class="wanted__item"><dl><dt>福利待遇</dt></dl><dl><dt>投递方式</dt><p>工作地点：上海市宝山区园丰路68号</p></dl></div></div>"""
    )


class MysteelReplay:
    last_evidence = "fixture"

    def __init__(self, document: str):
        self.html = document
        self.page = self

    async def content(self) -> str:
        return self.html

    async def observed(self, needle: str) -> dict[str, object]:
        raise AssertionError("static tabs need no API")

    async def request(
        self, url: str, *, payload: dict[str, object] | None = None, detail: bool = False
    ) -> dict[str, object]:
        raise AssertionError("static tabs need no API")

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url == f"https://{MysteelCampus.host}{MysteelCampus.path}"


def adapter(document: str, now: datetime) -> MysteelCampus:
    return MysteelCampus(
        Source(
            source_id="COM0250",
            company_id="COM0250",
            company="上海钢联电子商务股份有限公司",
            url="https://about.mysteel.com/career/",
        ),
        MysteelReplay(document),
        now,
    )


async def test_all_hidden_interns_excluded(now: datetime) -> None:
    result = await adapter(html(), now).collect()
    assert not result.coverage_issues() and not result.jobs
    assert [
        (s.expected, s.listed, s.unique, s.skipped_out_of_scope, s.terminal) for s in result.scopes
    ] == [(2, 2, 2, 2, True)] * 2


async def test_formal_full_text_and_no_invented_dates(now: datetime) -> None:
    result = await adapter(html().replace("法务实习生", "法务校招生"), now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 1
    job = result.jobs[0]
    assert job.source_key == "recruit-role:法务校招生"
    assert job.duties == "研究市场" and job.requirements == "本科应届生"
    assert job.location == "上海市宝山区园丰路68号"
    assert not job.published and not job.deadline and not job.education


@pytest.mark.parametrize(
    "before,after",
    [
        ("职能板块", "博士岗位"),
        ("上海钢联电子商务股份有限公司", "其他集团"),
        ("法务实习生", "人力实习生"),
        ("岗位职责：", "职责待补"),
        ("</footer>", '</footer><div class="pager">下一页</div>'),
        ("本科应届生", '<a href="new.xlsx">附件</a>'),
        ("福利待遇", "新增岗位"),
        ("工作地点：", "公司地址："),
    ],
)
async def test_unproven_structure_fails(now: datetime, before: str, after: str) -> None:
    result = await adapter(html().replace(before, after), now).collect()
    assert result.coverage_issues()
