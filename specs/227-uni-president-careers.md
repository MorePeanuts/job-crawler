# SPEC-227 统一企业人力资源网

状态：已实现，待质量检查和真实验收；SPEC-156 固定 B 组 COM0164，不计入完成数。

## 目标与非目标

覆盖名录统一企业股份有限公司官网统一发布的职缺总览、集团事业伙伴 MA 六家企业职位及附属招募计划范围核对。官网 https://hr.pec.com.tw/zh-CN/job 当前16条、两页；2026集团MA为目录中一条计划，官网职缺条件另展开六个公司职位，Q8明确允许应届毕业生申请。不能只采第一页或把MA与展开职位重复计数。制造伙伴目前为简历登记与60天媒合，非公开岗位目录；暑期实习排除。各公司介绍处的一般官网/人力资源导航不宣称已遍历其所有独立招聘业务；本版覆盖官网统一发布的上述目录与MA计划。不得提交登记、简历、投递、登录或验证码。

## 输入、输出和已观察契约

输入上述企业与官方入口，输出公共 Job/Scope、证据及B组快照。页面真实 GET https://pechr-web-backend.azurewebsites.net/api/jobs 携带 page、countPerPage=10、targetDate（本轮UTC时刻），返回 items/totalCount。已观察page1十条、page2六条，totalCount=16；分页按固定本轮targetDate、总数、唯一jobId闭合，重复页、总数漂移、短页不得冒充终态。列表本身含完整职责与要求，无独立详情接口，不因缺日期跳读内联正文。

字段包括 jobId、orgCode、jobName、jobDesc、workPlace、conditionEdu/Lang/Exp/Others、startDate/endDate、isClosedMark/isActiveMark/isDeleteMark、isSubJob、jobIntroUrl。仅保存公开岗位字段，不提交createBy/lastUpdateBy内部账号字段。requestDate是可报到时间，不是发布日期；creationDate/lastUpdateDate也不替代发布日期。startDate在页面显示为本地职务发布日期；endDate为接口提供的带Z时区日期时间，保留原值参与公共截止判断，不把本地午夜擅自延长至当天日末；页面没有单独展示截止字段，该限制保留在字段来源。未知日期、地点、单位、学历、专业不推填。

MA主目录记录的报名入口与官方事业伙伴页核对，条件页六个公司分节各有职缺名称、工作内容、实作规划、职涯发展。以计划jobId+分节官方公司URL作稳定身份，重名标题仍分别保留。主目录计划记录计入父目录核对，不再导出为额外岗位。各职位职责逐节保留，公共申请资格与Q8应届资格带来源追加，实作培训不误判为实习。单位名称须有公开来源；只有Logo/URL时不猜法人名。MA日期只在证明主计划与六分节对应后继承，工作地不从页脚联系地址推填。

## 失败行为

主目录身份/结构/导航或计划集合变更、未知isSubJob、非空未解析jobIntroUrl、MA分节缺失/新增链接范围、资格问答不可读、日期语义不明、制造伙伴改为公开岗位、实习栏目出现正式校招等均报告partial并保留已有记录。已验证16只是本次事实，未来按源总数采集，不硬编码16为永远正确的总量。零目录必须有明确totalCount=0和完整范围核对，不能把请求失败或空白当零。

## 验收条件

有效回放涵盖两页、重复ID/页、源总数变化、字段与日期语义、MA一对六且不重复主计划、相同标题不同公司、应届与不限经验区分、实习/媒合排除、局部失败保留记录、内联全文全刷新。UVsync/Ruff/ty/pytest全部通过后独立状态库实采；coverage complete、目录与详情计数闭合、audit_delivery通过才启用绑定并进入B组总表。尚未真实验收。
