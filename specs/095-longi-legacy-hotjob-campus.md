# SPEC-095 隆基绿能旧版 Hotjob 校招本级岗位

状态：待实现、待实采。日期：2026-10-14。归属 SPEC-050。

## 目标与非目标

从 COM0251 隆基绿能科技股份有限公司招聘管理平台 `https://www.hotjob.cn/wt/LONGI/mobweb/v8/position/list?brandCode=1&recruitType=1` 采集公开校园招聘岗位。该租户还展示制造事业群、研究院、部门等其他主体或归属不明的岗位，仅列表与详情都明确标为“隆基绿能科技股份有限公司”的岗位纳入；不以招聘平台品牌推断其他卡片的法人。不登录、投递或展开人数成多条。

## 输入输出与失败行为

站点旧版 v8 以服务端 HTML 显示校招 `recruitType=1`，首页每页 10 条，后续请求 `/wt/LONGI/mobweb/v8/position/list?ajaxMini=true&pc.currentPage=N&recruitType=1&brandCode=1`。每页从 `toDetailPostUrl(postId,1,page)` 提取唯一岗位 ID、标题、单位、工作地点及正文。正常页面用 `currentPage`、`lastPage` 确认继续；末页可能不返回这两个字段，须以少于 10 条和下一页返回相同 ID 集合共同确认，不能将页面结构异常自动视为完成。

对本级岗位读取公开详情 `/wt/LONGI/mobweb/v8/position/detail`，核对 ID、标题、准确单位、地点、职责和要求与列表一致。源站只显示相对“更新”时刻，未给岗位发布日期或截止日，两列保留空，不据“1天前更新”推算具体日期。目录和详情证据逐岗留存；分页重复、身份不符、正文缺失或请求失败报告局部失败并保留已成功记录。

## 可验证验收条件

1. 离线回放涵盖多页、末页重复验证、非本级机构排除、详情 ID/主体冲突、局部详情失败和空日期。
2. 独立状态库 `--window all` 实采，目录唯一 ID 与末页闭合，本级岗位有效数量大于零，`coverage=complete`。
3. 实采后才更新正式来源和绑定；阶段汇总去重审计、归档发布，Ruff、ty、pytest 通过。
