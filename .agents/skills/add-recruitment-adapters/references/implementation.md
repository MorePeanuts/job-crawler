# 实现与验收参考

从仓库根目录查看下面路径；本文件用于定位已有契约，不是未验证网站的参数模板。

## 先形成本站 spec

按 `specs/` 当前编号创建规范，包含目标/非目标、企业和入口依据、纳入/排除范围、输入输出、失败行为与可测试验收条件。平台事实至少说明：

- 企业主体、集团单位/子公司边界、正式校招/实习/社招及博士等不同项目。
- 列表实际请求方式、已观察参数、过滤条件、页码/游标、源总数语义与末页依据。
- 详情 ID 和列表记录的关联；跨单位 ID 是否唯一；公告如何一对多展开；附件是否可解析。
- 发布时间/更新日期/截止时间各自字段含义，未知日期怎样保留。
- 正文、最低可报名学历、地址与地区字段；来源确实缺失时怎样报告。
- 登录/验证码、访问错误、数据变化与预算耗尽怎样保留 partial/blocked。

## 代码入口

| 工作 | 已有实现与依据 |
| --- | --- |
| 来源与绑定 | `models.py` 的 Source/Binding；`sources.py`；`sites/sources.csv`、`sites/bindings.toml` |
| 基类与覆盖 | `adapters/base.py` 的 Adapter；`models.py` 的 Scope/Collection；`adapters/__init__.py` 的 REGISTRY |
| 浏览器和证据 | `transport.py` 的 BrowserSession/Session；`docs/adapter-development.md` 的 ready_endpoints 约定 |
| 列表预筛选、详情缓存 | `incremental.py`、SPEC-009、`tests/test_incremental.py` |
| 日期/导入与模型 | `filtering.py`、`runner.py`、`delivery.py`；SPEC-007、009、010、011 |
| 正文章节拆分 | `description.py`；SPEC-034；不自行按任意“岗位要求”字串切分 |
| 汇总及归档 | `bundle.py`、`retention.py`、SPEC-047；配合本 skill 的 delivery.md |

表内 Python 路径均相对 `src/job_crawler/`，测试路径相对项目根目录。

相似平台优先参考以下实际实现及对应测试，不要照抄租户参数：

- 北森：`adapters/zhiye.py`、`sunwoda.py`；Category、PortalId、多博士目录和定制详情路径需逐站验证。
- Moka：`adapters/moka.py`；同租户/siteId、当前页面公开解码参数、列表/详情与法人部门映射需核对。
- Hotjob：`adapters/hotjob.py`；确认表单格式、recruitType、首次发布与更新字段，移动入口另作验证。
- 前程无忧：`adapters/campaign51.py`、`coapi51.py`、`wtmec.py`；活动页、静态数组和 COAPI 是不同契约。
- 智联：`adapters/zhaopin.py`；单位树、活动范围与身份关系。
- 自定义 JSON/内嵌正文/虚拟列表：`inline_catalogs.py`、`chinatower.py`、`anker.py`、`haier.py`；SPEC-043～046 和 `tests/test_batch6_contracts.py`。

详细平台陷阱以 [适配器规范](../../../../docs/adapter-development.md) 为准，不从一页渲染结果推断整家公司覆盖。

## 不可丢失的运行契约

每个目录/单位/批次建立 Scope。`expected`、`listed`、`unique` 的口径一致；按当前模型核对：

```text
details + reused_details + skipped_window + skipped_expired + skipped_closed == unique
```

`terminal` 必须来自已证明的末页、总数或穷尽游标。重复页、详情错配、附件未处理、总数持续变化等不能标为完整。岗位用源 ID 及必要单位/批次作唯一键；不按标题去重，不把公告数当岗位数。

详情前使用 `before_detail`，返回 None 才读取；读取并校验成功后 `remember`。跨页/并发时保存对应列表证据，不能用当前 session 中另一条详情的 last_evidence 代替。缺少发布时间的列表不能直接跳过；列表已有全文时不再请求详情。全量刷新和每日复用都要验证，不能只测缓存命中。

职责、要求、学历、地点、地址、日期分别有来源依据。接受多学历时按项目最低可报名策略；不把“不限”改成本科、不把城市猜成详细地址，不将更新时间当发布时间。分类及必要学历辅助交给公共交付层，不在适配器中用固定值填齐必填列。

## 真实验收记录模板

在 `docs/` 按批次记录：企业ID/来源ID、原始及最终入口依据、适配器/版本、校招范围、采集时刻、源目录总数、读取/复用/跳过数量、有效岗位数、严格导入与待补全数、结束依据、证据/快照路径、问题及后续条件。命令中记录参数，不记录密钥、Cookie 或会话。

只有离线 fixture 通过的站点仍待真实验证。公开岗位可读而投递需登录时继续采集公开内容；确需登录读取且无支持会话时报告障碍，不注册、投递或破解验证码。新依赖用 uv，平台公共改动回归受影响适配器，保留可复核的失败样本。
