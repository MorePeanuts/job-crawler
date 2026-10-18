# SPEC-221 长江实业官网职位目录

状态：开发中；SPEC-156固定B组COM0297。

## 目标与输入输出

输入名录长江实业集团有限公司，官方https://www.ckah.com/careers。覆盖该集团官网Careers全部部门、全部分页和内联展开正文，输出Job/Scope、真实证据及B组岗位表。当前两页8+4，共12个公开岗位，第二页Sales Professionals明确欢迎应届且无需全职经验。范围为集团官网统一公布的职位，不声称已遍历各投资公司另行运营的独立招聘网站；不将长江和记等同名关联企业归入本公司，不投递、不发邮件。

## 目录协议

Drupal静态HTML中.panel-section包含无筛选form[action=/careers]，select[name=tag_id]的selected必须All；岗位.panel-title a的#accordion-数字-1链接对应.panel-collapse及.panel-body，真实Ref.:业务编号唯一。标题锚点与正文容器必须一一对应，部门标题不作岗位。职责/要求已内联，无需点击发送、登录或抓申请接口。

nav.pager当前aria-current与?page=0/1一致；首屏有next与last指向page1，第二页只有previous、无next。按照实际下一页链接遍历，校验同域同路径、无局部筛选、逐页递增、末页一致。非末页8条，末页1–8条；总量由完整末页闭合，不拿首页8条当全量。无分页/零页的新形态本版未实证，明确失败而非推断零；100页硬上限，重页/重ID/Ref重复/短页/变末页均报错并保留已成功记录。

## 正文与范围

Ref后有Responsibilities:/Requirements:时分别解析；仅资格条目时全文放requirements，duties留空，不把资格杜撰为职责。附图、附件或新增外部详情链接失败待展开。源没有发布日期、截止日、岗位地点和必需学历结构字段，保持空；不使用网站页脚年份、发布日期后的六周通用回复说明、公司邮寄地址推定字段。source_url保留真实分页加岗位锚点。

明确fresh/recent/new graduates欢迎文字作为应届资格；仅university graduate表示学历，不算校招。Sales Professionals虽前文经验要求2年，但明确fresh graduates和no prior full-time experience required例外，纳入校招；Temporary Sales Service Assistant要求每周3–5天、学生也可，标临时岗位排除正式校招。其余混合目录记录保留并按未明确校招排除，不称“没有职位”。每次刷新完整内联正文，日期未知的all岗位保留，day按公共首次发现策略。

## 失败与验收

主体、无筛选、分页、身份、正文关联和终态任何缺口保留partial/blocked，不默认为空成功。回放包括两页12岗位、次页应届、临时排除、资格不冒充职责、日期不猜、Ref/ID重复、错页/丢页/短页/筛选/附件及局部失败。完整UVsync/Ruff/ty/pytest通过后独立状态库实采，核对12目录与1有效的实时结果、覆盖和审计；通过才启用与B组汇总。实际数量变化按完整分页规则验证，不以本规范预期替代实采。
