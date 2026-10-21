# 2026 独角兽候选适配器验收进度

截至 2026-10-21，按 SPEC-276 的固定基线新增 19 家有有效岗位的企业，目标 50 家尚未完成。各站均使用临时绑定真实全目录采集，`coverage=complete`，来源证据和逐岗快照保存在下表目录；导入约束未满足的岗位保留在待补全记录中。

| 来源 | 企业 | 适配器 | 目录记录 | 有效岗位 | 严格导入 | 待补全 | 快照 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| COM0510 | 长江存储 | zhiye-ymtc-campus@1 | 106 | 106 | 76 | 30 | `outputs/dev-unicorn50-COM0510-mapped/` |
| COM0513 | 长鑫科技 | zhiye-cxmt-campus@1 | 194 | 194 | 83 | 111 | `outputs/dev-unicorn50-COM0513-mapped/` |
| COM0518 | 追觅科技 | zhiye-dreame-campus@1 | 84 | 75 | 36 | 39 | `outputs/dev-unicorn50-COM0518-mapped/` |
| COM0521 | 元气森林 | feishu-yuanqi-campus@1 | 17 | 8 | 0 | 8 | `outputs/dev-unicorn50-COM0521/` |
| COM0522 | 远景动力 | zhiye-aesc-campus@1 | 1 | 1 | 0 | 1 | `outputs/dev-unicorn50-COM0522-mapped/` |
| COM0523 | 得物 | feishu-dewu-campus@1 | 162 | 154 | 0 | 154 | `outputs/dev-unicorn50-COM0523/` |
| COM0524 | 紫光展锐 | hotjob-unisoc-campus-2027@1 | 73 | 73 | 67 | 6 | `outputs/dev-unicorn50-COM0524/` |
| COM0528 | 蜂巢能源科技股份有限公司 | zhiye-svolt-campus@1 | 198 | 198 | 4 | 194 | `outputs/dev-unicorn50-COM0528/` |
| COM0556 | 歌尔微电子 | hotjob-goermicro-campus-2027@1 | 60 | 60 | 33 | 27 | `outputs/dev-unicorn50-COM0556-v2/` |
| COM0566 | 哈啰出行 | zhiye-hellobike-campus@1 | 44 | 44 | 3 | 41 | `outputs/dev-unicorn50-COM0566/` |
| COM0599 | 千寻智能 | feishu-spirit-ai-campus@1 | 55 | 33 | 0 | 33 | `outputs/dev-unicorn50-COM0599/` |
| COM0605 | 中科宇航 | zhiye-cas-space-campus@1 | 71 | 66 | 0 | 66 | `outputs/dev-unicorn50-COM0605/` |
| COM0615 | 树根互联 | zhiye-irootech-campus@1 | 41 | 39 | 0 | 39 | `outputs/dev-unicorn50-COM0615/` |
| COM0653 | 海柔创新 | zhiye-hairobotics-campus@1 | 87 | 87 | 29 | 58 | `outputs/dev-unicorn50-COM0653/` |
| COM0654 | 君乐宝 | zhiye-junlebao-campus@1 | 19 | 19 | 0 | 19 | `outputs/dev-unicorn50-COM0654/` |
| COM0658 | 银河航天 | zhiye-galaxy-campus@1 | 106 | 106 | 2 | 104 | `outputs/dev-unicorn50-COM0658/` |
| COM0719 | 乐禾食品 | zhiye-lehe-campus@1 | 13 | 13 | 0 | 13 | `outputs/dev-unicorn50-COM0719/` |
| COM0730 | 思必驰 | zhiye-aispeech-campus@1 | 38 | 38 | 25 | 13 | `outputs/dev-unicorn50-COM0730/` |
| COM0743 | 智慧芽 | zhiye-zhihuiya-campus@1 | 11 | 11 | 3 | 8 | `outputs/dev-unicorn50-COM0743/` |

合计 1380 条目录记录、1325 条有效岗位、361 条严格导入、964 条待补全。逐源采集时间见 `.runtime/batches/unicorn50-20261021/validated.json` 的 `as_of`；阶段数据不作为最终 50 家交付。

## 保留障碍与后续工作

- COM0536 昆仑芯、COM0611 粤芯半导体、COM0623 慧策、COM0682 认养一头牛、COM0748 e签宝：本次浏览器未取得可核对的完整岗位列表，未绑定。
- COM0505 微众银行与 COM0565 喜马拉雅：公开校园目录当前为零岗位；不计目标。
- COM0557 喜茶：校园类别混入实习与兼职，尚未形成可靠的正式校招范围。
- COM0625 千寻位置：当前所见主要为 2025 校招旧记录，暂不计入。
- COM0592 T3 出行：公开目录仅 4 条，含 26 届及更早的无截止岗位，届别有效性待复核。
- 继续选择 SPEC-275 候选直至有至少 50 个不同公司 ID 完成真实采集；之后执行 `bundle`、工作簿审计和 `archive --publish`。
