from datetime import datetime
from typing import Any

import pytest

from job_crawler.adapters.sbp import (
    LINKS,
    Cttq,
    Njcttq,
    Qingjiang,
    Tide,
    qingjiang_fields,
    tide_details,
    validate_members,
)
from job_crawler.models import Source


class Replay:
    last_evidence = "fixture"

    def __init__(self, html: str, detail: str = ""):
        self.html = html
        self.detail = detail
        self.page = self
        self.reads: list[str] = []

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        pass

    async def content(self) -> str:
        return self.html

    async def request_html(self, url: str, *, detail: bool = False) -> str:
        self.reads.append(url)
        assert detail
        return self.detail

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("HTML branch needs no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("HTML branch needs no API")


def source(host: str) -> Source:
    return Source(
        source_id="COM0432",
        company_id="COM0432",
        company="中国生物制药有限公司",
        url=f"https://{host}/",
    )


def qingjiang_html() -> str:
    cards = []
    for key, title, body in [
        (1, "营销实习生", "任职要求：本科"),
        (2, "分析研究员", "任职要求：从事药品研发分析工作1年以上"),
        (3, "合成研究员", "任职资格：应届硕士或本科一年以上工作经验者\n岗位职责：实验研究"),
        (4, "生产管培生", "全日制本科及以上学历，药学专业"),
    ]:
        cards.append(f"""<div class="panel"><div class="panel-title"><a><span>研发类</span><span>{title}</span><span>1</span><span>淮安市</span><span></span></a></div>
        <div class="zp_nei"><h2>招聘条件</h2><p>{body}</p></div><div class="zp_nei"><h2>联系方式</h2></div>
        <a class="join" href="human_zp_n.aspx?id={key}">我要应聘</a></div>""")
    return (
        '<a href="human_xy.aspx">校园招聘</a>江苏正大清江制药有限公司<div id="bs-collapse">'
        + "".join(cards)
        + "</div>"
    )


async def test_qingjiang_complete_inline_and_eligibility(now: datetime) -> None:
    replay = Replay(qingjiang_html())
    result = await Qingjiang(source(Qingjiang.host), replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 2
    assert result.scopes[0].expected == result.scopes[0].unique == 4
    assert result.scopes[0].skipped_out_of_scope == 2
    synth, trainee = result.jobs
    assert synth.education == "硕士" and synth.duties == "实验研究"
    assert synth.source_key == "qingjiang:3" and synth.company == "中国生物制药有限公司"
    assert trainee.unit == "江苏正大清江制药有限公司" and not trainee.duties
    assert not synth.published and not synth.deadline and not replay.reads


@pytest.mark.parametrize(
    "before,after",
    [("id=4", "id=3"), ("招聘条件", "岗位附件"), ("全日制本科", '<img src="new.png">全日制本科')],
)
async def test_qingjiang_incomplete_or_duplicate_fails(
    now: datetime, before: str, after: str
) -> None:
    result = await Qingjiang(
        source(Qingjiang.host), Replay(qingjiang_html().replace(before, after)), now
    ).collect()
    assert result.coverage_issues()


def tide_html() -> str:
    return """<div class="xiangqingtitle"><span>博士后<b class="applyStatus">(未申请)</b></span></div>
    <ul><li class="ntitle">招聘类别：</li><li>校园招聘</li><li class="ntitle">工作性质：</li><li>全职</li>
    <li class="ntitle">发布时间：</li><li>2026-09-29</li><li class="ntitle">截止时间：</li><li></li></ul>
    <div class="xiangqingtext"><p>工作地点：</p><p>北京市-亦庄开发区</p><p>工作职责：</p><p>研究药物</p><p>任职资格：</p><p>博士学历</p></div>
    <script>var jobAdId = 123;</script>"""


def test_tide_dates_and_identity() -> None:
    fields = tide_details(tide_html(), "博士后", "123")
    assert fields["published"] == "2026-09-29" and not fields["deadline"]
    assert fields["location"] == "北京市-亦庄开发区" and fields["duties"] == "研究药物"
    with pytest.raises(Exception, match="身份错配"):
        tide_details(tide_html(), "博士后", "124")
    with pytest.raises(Exception, match="不是校园"):
        tide_details(tide_html().replace("校园招聘", "社会招聘"), "博士后", "123")


async def test_tide_full_list_intern_exclusion(now: datetime) -> None:
    rows = "".join(
        f'<tr><td><a href="/zpdetail/{key}" jobadid="{key}">{title}</a></td><td>研发中心</td><td>研发中心</td><td>北京...</td></tr>'
        for key, title in [("123", "博士后"), ("124", "采购实习生")]
    )
    html = f'北京泰德制药股份有限公司 校招分类<table class="listtable"><tbody>{rows}</tbody></table><span class="tablenote">共2条记录</span>'
    replay = Replay(html, tide_html())
    result = await Tide(source(Tide.host), replay, now).collect()
    assert not result.coverage_issues() and len(result.jobs) == 1
    assert result.scopes[0].skipped_out_of_scope == 1
    assert replay.reads == ["https://tidepharm.zhiye.com/zpdetail/123"]
    missing = await Tide(
        source(Tide.host), Replay(html.replace("共2条", "共3条"), tide_html()), now
    ).collect()
    assert missing.coverage_issues()


def test_members_addition_or_missing_fails() -> None:
    html = (
        "中国生物制药<ul>"
        + "".join(
            f'<li><a title="{name}" href="{url}">{name}</a></li>' for name, url in LINKS.items()
        )
        + "</ul>"
    )
    validate_members(html)
    with pytest.raises(Exception, match="导航变化"):
        validate_members(
            html.replace("</ul>", '<a title="新增成员" href="https://new.example/">新增</a></ul>')
        )
    with pytest.raises(Exception, match="导航变化"):
        validate_members(html.replace("正大丰海", "未知成员"))


def test_member_keys_and_education_conditions(now: datetime) -> None:
    a = Cttq(source(Cttq.host), Replay(""), now)
    b = Njcttq(source(Njcttq.host), Replay(""), now)
    assert (
        a.job("same", title="岗位", source_url=a.source.url).source_key
        != b.job("same", title="岗位", source_url=b.source.url).source_key
    )
    assert a.entity_key("job:same") == "job:cttq:same"
    assert b.entity_key("job:same") == "job:njcttq:same"
    assert qingjiang_fields("任职资格：应届硕士或本科一年以上工作经验者")[2:] == ("硕士", True)
