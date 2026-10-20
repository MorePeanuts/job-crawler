"""The joint GIIHG catalog must not attribute subsidiary jobs to headquarters."""

from job_crawler.adapters.zhaopin import Giihg2027


def test_only_headquarters_is_in_scope() -> None:
    adapter = Giihg2027.__new__(Giihg2027)
    assert adapter.in_scope({"campusOrgName": "广州工业投资控股集团有限公司"})
    for subsidiary in (
        "广州广日股份有限公司",
        "万力轮胎股份有限公司",
        "孚能科技（赣州）股份有限公司",
    ):
        assert not adapter.in_scope({"campusOrgName": subsidiary})
    assert not adapter.in_scope({"campusOrgName": None})
