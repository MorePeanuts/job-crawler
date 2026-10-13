from job_crawler.adapters.byd import requirement_education


def test_byd_education_uses_minimum_eligible_level() -> None:
    assert requirement_education("学历要求：本科及以上") == "本科"
    assert requirement_education("学历：硕士研究生") == "硕士"
    assert requirement_education("学历要求：博士") == "博士"


def test_byd_education_does_not_guess_missing_requirement() -> None:
    assert requirement_education("专业不限，具备良好的沟通能力") == ""
