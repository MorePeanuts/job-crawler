"""AAC Optics' fully rendered campus and social job cards."""

from typing import Protocol, cast

from bs4 import BeautifulSoup

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.description import split_sections
from job_crawler.models import Scope


class Page(Protocol):
    async def content(self) -> str: ...


class PageSession(Protocol):
    page: Page


class AacOpticsCampus(Adapter):
    name = "aacoptics-campus"
    host = "www.aacoptics.com"
    path = "/?page_id=1517"
    scope_description = "辰瑞光学官网职位卡中明确标注校园招聘的全目录；排除社招和未标性质"

    async def harvest(self) -> None:
        html = await cast(PageSession, self.session).page.content()
        soup = BeautifulSoup(html, "html.parser")
        check(soup.select_one("#aol_career_form") is not None, "辰瑞官网招聘插件未加载")
        check(
            not soup.select(".aol-pagination, .page-numbers, .aol-next, .aol-prev"),
            "辰瑞职位卡出现未适配的分页控件",
        )
        cards = soup.select(".aol-ad-inner-wrapper")
        check(bool(cards), "辰瑞官网未显示职位卡")
        scope = Scope(name="aacoptics-rendered-careers", expected=len(cards))
        self.result.scopes.append(scope)
        seen: set[str] = set()
        for card in cards:
            class_attr = card.get("class")
            check(isinstance(class_attr, list), "辰瑞职位卡缺少 CSS 类")
            assert isinstance(class_attr, list)
            classes = [str(part) for part in class_attr if str(part).startswith("aol_ad_")]
            check(len(classes) == 1, "辰瑞职位卡缺少稳定 ID")
            key = classes[0].removeprefix("aol_ad_")
            check(key.isdigit() and key not in seen, "辰瑞职位卡 ID 重复或无效")
            seen.add(key)
            scope.listed += 1
            scope.unique += 1
            footer = card.select_one(".panel-footer")
            check(footer is not None, "辰瑞职位卡缺少招聘渠道")
            assert footer is not None
            channels = [
                item.get_text(" ", strip=True)
                for item in footer.select(".aol-tax-wrapper")
                if "招聘渠道" in item.get_text(" ", strip=True)
            ]
            check(len(channels) <= 1, "辰瑞职位卡出现多个招聘渠道")
            if not channels or "校园招聘" not in channels[0]:
                scope.skipped_out_of_scope += 1
                continue
            check("社会招聘" not in channels[0], "辰瑞职位卡招聘渠道混合")
            title_node = card.select_one(".panel-heading")
            description_node = card.select_one(".panel-body p")
            link = card.select_one(".panel-body a[href]")
            check(
                title_node is not None and description_node is not None and link is not None,
                "辰瑞校园职位缺少标题、正文或详情链接",
            )
            assert title_node is not None and description_node is not None and link is not None
            title = text(title_node.get_text(" ", strip=True))
            duties, requirements = split_sections(description_node.get_text("\n", strip=True))
            check(bool(title and duties and requirements), "辰瑞校园职位正文不完整")
            url = str(link["href"])
            check(url.startswith(f"https://{self.host}/?aol_career="), "辰瑞职位详情链接改变")
            categories = [
                item.get_text(" ", strip=True).removeprefix("分类:").strip(" ,，")
                for item in footer.select(".aol-tax-wrapper")
                if "分类" in item.get_text(" ", strip=True)
            ]
            cities = [
                item.get_text(" ", strip=True).removeprefix("城市:").strip(" ,，")
                for item in footer.select(".aol-tax-wrapper")
                if "城市" in item.get_text(" ", strip=True)
            ]
            self.result.jobs.append(
                self.job(
                    key,
                    title=title,
                    source_url=url,
                    category_raw=categories[0] if categories else "",
                    location=cities[0] if cities else "",
                    duties=duties,
                    requirements=requirements,
                    field_sources={
                        "duties": "aol-ad-inner-wrapper.panel-body:工作职责",
                        "requirements": "aol-ad-inner-wrapper.panel-body:任职资格",
                        "published": "source_missing",
                        "deadline": "source_missing",
                    },
                )
            )
            scope.details += 1
        scope.evidence.append(self.session.last_evidence)
        scope.terminal = True
