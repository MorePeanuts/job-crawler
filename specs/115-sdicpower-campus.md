# SPEC-115 国投电力 2027 校园招聘

状态：真实覆盖已验收。日期：2026-10-15。归属 SPEC-101。

## 目标与非目标

接入名录 COM0299 国投电力控股股份有限公司公开的 2027 届校招项目。高校与国聘平台信息指向 `https://sdicpower.iguopin.com/`；只采集该公司及已明确归属的企业校招岗位，排除社招和实习。

## 输入、输出与站点契约

2026-10-15 观察官方 `https://sdicpower.iguopin.com/job-campus` 的国聘接口：`activity/exclusive/v1/info?domain=sdicpower` 给出主体 `company_id=10685296837396155` 和名称；`company/organization/v1/tree` 返回以该公司为根的成员树及 `all_job_count=32`；`jobs/v1/list` 请求无地点/单位/关键词筛选，以 `company_id_with_sub=10685296837396155`、`nature=["115xW5oQ","11bTac9","114Fay7E"]` 查询，`data.total=32`。列表每条含唯一 `job_id`、明确 `company_id/company_name`、完整 `contents`、学历、地点和 `end_time`。根目录 32 与成员树 `all_job_count` 需按实时值一致；分页至唯一 ID 与总数闭合，岗位招聘单位必须存在于成员树。`start_time` 是招聘起始时间而非源站发布时间，`refresh_time/update_time` 也不作为发布时间。保留原始业务单位和部门，不能称子公司岗位为股份本部直招。

## 失败行为

入口不存在、缺少项目身份或单位、仅呈现其他法人、分页/详情不闭合时保留证据并报告，不计入新增 50 家。

## 可验证验收条件

1. 回放覆盖项目身份、分页、岗位内容与失败。
2. 真实全量覆盖完整且有有效正式校招岗位。
3. 通过后启用绑定和更新批次记录。

## 真实验收

`outputs/dev-20261015-COM0299` 的 `--window all` 于 2026-10-15 10:48（上海）验证机构树 `all_job_count=32` 与 `expected=listed=unique=details=32` 一致，末页闭合，`coverage=complete`，选中 32 条。站点覆盖运行禁用模型，信息表 32 条、严格导入 0、待补全 32。逐页快照及机构树证据保留在运行目录。
