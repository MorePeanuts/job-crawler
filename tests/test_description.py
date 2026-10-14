"""SPEC-034: title boundaries, actual incident shapes and prose preservation."""

from collections.abc import Callable

import pytest

from job_crawler.adapters.bilibili import sections as bilibili_sections
from job_crawler.adapters.campaign51 import split_jobinfo
from job_crawler.adapters.hotjob import detail_body
from job_crawler.adapters.moka import sections as moka_sections
from job_crawler.adapters.zhaopin import split_detail
from job_crawler.config import MappingConfig
from job_crawler.description import clean_field_headings, split_sections, strip_heading
from job_crawler.exporter import normalize
from job_crawler.models import Job


@pytest.mark.parametrize(
    "body",
    [
        "【岗位职责】\n开发软件\n【任职要求】\n本科及以上",
        "【岗位职责】开发软件【任职资格】本科及以上",
        "岗位职责：开发软件\n任职要求：本科及以上",
        "一、岗位职责\n开发软件\n二、岗位要求：\n本科及以上",
        "[岗位职责]\n开发软件\n[岗位要求]\n本科及以上",
        "（岗位职责）开发软件（任职条件）本科及以上",
        "岗位职责；\n开发软件\n【\n任职资格：\n】本科及以上",
        "\ufeff岗位职责\u200b\n开发软件\n任职要求：本科及以上",
        "任职要求：本科及以上\n岗位职责：开发软件",
        "【工作职责Responsibilities】开发软件【任职要求Requirements】本科及以上",
        "岗位职责：开发软件\n【任职要求\n本科及以上",
        "岗位职责：开发软件\n任职要求如下：本科及以上",
    ],
)
def test_heading_variants(body: str) -> None:
    assert split_sections(body) == ("开发软件", "本科及以上")


@pytest.mark.parametrize(
    "splitter", [split_detail, split_jobinfo, moka_sections, bilibili_sections]
)
def test_shared_adapters_consume_bracketed_headings(
    splitter: Callable[[str], tuple[str, str]],
) -> None:
    assert splitter("【岗位职责】\n开发软件\n【任职要求】\n本科及以上") == (
        "开发软件",
        "本科及以上",
    )


def test_sungrow_brackets_across_html_paragraphs() -> None:
    assert moka_sections(
        "<p>【岗位职责】</p><p>开发软件【</p><p><br></p><p>任职资格：</p><p>】学历背景：硕士</p>"
    ) == ("开发软件", "学历背景：硕士")


def test_html_inline_tags_and_standalone_colon() -> None:
    assert moka_sections(
        "<p><strong>岗位职责</strong>：</p><p>开发软件</p>"
        "<p>【<strong>任职资格</strong>】</p><p>本科及以上</p>"
    ) == ("开发软件", "本科及以上")


def test_prose_and_meaningful_brackets_are_preserved() -> None:
    body = "根据岗位职责制定方案，明确任职要求。\n使用【Python】和[SQL]。\n任职要求说明需要讨论。"
    assert split_sections(body) == (body, "")
    assert strip_heading(body, "duties") == body
    assert split_sections("无标题正文", unheaded_duties=False) == ("", "")
    assert split_sections("职责【任职要求未明确】说明") == ("职责【任职要求未明确】说明", "")
    assert split_sections("根据【岗位职责】制定方案，符合【任职要求】。") == (
        "根据【岗位职责】制定方案，符合【任职要求】。",
        "",
    )


def test_prefix_repeated_sections_and_empty_sections() -> None:
    assert split_sections("简介\n岗位职责：\n任职要求：硕士\n岗位职责：开发") == (
        "简介\n开发",
        "硕士",
    )
    assert split_sections("【岗位职责】\n【任职要求】") == ("", "")
    assert split_sections("项目简介。岗位要求如下：本科") == ("项目简介。", "本科")
    assert split_sections("专业：计算机\n岗位职责：开发", include_preamble=False) == ("开发", "")


def test_structured_fields_do_not_move_content_or_delete_internal_headers() -> None:
    assert strip_heading("【岗位职责】\n开发【系统】", "duties") == "开发【系统】"
    assert strip_heading("岗位要求：本科", "duties") == "岗位要求：本科"
    assert strip_heading("开发\n任职要求：本科", "duties") == "开发\n任职要求：本科"
    assert detail_body(
        {"workContent": "【岗位职责】开发", "serviceCondition": "任职要求：本科"}
    ) == ("开发", "本科")
    assert detail_body({"workContent": "【岗位职责】开发【任职要求】本科"}) == ("开发", "本科")


def test_normalize_removes_structured_titles_without_mutating_snapshot(job: Job) -> None:
    job.duties = "岗位职责：\n开发【系统】"
    job.requirements = "任职要求\n本科"
    clean = normalize(job, MappingConfig())
    assert clean.duties == "开发【系统】"
    assert clean.requirements == "本科"
    assert job.duties.startswith("岗位职责")
    assert normalize(clean, MappingConfig()) == clean


def test_structured_field_headers_after_preamble_and_wrong_source_label() -> None:
    assert clean_field_headings("团队简介\n【岗位职责】\n开发") == "团队简介\n开发"
    assert clean_field_headings("【岗位职责】\n必要条件：本科") == "必要条件：本科"
    assert clean_field_headings("请阅读【岗位职责】后申请") == "请阅读【岗位职责】后申请"
