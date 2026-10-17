# SPEC-160 软通动力校园目录

状态：已实现并通过本轮零正式岗位覆盖验收，详见 docs/remaining-271-acceptance.md；SPEC-156 A 组 COM0412。

## 目标与非目标

采集名录官方 `career.isoftstone.com/talent/htmls/xiaoyuanzhaopin/index.html` 校园目录，排除页面 API 明确标为实习的职位。2027 字样不能覆盖 hiretype_name=实习。本轮两页共 9 条全部为实习，应得到完整覆盖与零正式岗位，不计入有岗位企业。

## 观察契约、输入输出

页面 POST `/campus/all`：workCity=""，jobTypeId="0"，keyWord=""，maxcount=6，page 从 1 开始。响应 count=9，results 为岗位行；第一页 6 条，第二页 3 条且 next=null。next 可能指向后台 iyuanzhou 域名，仅核对页码和页大小，继续向实际观察到的官网端点发送同会话 POST，不跨到后台域名。

行 id 为稳定岗位身份；hiretype_name 为招聘类型。正式全职行读取 `/talent/htmls/xiaozhaozhiweixiangqing/index.html?id=<id>&recruitType=1`，从公开详情观察 `/campus/detail`，POST id。success="true" 且 data.id、name 需对应列表。列表 describe 只含职责，详情另有 jobrequirements，禁止把列表当完整正文。

职责 describe，要求 jobrequirements，学历 educational_name，工作地点 address_detail，发布时间 publish_date。未提供截止/实际详细地址则为空；列表 address_detail 只是省市名称，不填为详细地址。分类交公共 delivery。不保留 wxa_code 图片字段。继承公共增量 before_detail/remember。

## 失败行为与验收

未知招聘类型、筛选残留、总数变化、next 提前结束/异常页码、重复页、详情身份错配或请求失败保留 partial。实习计入 skipped_out_of_scope，不能生成正式校招岗位。

tests/test_isoftstone.py 回放验证分页末页、实习排除、完整详情要求、局部详情错误、异常终态和类型。临时绑定真实遍历两页核对 9=0详情+9实习排除并保存证据；真实有岗详情尚无正式样本，记录限制。质量门禁通过后启用。
