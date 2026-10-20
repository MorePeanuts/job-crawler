"""Checks for the category-to-role expansion of Baosteel's campus notice."""

import pytest

from job_crawler.adapters.baowu_baosteel import roster
from job_crawler.transport import CrawlError


def notice(*, extra: str = "", company: str = "宝山钢铁股份有限公司") -> str:
    return f"""
    <h1>中国宝武2027届“国宝生”计划之宝钢股份“英才”招聘计划</h1>
    <p>{company}是中国宝武钢铁集团有限公司的旗舰子公司。</p>
    <p>2027年应届本科生、硕士研究生、博士研究生</p>
    <div><p>二、招聘岗位</p>
      <p>数据AI工程师</p><p>人工智能工程师、大模型工程师、大数据工程师、平台构建工程师</p>
      <p>工作地点：上海、武汉</p><p>专业：计算机、软件工程</p>
      <p>工艺工程师</p><p>冶金工艺工程师、材料工艺工程师、煤化工工程师、矿物加工工程师、能源动力工程师</p>
      <p>工作地点：上海、武汉</p><p>专业：冶金、材料工程</p>
      <p>设备工程师</p><p>自动化工程师、电气工程师、机械工程师、仪器仪表工程师</p>
      <p>工作地点：上海、武汉</p><p>专业：自动化、电气工程</p>
      <p>市场营销/海外贸易培训生</p>
      <p>工作地点：上海、北京</p><p>专业：国际贸易、市场营销</p>
      {extra}<p>三、薪酬福利</p></div>
    """


def test_expands_all_four_categories_without_assigning_category_cities() -> None:
    rows = roster(notice())
    assert len(rows) == 14
    assert rows[0]["title"] == "人工智能工程师"
    assert rows[0]["location_range"] == "上海、武汉"
    assert rows[-1]["title"] == "市场营销/海外贸易培训生"
    assert rows[-1]["majors"] == "国际贸易、市场营销"


def test_new_role_or_changed_parent_cannot_silently_pass() -> None:
    with pytest.raises(CrawlError):
        roster(notice(extra="<p>新增岗位</p>"))
    with pytest.raises(CrawlError):
        roster(notice(company="其他公司"))
