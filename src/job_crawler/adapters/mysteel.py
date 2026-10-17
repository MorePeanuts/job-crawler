"""Mysteel's complete, eagerly rendered campus tabs."""

from typing import cast

from bs4 import BeautifulSoup, Tag

from job_crawler.adapters.base import Adapter, text
from job_crawler.adapters.platforms import check
from job_crawler.models import Scope
from job_crawler.transport import BrowserSession


def sections(card: Tag) -> tuple[str, str]:
    paragraphs = [p.get_text(strip=True) for p in card.select("dd p")]
    check(
        paragraphs.count("岗位职责：") == paragraphs.count("任职要求：") == 1,
        "钢联岗位职责/要求结构变化",
    )
    boundary = paragraphs.index("任职要求：")
    check(
        paragraphs[0] == "岗位职责：" and 1 < boundary < len(paragraphs) - 1, "钢联岗位正文不完整"
    )
    return "\n".join(paragraphs[1:boundary]), "\n".join(paragraphs[boundary + 1 :])


class MysteelCampus(Adapter):
    name = "mysteel-campus"
    host = "about.mysteel.com"
    path = "/career/?id=recruit"
    scope_description = (
        "上海钢联官网校园招聘业务/职能两个完整静态栏目；实习排除，公众号其他机会未覆盖"
    )

    async def harvest(self) -> None:
        session = cast(BrowserSession, self.session)
        document = BeautifulSoup(await session.page.content(), "html.parser")
        check(
            "上海钢联电子商务股份有限公司 版权所有" in document.get_text(" ", strip=True),
            "钢联官网主体变化",
        )
        check(
            [(n.get("id"), n.get_text(strip=True)) for n in document.select("#main-nav > li")]
            == [
                ("position", "职业发展"),
                ("team", "团队风采"),
                ("bidding", "社会招聘"),
                ("recruit", "校园招聘"),
            ],
            "钢联主导航变化",
        )
        tabs = [(n.get("id"), n.get_text(strip=True)) for n in document.select("#recruit-box li")]
        check(
            tabs
            == [
                ("business", "业务板块"),
                ("recruit-role", "职能板块"),
                ("recruit-application", "应聘须知"),
            ],
            "钢联校园栏目变化",
        )
        blocks = document.select("#recruit-content > .wanted__item")
        check(len(blocks) == len(tabs), "钢联校园隐藏栏目缺失")
        check(
            not document.select(
                "#recruit-content a[href],#recruit-content iframe,.pagination,.pager"
            ),
            "钢联出现未验证详情/附件/分页",
        )
        check(
            [text(n) for n in blocks[2].select("dt")] == ["福利待遇", "投递方式"],
            "钢联应聘须知变化或新增岗位",
        )
        application = blocks[2].get_text("\n", strip=True)
        addresses = [
            p.get_text(strip=True).removeprefix("工作地点：")
            for p in blocks[2].select("p")
            if p.get_text(strip=True).startswith("工作地点：")
        ]
        check(len(addresses) == 1 and bool(addresses[0]), "钢联工作地点缺失")
        for (tab_id, label), block in zip(tabs[:2], blocks[:2], strict=True):
            scope = Scope(name=f"mysteel:{tab_id}", unit=str(label))
            scope.evidence.append(session.last_evidence)
            self.result.scopes.append(scope)
            try:
                cards = block.select(":scope > dl")
                check(bool(cards), "钢联校园栏目为空，未证明零目录")
                scope.expected = len(cards)
                scope.listed = len(cards)
                seen: set[str] = set()
                for card in cards:
                    title = text(card.select_one("dt"))
                    check(bool(title) and title not in seen, "钢联岗位标题为空或重复")
                    seen.add(title)
                    scope.unique += 1
                    check(not card.select("img,a[href],iframe"), "钢联岗位出现未验证附件")
                    duties, requirements = sections(card)
                    if "实习" in title:
                        scope.skipped_out_of_scope += 1
                        continue
                    key = f"{tab_id}:{title}"
                    listing = {"card": str(card), "application": application}
                    cached = self.before_detail(f"job:{key}", listing, scope)
                    if cached is not None:
                        self.result.jobs.extend(cached)
                        continue
                    job = self.job(
                        key,
                        title=title,
                        duties=duties,
                        requirements=requirements,
                        location=addresses[0],
                        source_url=f"https://{self.host}{self.path}",
                        field_sources={
                            "duties": "校园卡片岗位职责",
                            "requirements": "校园卡片任职要求",
                            "location": "应聘须知工作地点",
                            "published": "source_missing",
                            "deadline": "source_missing",
                            "education": "source_missing:保留要求待公共补全",
                        },
                    )
                    self.result.jobs.append(job)
                    self.remember(f"job:{key}", listing, [job])
                    scope.details += 1
                scope.terminal = True
            except Exception as exc:
                self.error(exc)
