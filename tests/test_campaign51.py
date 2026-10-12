"""51job campaign arrays, card IDs and city-specific jobs must all be covered."""

from datetime import datetime
from typing import Any

from job_crawler.adapters.campaign51 import ChinaGas, Lens, TianjinBank, split_jobinfo
from job_crawler.models import Source


class Page:
    def __init__(self, session: "Replay"):
        self.session = session

    async def content(self) -> str:
        return self.session.pages[self.session.url]

    async def evaluate(self, script: str) -> Any:
        if script == "() => window.obj":
            return self.session.rows["obj"]
        if script == "() => typeof jobListData === 'undefined' ? null : jobListData":
            return self.session.rows["jobListData"]
        raise AssertionError(script)


class Replay:
    last_evidence = "initial.json"

    def __init__(self, pages: dict[str, str], rows: dict[str, list[dict[str, str]]] | None = None):
        self.pages = pages
        self.rows = rows or {}
        self.url = ""
        self.page = Page(self)

    async def open(self, url: str, *, ready_endpoints: tuple[str, ...] = ()) -> None:
        assert url in self.pages
        self.url = url
        self.last_evidence = url.rsplit("/", 1)[-1] + ".json"

    def snapshot(self, label: str, html: str) -> str:
        assert html
        self.last_evidence = label + ".json"
        return self.last_evidence

    async def observed(self, needle: str) -> dict[str, Any]:
        raise AssertionError("static page has no API")

    async def request(
        self, url: str, *, payload: dict[str, Any] | None = None, detail: bool = False
    ) -> dict[str, Any]:
        raise AssertionError("static page has no API")


def source(adapter: type[Lens] | type[ChinaGas] | type[TianjinBank]) -> Source:
    return Source(
        source_id={
            "lens-static": "COM0245",
            "chinagas-static": "COM0259",
            "tjyh-static": "COM0406",
        }[adapter.name],
        company_id="COMTEST",
        company="测试企业",
        url=f"https://{adapter.host}{adapter.path}",
    )


def apply(job_id: str, *, ctmid: str = "1") -> str:
    return f"https://xyz.51job.com/external/apply.aspx?jobid={job_id}&ctmid={ctmid}"


def lens_row(job_id: str, region: str) -> dict[str, str]:
    return {
        "attr5": apply(job_id),
        "attr9": region,
        "value": f"工程师{job_id}",
        "岗位职责": "开发系统",
        "岗位要求": "本科及以上",
        "attr2": "岗位职责：开发系统<br>岗位要求：本科及以上<br>工作地点：浏阳园区",
    }


async def test_lens_uses_full_array_instead_of_visible_first_region(now: datetime) -> None:
    url = source(Lens).url
    html = f"""<div class='tab'><div>湖南长沙</div><div>湖南湘潭</div></div>
    <div class='zw'><a href='{apply("1")}'></a></div>"""
    replay = Replay({url: html}, {"obj": [lens_row("1", "湖南长沙"), lens_row("2", "湖南湘潭")]})
    result = await Lens(source(Lens), replay, now).collect()
    assert result.coverage_issues() == []
    assert [job.source_key for job in result.jobs] == ["1", "2"]
    assert result.jobs[0].address == "浏阳园区"
    assert result.jobs[0].published == ""


async def test_lens_duplicate_or_missing_body_fails_coverage(now: datetime) -> None:
    url = source(Lens).url
    html = f"<div class='tab'><div>湖南长沙</div></div><div class='zw'><a href='{apply('1')}'></a></div>"
    duplicate = Replay({url: html}, {"obj": [lens_row("1", "湖南长沙")] * 2})
    assert (await Lens(source(Lens), duplicate, now).collect()).coverage_issues()
    missing = lens_row("1", "湖南长沙") | {"岗位要求": ""}
    assert (
        await Lens(source(Lens), Replay({url: html}, {"obj": [missing]}), now).collect()
    ).coverage_issues()


async def test_lens_robot_company_tab_uses_explicit_address_for_location(now: datetime) -> None:
    url = source(Lens).url
    html = f"<div class='tab'><div>智能机器人公司</div></div><div class='zw'><a href='{apply('1')}'></a></div>"
    row = lens_row("1", "智能机器人公司")
    row["attr2"] = row["attr2"].replace("浏阳园区", "长沙浏阳园区")
    result = await Lens(source(Lens), Replay({url: html}, {"obj": [row]}), now).collect()
    assert result.coverage_issues() == []
    assert result.jobs[0].unit == "智能机器人公司"
    assert result.jobs[0].location == "湖南长沙"
    changed = row | {"attr2": row["attr2"].replace("长沙浏阳园区", "未知园区")}
    blocked = await Lens(source(Lens), Replay({url: html}, {"obj": [changed]}), now).collect()
    assert blocked.coverage_issues()


def gas_pages(ids: list[str]) -> dict[str, str]:
    home = source(ChinaGas).url
    directory = "https://campus.51job.com/chinagasholdings/page2.html"
    return {
        home: '<a href="page2.html">校园招聘</a>',
        directory: '<div class="listbox">'
        + "".join(
            f'<div class="list" jobid="{job_id}"><div class="list-detail">'
            f'<a class="apply" href="{apply(job_id)}"></a></div></div>'
            for job_id in ids
        )
        + "</div>",
    }


def gas_row(job_id: str) -> dict[str, str]:
    return {
        "jobid": job_id,
        "ctmid": "1",
        "jobname": "储备干部",
        "jobarea": "深圳",
        "jobinfo": "任职要求：本科及以上\n岗位职责：负责项目交付",
    }


async def test_chinagas_reconciles_array_and_dom(now: datetime) -> None:
    result = await ChinaGas(
        source(ChinaGas),
        Replay(gas_pages(["1", "2"]), {"jobListData": [gas_row("1"), gas_row("2")]}),
        now,
    ).collect()
    assert result.coverage_issues() == []
    assert result.scopes[0].expected == 2
    assert result.jobs[0].duties == "负责项目交付"
    assert result.jobs[0].requirements == "本科及以上"


async def test_chinagas_rejects_missing_or_duplicate_ids(now: datetime) -> None:
    missing = await ChinaGas(
        source(ChinaGas),
        Replay(gas_pages(["1"]), {"jobListData": [gas_row("2")]}),
        now,
    ).collect()
    assert missing.coverage_issues()
    duplicate = await ChinaGas(
        source(ChinaGas),
        Replay(gas_pages(["1", "1"]), {"jobListData": [gas_row("1"), gas_row("1")]}),
        now,
    ).collect()
    assert duplicate.coverage_issues()

    empty = await ChinaGas(
        source(ChinaGas), Replay(gas_pages([]), {"jobListData": []}), now
    ).collect()
    assert empty.coverage_issues()


async def test_chinagas_rejects_apply_link_with_different_tenant(now: datetime) -> None:
    pages = gas_pages(["1"])
    target = "https://campus.51job.com/chinagasholdings/page2.html"
    pages[target] = pages[target].replace("ctmid=1", "ctmid=2")
    result = await ChinaGas(
        source(ChinaGas), Replay(pages, {"jobListData": [gas_row("1")]}), now
    ).collect()
    assert result.coverage_issues()


def bank_pages(*, special: str | None = None) -> dict[str, str]:
    home = source(TianjinBank).url
    hot = "https://campus.51job.com/tjyh_2026/job.html"
    special_url = "https://campus.51job.com/tjyh_2026/jobs.html"
    return {
        home: '<a href="job.html">热招岗位</a><a href="jobs.html">专项招聘</a>',
        hot: f"""<div class='jobContainer'>
          <div class='jobtitle'>总行科技人才</div>
          <div class='jobinfo'><p class='text1'>开发软件</p>
            <div class='jobt'>岗位要求</div><p class='text2'>硕士及以上</p>
            <div class='jobt'>工作地点</div><p class='text2'>天津总部</p>
            <a class='submit' href='{apply("1")}'></a></div>
          <div class='jobtitle'>营业网点岗位</div>
          <div class='jobinfo'><p class='text1'>服务客户</p>
            <div class='jobt'>岗位要求</div><p class='text2'>本科及以上</p>
            <div class='jobcity' data-url='{apply("2")}'>天津市东丽区</div>
            <div class='jobcity' data-url='{apply("3")}'>天津市津南区</div></div>
          </div>""",
        special_url: special
        if special is not None
        else f"""<div class='kuang1'><div class='content1'><p>2026届毕业生</p></div></div>
        <div class='content'><p class='jobtips'>营业网点业务类岗位</p>
          <div class='jobcity' data-url='{apply("4")}'>天津市宝坻区</div></div>""",
    }


async def test_tianjin_bank_expands_all_city_ids_and_both_branches(now: datetime) -> None:
    result = await TianjinBank(source(TianjinBank), Replay(bank_pages()), now).collect()
    assert result.coverage_issues() == []
    assert [scope.expected for scope in result.scopes] == [3, 1]
    assert [job.source_key for job in result.jobs] == ["1", "2", "3", "4"]
    assert result.jobs[2].location == "天津市津南区"


async def test_tianjin_bank_does_not_hide_special_branch_failure(now: datetime) -> None:
    result = await TianjinBank(
        source(TianjinBank), Replay(bank_pages(special="<div>页面结构变化</div>")), now
    ).collect()
    assert len(result.jobs) == 3
    assert result.coverage_issues()
    assert not result.scopes[1].terminal


async def test_tianjin_bank_rejects_reused_city_apply_id(now: datetime) -> None:
    pages = bank_pages()
    hot = "https://campus.51job.com/tjyh_2026/job.html"
    pages[hot] = pages[hot].replace(apply("3"), apply("2"))
    result = await TianjinBank(source(TianjinBank), Replay(pages), now).collect()
    assert result.coverage_issues()


def test_split_jobinfo_supports_requirement_first() -> None:
    assert split_jobinfo("岗位要求\n本科及以上\n岗位职责：负责研发") == ("负责研发", "本科及以上")
