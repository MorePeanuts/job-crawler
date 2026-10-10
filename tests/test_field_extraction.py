import pytest

from job_crawler.field_extraction import address_decision, education_decision, enrich_fields
from job_crawler.models import Job


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("大学本科", "本科"),
        ("硕士研究生", "硕士"),
        ("博士研究生", "博士"),
        ("大学本科,硕士研究生", "本科"),
        ("研究生", "硕士"),
        ("硕士研究生,博士研究生", "硕士"),
        ("大专,高职,大学本科", "大专"),
        ("大专,高职", "大专"),
        ("学历不限", "学历不限"),
    ],
)
def test_structured_education_has_priority(job: Job, raw: str, expected: str) -> None:
    job.education = raw
    job.requirements = "博士优先，本科毕业院校为重点大学。"
    assert education_decision(job).value == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2027届本科及以上学历毕业生，计算机专业优先。", "本科"),
        ("大学本科或以上学历。硕士优先。", "本科"),
        ("硕士研究生及以上学历，具备沟通能力。", "硕士"),
        ("具有博士学位。", "博士"),
        ("最低学历为大专。", "大专"),
        ("本科/硕士毕业生。", "本科"),
        ("2027届本科生/硕士生，计算机专业。", "本科"),
        ("本科、硕士、博士学历，计算机专业。", "本科"),
        ("硕士及以上学历（博士优先）。", "硕士"),
        ("本科及以上学历、计算机专业优先。", "本科"),
        ("本科及以上学历者优先。", ""),
        ("硕士及以上学历，本科理工科专业优先，硕士财务复合背景优先。", "硕士"),
        ("硕士及以上学历，本科财政学类税务相关专业，研究生期间侧重课题研究。", "硕士"),
        ("相关专业背景，硕士及以上学历。", "硕士"),
        ("本科及以上学历（大专相关专业也可考虑）。", ""),
        ("本科及以上（部分专业方向要求硕士及以上）。", ""),
        ("硕士及以上学历，特别优秀者可放宽至本科。", ""),
        ("本科阶段学习成绩优秀。", ""),
        ("本科毕业生年龄不超过26岁；博士研究生年龄不超过35岁。", ""),
        ("研究生学历应届毕业生。", "硕士"),
        ("计算机相关专业硕士或博士研究生。", "硕士"),
        ("博士研究生毕业，材料相关专业。", "博士"),
        ("2027届应届硕士 / 博士，计算机相关专业。", "硕士"),
        ("1. Bachelor’s degree or above in any field.", "本科"),
        ("1. PhD, Master's, or Bachelor's degree in Computer Science", "本科"),
        ("Education: Pursuing a Bachelor’s degree or higher", "本科"),
        ("Master's degree preferred", ""),
        ("硕士学历者优先，经验优秀者学历不限。", ""),
        ("本科及以上学历。硕士及以上学历。", ""),
    ],
)
def test_education_requires_unambiguous_eligibility(job: Job, text: str, expected: str) -> None:
    job.education = ""
    job.requirements = text
    result = education_decision(job)
    assert result.value == expected
    if expected:
        assert result.quote in text and result.quote
    enriched = enrich_fields(job)
    assert enriched.education == expected
    assert job.education == ""


def test_conservative_policy_and_provenance(job: Job) -> None:
    job.education = "大学本科,硕士研究生"
    assert education_decision(job, "explicit_only").value == job.education
    job.education = ""
    job.requirements = "本科/硕士毕业生"
    assert education_decision(job, "explicit_only").value == ""
    normalized = enrich_fields(job)
    assert normalized.field_sources["education"].endswith("quote:本科/硕士毕业生")
    assert enrich_fields(normalized) == normalized


def test_duties_only_when_explicitly_describing_applicants(job: Job) -> None:
    job.education = ""
    job.requirements = "有相关工作经验"
    job.duties = "负责本科毕业生的招聘和培训"
    assert education_decision(job).value == ""
    job.duties = "招聘对象：面向全日制大学本科及以上学历的应届毕业生"
    assert education_decision(job).value == "本科"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("工作地址：广东省深圳市南山区科技路88号A座。", "广东省深圳市南山区科技路88号A座"),
        ("办公地点：上海市浦东新区示例大厦。", "上海市浦东新区示例大厦"),
        ("工作地点：北京、上海、深圳。", ""),
        ("联系地址：深圳市示例路88号。", ""),
        ("公司总部地址：深圳市示例路88号。", ""),
        ("面试地址：深圳市示例路88号。", ""),
        ("工作地址：上海市示例路1号。办公地址：北京市示例路2号。", ""),
    ],
)
def test_workplace_address_not_inferred_from_city_or_contact(
    job: Job, text: str, expected: str
) -> None:
    job.address = ""
    job.requirements = text
    result = address_decision(job)
    assert result.value == expected
    if expected:
        assert result.quote in text
