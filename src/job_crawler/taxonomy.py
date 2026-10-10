"""Read a restricted JS data literal without executing JavaScript."""

import ast
import hashlib
import json
import re
from pathlib import Path

from pydantic import Field

from job_crawler.models import Model


class Group(Model):
    name: str = Field(min_length=1)
    positions: list[str]


class Category(Model):
    name: str = Field(min_length=1)
    groups: list[Group] = Field(min_length=1)


class Taxonomy(Model):
    source: str
    sha256: str
    categories: list[Category] = Field(min_length=1)

    def paths(self) -> dict[str, list[str]]:
        result = {c.name: [g.name for g in c.groups] for c in self.categories}
        if len(result) != len(self.categories) or any(
            len(groups) != len(set(groups)) for groups in result.values()
        ):
            raise ValueError("分类名称重复")
        return result


def parse_javascript(text: str) -> Taxonomy:
    match = re.fullmatch(
        r"\s*(?:/\*.*?\*/\s*)?export\s+const\s+JOB_POSITION_CATEGORIES\s*=\s*(\[.*\])\s*;?\s*",
        text,
        re.DOTALL,
    )
    if not match:
        raise ValueError("仅支持 JOB_POSITION_CATEGORIES 数据常量")
    # Tokenize quoted strings first, so their contents never become code or keys.
    tokens = re.findall(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|\w+|[^\s]", match[1])
    literal = " ".join(repr(t) if t in {"name", "groups", "positions"} else t for t in tokens)
    try:
        data = ast.literal_eval(literal)
    except (ValueError, SyntaxError) as exc:
        raise ValueError("分类脚本包含不支持的表达式") from exc
    result = Taxonomy(
        source="job-position.js",
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        categories=data,
    )
    result.paths()
    return result


def load_taxonomy(path: Path) -> Taxonomy:
    return Taxonomy.model_validate(json.loads(path.read_text(encoding="utf-8")))
