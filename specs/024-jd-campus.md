# SPEC-024 京东应届生招聘

状态：代码与真实全量覆盖已验收。2026-10-12；导出见 `docs/adapter-batch3-acceptance.md`。

接入 COM0009 `campus.jd.com/#/jobs` 中由 `api/wx/position/page?type=present` 返回的公开应届生目录。已观察到首轮 `totalNumber=124`、每页 10 条，列表含完整职责、任职要求、发布时间、岗位唯一 `publishId` 和多个工作城市；`getProjectList` 给出应届生项目 ID（当前 56、57、58），必须用当轮项目树验证，不能混入实习或 TGT 专项。详情路由由点击岗位核验为 `#/details?id=<publishId>`。

适配器保留全部应届生岗位与源响应证据，按页核对 `totalNumber`、唯一键与终止；站点此接口的 `pageCount=0` 是未填值，页数由 `totalNumber/pageSize` 计算，不能误认为零页。地址从 `requirementVoList[].workCity` 去重合并。无可核实截止日时留空，不访问投递。项目树缺失或 ID 不符、重复岗位、正文缺失、意外筛选或 API 失败时停止受影响范围并报告 partial；已采岗位仍保存。回放覆盖首/次/末页、项目归属、重复页和缺失字段，真实采集须 `coverage=complete`，再绑定 ready。
