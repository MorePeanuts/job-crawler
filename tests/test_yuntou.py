"""Closed announcements must not hide a changed or still-open recruitment scope."""

import hashlib
import json
from datetime import datetime
from typing import cast

import pytest

from job_crawler.adapters.yuntou import (
    ENTRY,
    IMAGE_NOTICES,
    ROOT,
    TZ,
    Notice,
    YuntouNotices,
    article,
    deadline,
    excluded,
    listing,
)
from job_crawler.models import Source
from job_crawler.transport import CrawlError, Session


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("报名时间：2026年3月30日至2026年4月9日24:00。", "2026-04-10T00:00:00+08:00"),
        ("报名时间。自2024年8月5日至2024年8月14日24:00止。", "2024-08-15T00:00:00+08:00"),
        (
            "应聘者请于2021年3月18日至3月22日17:00前如实提交个人报名信息。",
            "2021-03-22T17:00:00+08:00",
        ),
        ("扫描材料于2019年8月31日前发送至邮箱。", "2019-09-01T00:00:00+08:00"),
        ("报名时间自招聘公告发布之日起至2018年5月3日24:00止。", "2018-05-04T00:00:00+08:00"),
        ("报名时间：即日起至2018年3月4日，每天上午9:00-12:00。", "2018-03-05T00:00:00+08:00"),
        ("报名时间：2017年6月26日9：00-6月30日17︰00。", "2017-06-30T17:00:00+08:00"),
        ("报名时间：2017年5月15日-5月26日，每天上午9：00-12：00。", "2017-05-27T00:00:00+08:00"),
        ("报名时间：2017年2月4日—2月10日，每天上午9：00-12：00。", "2017-02-11T00:00:00+08:00"),
    ],
)
def test_application_deadlines(text, expected):
    value, evidence = deadline("年龄1990年4月1日后出生。" + text + "须于2027年7月31日前毕业。")
    assert value.isoformat() == expected and evidence


@pytest.mark.parametrize(
    "text",
    [
        "须于2027年7月31日前毕业。",
        "报名时间：即日起至招满。",
        "报名时间：3月1日至3月10日。",
        "报名时间：2026年3月30日。",
        "报名时间：2026年3月30日至2026年3月29日。",
        "报名时间：2026年3月30日至2026年4月9日24:30。",
        "报名时间：2026年3月30日至2026年4月31日。",
        "报名时间：2026年3月30日至2026年4月9日。报名时间：2026年5月1日至2026年5月9日。",
    ],
)
def test_no_guessed_deadlines(text):
    with pytest.raises((CrawlError, ValueError)):
        deadline(text)


@pytest.mark.parametrize(
    ("title", "skip"),
    [
        ("某集团校园招聘结果公示", True),
        ("某集团2019年拟补录人员名单公示", True),
        ("某集团2027年社会公开招聘公告", True),
        ("某集团见习人员招聘公告", True),
        ("某集团公开招聘公告", False),
        ("某集团招聘公告公示", False),
        ("某集团社会招聘延期公告", False),
    ],
)
def test_explicit_scope_only(title, skip):
    assert bool(excluded(title)) == skip


def row(index, title="社会招聘公告"):
    return f'<dd><div class="divleft"><span>01</span><em>2026-04</em></div><div class="divright"><a href="/news/rczp/{index:08x}-abcd.htm">{title}</a></div></dd>'


def page(index):
    rows = (
        "".join(row(i) for i in range(14)) + row(14, "校园招聘公告")
        if index == 1
        else row(15, "图片招聘公告")
    )
    tail = '<a href="/newslist/rczp/2/15.htm">尾页</a>' if index == 1 else "<a>尾页</a>"
    return f'<div>人才招聘</div>{rows}<div id="pageContainer"><a class="hover">{index}</a><a href="/newslist/rczp/1/15.htm">首页</a>{tail}<script>var max =2;</script></div>'


def detail(title="校园招聘公告", text="报名时间：2026年3月30日至2026年4月9日24:00。", image=""):
    return f'<div class="articleTitle">{title}</div><div class="articleTime">日期：2026-04-01</div><div class="articleBox">{text}{image}</div>'


@pytest.mark.parametrize(
    "fault", ["empty", "active", "tail", "count", "date", "external", "repeat"]
)
def test_page_failures(fault):
    html = page(1)
    if fault == "empty":
        html = "无数据"
    elif fault == "active":
        html = html.replace('class="hover">1', 'class="hover">2')
    elif fault == "tail":
        html = html.replace("max =2", "max =3")
    elif fault == "count":
        html = html.replace(row(0), "")
    elif fault == "date":
        html = html.replace("2026-04", "2026-99")
    elif fault == "external":
        html = html.replace("/news/rczp/00000000", "https://example.com/news/rczp/00000000")
    elif fault == "repeat":
        html = html.replace("00000001-abcd", "00000000-abcd")
    with pytest.raises((CrawlError, ValueError)):
        listing(html, 1)


def test_inline_split_dates_and_article_identity():
    notice = Notice(ROOT + "/news/rczp/a.htm", "校园招聘公告", "2026-04-01")
    html = detail(text="报名时间：202<span>6</span>年3月30日至2026年4月9日24:00。")
    text, _, _ = article(html, notice)
    assert deadline(text)[0].day == 10
    with pytest.raises(CrawlError):
        article(html.replace("校园招聘公告", "别家公告"), notice)
    with pytest.raises(CrawlError):
        article(html.replace("日期：2026-04-01", "日期：2026-04-02"), notice)


class Response:
    status = 200

    def __init__(self, content):
        self.content = content

    async def body(self):
        return self.content


class Replay:
    last_evidence = "entry"

    def __init__(self, output, fault=""):
        self.output = output
        self.fault = fault
        self.page = self
        self.request = self
        self.read = []
        self.images = []

    async def open(self, url, **kwargs):
        assert url == ENTRY

    async def content(self):
        return page(1)

    async def request_html(self, url):
        self.last_evidence = url
        self.read.append(url)
        if "/newslist/" in url:
            html = page(2)
            if self.fault == "duplicate":
                html = html.replace("0000000f-abcd", "0000000e-abcd")
            if self.fault == "page_change":
                html = html.replace("max =2", "max =3").replace(
                    "<a>尾页</a>", '<a href="/newslist/rczp/3/15.htm">尾页</a>'
                )
            return html
        if "0000000e" in url:
            if self.fault == "failed_detail":
                raise TimeoutError("detail unavailable")
            html = detail()
            if self.fault == "future":
                html = html.replace("2026年4月9日", "2027年4月9日")
            if self.fault == "unverified_image":
                html = detail(image='<img src="/new.png">')
            if self.fault == "body_extension":
                html = detail(text="报名时间：2026年3月30日至2026年4月9日24:00。延长报名时间。")
            if self.fault == "unknown":
                html = detail(text="招满即止")
            return html
        html = detail("图片招聘公告", "", '<img src="/Uploads/NewsPhoto/test.png">')
        if self.fault == "extra_image":
            html = html.replace("</div>", '<img src="/extra.png"></div>')
        if self.fault == "changed_text":
            html = html.replace('class="articleBox">', 'class="articleBox">延期报名')
        return html

    def consume_request(self):
        pass

    async def get(self, url, **kwargs):
        self.images.append(url)
        return Response(b"changed" if self.fault == "changed_image" else b"verified-image")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "",
        "duplicate",
        "page_change",
        "failed_detail",
        "future",
        "unknown",
        "extra_image",
        "unverified_image",
        "body_extension",
        "changed_text",
        "changed_image",
    ],
)
async def test_complete_and_partial(tmp_path, monkeypatch, fault):
    notice = Notice(ROOT + "/news/rczp/0000000f-abcd.htm", "图片招聘公告", "2026-04-01")
    html = detail("图片招聘公告", "", '<img src="/Uploads/NewsPhoto/test.png">')
    _, images, fingerprint = article(html, notice)
    monkeypatch.setitem(
        IMAGE_NOTICES,
        "0000000f-abcd.htm",
        {
            "deadline": "2026-04-10T00:00:00+08:00",
            "expression": "verified test notice",
            "fingerprint": fingerprint,
            "images": [(images[0], hashlib.sha256(b"verified-image").hexdigest())],
        },
    )
    replay = Replay(tmp_path, fault)
    source = Source(
        source_id="COM0138", company_id="COM0138", company="云南省投资控股集团有限公司", url=ENTRY
    )
    result = await YuntouNotices(
        source, cast(Session, replay), datetime(2026, 10, 18, tzinfo=TZ)
    ).collect()
    assert not result.jobs
    if not fault:
        assert not result.coverage_issues()
        assert result.scopes[0].expected == 16
        assert result.scopes[0].details == 2
        assert result.scopes[0].skipped_out_of_scope == 14
        assert len(result.scopes) == 3 and all(s.skipped_expired == 1 for s in result.scopes[1:])
        records = json.loads((tmp_path / "yuntou-notice-dispositions.json").read_text())
        assert len(records) == 16 and records[-1]["deadline_evidence"]
        assert len(replay.read) == 3 and len(replay.images) == 1
    else:
        assert result.issues and result.coverage_issues()
        if fault in {"failed_detail", "future", "unknown"}:
            assert result.scopes[-1].terminal and result.scopes[-1].skipped_expired == 1
        if fault == "future":
            assert result.issues[0].code == "unsupported_scope"
