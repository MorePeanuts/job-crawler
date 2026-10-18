"""iMatch whole-list, graph, scope and public detail regressions."""

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from job_crawler.adapters.cathay import TRAINING_IDS, CathayIMatch, dictionary, programme_pages
from job_crawler.adapters.cathay_data import (
    CAMPUS,
    CHANNEL,
    CHANNEL_PAGES,
    DETAIL_API,
    ENTRY,
    FILTERS,
    INFO,
    JAVA,
    LIST_API,
    MA,
    MA_PAGES,
    NAV,
    campus_basis,
    campus_rows,
    catalog,
    detail,
    gateway,
    internship,
    job_fields,
    job_id,
    joint_deadline,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session

FIX = Path(__file__).parent / "fixtures/cathay/public.json"


def fixture():
    return json.loads(FIX.read_text())


def wrapped(body):
    return {"MWHEADER": {"RETURNCODE": "0000"}, "TRANRS": body}


def html_catalog(count):
    return (
        f"<main>共計 {count} 筆資料</main><ul>"
        + "".join(f'<li><a href="{u}">{t}</a></li>' for u, t in NAV.items())
        + "</ul>"
    )


def script_sample(data):
    groups = {}
    for row in data["campus_sample"]:
        groups.setdefault(row["category"], []).append(
            {k: v for k, v in row.items() if k not in {"category", "id"}}
        )
    return "var jobs = " + json.dumps(groups, ensure_ascii=False, indent=2) + ";"


class Replay:
    def __init__(self, output, fault=""):
        self.data = fixture()
        self.output = output
        self.last_evidence = "list"
        self.calls = []
        self.fault = fault
        self.page = self
        self.url = ENTRY

    async def open(self, url, *, ready_endpoints=()):
        self.url = url
        self.last_evidence = url

    async def content(self):
        if self.url == ENTRY:
            return html_catalog(len(self.data["main"]))
        if self.url == CAMPUS:
            return '<script src="js/cathay2026hr.js"></script>'
        if self.url == JAVA:
            return "This site is currently suspended" if self.fault != "training" else "新正式職位"
        names = MA_PAGES if self.url == MA else CHANNEL_PAGES
        return "".join(f'<a href="{n}">職位</a>' for n in names)

    async def request_html(self, url, *, validate_html=True):
        self.last_evidence = url
        if url.endswith(".js"):
            return script_sample(self.data)
        if url.endswith("qna.html"):
            return "<main>申請資格</main>"
        return f'<a href="{INFO}I00024953">應徵</a>'

    async def observed_path(self, path):
        if path == LIST_API:
            return {
                "body": json.dumps(wrapped({"JOB_LIST": self.data["main"]})),
                "post_data": json.dumps({"TRANRQ": FILTERS}),
            }
        assert path == "/api/Sys/GetTranslation"
        return {
            "body": json.dumps(
                wrapped(
                    {
                        "i18nItems": [
                            {"key": k, "value": v} for k, v in self.data["dictionary"].items()
                        ]
                    }
                )
            )
        }

    async def request(self, url, *, payload, headers, detail):
        assert url == DETAIL_API and headers == {"Accept-Language": "zh_TW"} and detail
        key = payload["TRANRQ"]["APPL_FORM_NO"]
        self.calls.append(key)
        if self.fault == "request" and key == "I00024856":
            raise TimeoutError("detail unavailable")
        body = copy.deepcopy(self.data["details"][key])
        if self.fault == "identity" and key == "I00024856":
            body["APPL_FORM_NO"] = "I00000000"
        if self.fault == "unknown_link" and key == "I00020573":
            body["JOB_DESCRIPTION"] += '<a href="https://example.test/jobs.pdf">招聘附件</a>'
        self.last_evidence = key + ".json"
        return wrapped(body)


class Adapter(CathayIMatch):
    async def campaigns(self):
        replay = cast(Replay, self.session)
        ids = {r["id"] for r in replay.data["campus_sample"]}
        self.refs("campus-test", ids, ["campus"])
        return ids | TRAINING_IDS, ids, {key: ["campus"] for key in ids}


def make(tmp_path, now, fault=""):
    replay = Replay(tmp_path, fault)
    source = Source(source_id="COM0124", company_id="COM0124", company="国泰金控", url=ENTRY)
    return Adapter(source, cast(Session, replay), now), replay


async def test_graph_expands_gateway_deduplicates_closed_and_interns(tmp_path, now):
    adapter, replay = make(tmp_path, now)
    result = await adapter.collect()
    assert not result.coverage_issues(), result.issues
    keys = {j.source_key for j in result.jobs}
    assert len(keys) == len(result.jobs)
    assert {"I00024856", "I00001282", "I00005182"} <= keys
    assert not {"I00020573", "I00012494", "I00026753", "I00026938", "I00024953"} & keys
    assert len(replay.calls) == len(set(replay.calls))
    master = next(s for s in result.scopes if s.name == "cathay-unique-details")
    assert master.skipped_closed >= 3 and master.skipped_expired == 1
    assert master.skipped_out_of_scope >= 2
    assert all(not j.published for j in result.jobs)
    member = next(j for j in result.jobs if j.source_key == "I00005182")
    assert "官方校招" in member.field_sources["work_type"]


@pytest.mark.parametrize("fault", ["request", "identity", "unknown_link"])
async def test_partial_detail_or_link_retains_other_jobs(tmp_path, now, fault):
    adapter, _ = make(tmp_path, now, fault)
    result = await adapter.collect()
    assert result.coverage_issues() and result.jobs
    assert any(j.source_key == "I00001282" for j in result.jobs)


async def test_all_campaign_branches_and_training_guard(tmp_path, now):
    adapter, replay = make(tmp_path, now)
    extra, campus, provenance = await CathayIMatch.campaigns(adapter)
    assert TRAINING_IDS <= extra and len(campus) == 5
    assert set(provenance) == campus
    assert not adapter.result.coverage_issues()
    replay.fault = "training"
    await CathayIMatch.campaigns(adapter)
    assert adapter.result.coverage_issues()


@pytest.mark.parametrize("fault", ["count", "filter", "duplicate", "page_field", "nav"])
def test_catalog_rejects_incomplete_or_changed_scope(fault):
    d = fixture()
    rows = d["main"]
    data = wrapped({"JOB_LIST": rows})
    request = {"TRANRQ": dict(FILTERS)}
    html = html_catalog(len(rows))
    if fault == "count":
        html = html_catalog(len(rows) + 1)
    elif fault == "filter":
        request["TRANRQ"]["KEYWORD"] = "工程師"
    elif fault == "duplicate":
        rows.append(rows[0])
        html = html_catalog(len(rows))
    elif fault == "page_field":
        data["TRANRS"]["nextPage"] = 2
    else:
        html = html.replace("國泰校園徵才", "新專案")
    with pytest.raises(CrawlError):
        catalog(data, request, html)


def test_complete_array_may_exceed_visible_page_and_double_i():
    d = fixture()
    d["main"][0]["APPL_FORM_NO"] = "II00002621"
    assert (
        len(
            catalog(
                wrapped({"JOB_LIST": d["main"]}), {"TRANRQ": FILTERS}, html_catalog(len(d["main"]))
            )
        )
        > 10
    )
    assert job_id(INFO + "II00002621") == "II00002621"
    assert not job_id("https://other.test/iMatch/job/info/I00001282")


def test_campus_literal_parser_and_rejects_executable_or_duplicate():
    d = fixture()
    script = script_sample(d)
    assert len(campus_rows(script)) == 5
    for invalid in [
        script.replace('"url":', '"url":evil(),"url":', 1),
        script.replace('"MT":', '"NEW":', 1),
        script.replace(d["campus_sample"][1]["url"], d["campus_sample"][0]["url"]),
    ]:
        with pytest.raises((CrawlError, json.JSONDecodeError)):
            campus_rows(invalid)


@pytest.mark.parametrize("key", ["I00026753", "I00026938", "I00021731"])
def test_internship_overrides_fulltime_or_graduate_title(key):
    assert internship(fixture()["details"][key])


def test_real_job_with_zone_title_and_explicit_campus_is_retained():
    body = fixture()["details"]["I00024856"]
    assert "專區" in body["JOB_TITLE"] and not gateway(body)
    assert campus_basis(body) and not internship(body)


def test_graduate_role_and_negative_or_generic_experience():
    body = fixture()["details"]["I00005182"]
    assert not campus_basis(body)
    body["ACCEPT_ROLE_DESC_LIST"] = ["COMMON_UI_JOB_ACCEPT_ROLE_2"]
    assert campus_basis(body)
    body["ACCEPT_ROLE_DESC_LIST"] = None
    body["OTHER_CONDITION"] = "不接受應屆畢業生"
    with pytest.raises(CrawlError):
        campus_basis(body)


def test_closed_is_not_overridden_by_can_submit():
    body = fixture()["details"]["I00024953"]
    parsed = detail(wrapped(body), "I00024953", None)
    assert parsed["IS_OPEN"] == "N" and parsed["CAN_SUBMIT"] == "Y"


def test_joint_deadline_is_last_application_not_interview_or_notification():
    body = fixture()["details"]["I00012494"]
    assert joint_deadline(body).isoformat() == "2026-09-25T00:00:00+08:00"
    for value in ["面試2026/9/30", body["OTHER_CONDITION"] + "延期辦理"]:
        body["OTHER_CONDITION"] = value
        with pytest.raises(CrawlError):
            joint_deadline(body)


async def test_joint_active_batch_remains_partial(tmp_path, now):
    adapter, _ = make(tmp_path, now)
    adapter.as_of = datetime(2026, 8, 1, tzinfo=now.tzinfo)
    result = await adapter.collect()
    assert result.jobs and result.coverage_issues()
    assert any("联合招募仍开放" in x.message for x in result.issues)


def test_detail_fields_unknown_enums_and_dates_not_invented():
    d = fixture()
    body = d["details"]["I00024856"]
    fields = job_fields(body, d["dictionary"])
    assert not fields["published"] and not fields["deadline"] and not fields["education"]
    assert fields["unit"] == "產險" and "Windows Server" in fields["requirements"]
    body["OTHER_CONDITION"] += "\n履歷收件截至另行公告"
    assert job_fields(body, d["dictionary"])["deadline"] == "履歷收件截至另行公告"
    body["JOB_TYPE_DESC"] = "UNKNOWN"
    with pytest.raises(CrawlError):
        job_fields(body, d["dictionary"])


def test_new_programme_page_cannot_be_ignored():
    html = "".join(f'<a href="{name}">職位</a>' for name in CHANNEL_PAGES)
    assert len(programme_pages(html, CHANNEL, CHANNEL_PAGES)) == 7
    with pytest.raises(CrawlError):
        programme_pages(html + '<a href="new.html">新職缺</a>', CHANNEL, CHANNEL_PAGES)


def test_dictionary_does_not_silently_change_graduate_semantics():
    d = fixture()["dictionary"]
    d["COMMON_UI_JOB_ACCEPT_ROLE_2"] = "社會人士"
    with pytest.raises(CrawlError):
        dictionary(wrapped({"i18nItems": [{"key": k, "value": v} for k, v in d.items()]}))


async def test_shortlinks_and_cycles_do_not_duplicate_jobs(tmp_path, now):
    adapter, replay = make(tmp_path, now)
    replay.data["details"]["I00020573"]["JOB_DESCRIPTION"] += (
        f'<a href="{INFO}I00020573">目录回链</a>'
        '<a href="https://reurl.cc/test">应届岗位</a>'
        '<a href="https://pse.is/article">员工访谈</a>'
    )
    seen = []

    async def resolve(url):
        seen.append(url)
        return INFO + "I00001282" if "reurl" in url else "https://vocus.cc/article/1234"

    adapter.resolve = resolve
    result = await adapter.collect()
    assert not result.coverage_issues(), result.issues
    assert len(seen) == 2 and len(replay.calls) == len(set(replay.calls))
    assert len([j for j in result.jobs if j.source_key == "I00001282"]) == 1
    scope = next(s for s in result.scopes if s.name == "cathay-links-I00020573")
    assert scope.skipped_out_of_scope == 1


async def test_shortlink_failure_is_not_zero_or_full_coverage(tmp_path, now):
    adapter, replay = make(tmp_path, now)
    replay.data["details"]["I00020573"]["JOB_DESCRIPTION"] += (
        '<a href="https://reurl.cc/test">岗位</a>'
    )

    async def denied(url):
        raise CrawlError("access_denied", "shortener unavailable")

    adapter.resolve = denied
    result = await adapter.collect()
    assert result.coverage_issues() and result.jobs
    assert any(i.code == "access_denied" for i in result.issues)


async def test_daily_reuse_still_fetches_status_and_invalidates_changed_details(
    tmp_path, now, monkeypatch
):
    from datetime import timedelta

    from job_crawler.config import IncrementalConfig
    from job_crawler.incremental import IncrementalSource
    from job_crawler.storage import Store

    monkeypatch.setattr("job_crawler.incremental.evidence_exists", lambda path: True)
    store = Store(tmp_path / "state.sqlite")
    try:
        adapter, replay = make(tmp_path, now)
        ctx = IncrementalSource(store, "cathay", "all", now, now, IncrementalConfig())
        adapter.incremental = ctx
        baseline = await adapter.collect()
        assert not baseline.coverage_issues()
        ctx.finish(baseline)
        later = now + timedelta(hours=1)
        daily, current = make(tmp_path, later)
        current.data["details"]["I00024856"]["IS_OPEN"] = "N"
        current.data["details"]["I00001282"]["OTHER_CONDITION"] += "\n新增技能条件"
        daily.incremental = IncrementalSource(
            store, "cathay", "day", later, later, IncrementalConfig()
        )
        result = await daily.collect()
        assert not result.coverage_issues()
        assert "I00024856" in current.calls and not any(
            j.source_key == "I00024856" for j in result.jobs
        )
        changed = next(j for j in result.jobs if j.source_key == "I00001282")
        assert changed.detail_mode == "fresh" and "新增技能条件" in changed.requirements
        assert any(j.detail_mode == "cached" for j in result.jobs)
        assert len(current.calls) == len(replay.calls)
        daily.incremental.finish(result)
        saved = store.load_history("cathay")
        failed, _ = make(tmp_path, later, "request")
        failed.incremental = IncrementalSource(
            store, "cathay", "day", later, later, IncrementalConfig()
        )
        partial = await failed.collect()
        failed.incremental.finish(partial)
        assert partial.coverage_issues() and store.load_history("cathay") == saved
    finally:
        store.close()
