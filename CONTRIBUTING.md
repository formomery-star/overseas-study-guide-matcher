# 共同补充留学资料

先提交 Issue 认领具体“院校—专业—政策年—字段”，避免重复工作。资料缺失允许保留待核实，不允许猜值。代码修改也通过 PR，并附标准测试结果。

## 数据贡献流程

1. 在 Issue 写明项目编号、拟补字段、官方来源、年份和适用身份。
2. 维护者确认编号和当前字段 SHA256；新学校/专业先登记，禁止凭名称自动合并。
3. 复制 `contributions/example.json`，逐项填写。示例完全合成，example.org 不是真实院校。
4. 执行 `python scripts/community_data.py validate contributions/你的文件.json`。
5. 提交 PR。通过校验只代表格式正确；维护者仍须阅读官方正文、确认年份、身份、授权及范围。
6. 维护者在受控环境生成审核记录、构建独立版本、跑生产匹配回归，才可同步服务器。

不得提交学生信息、联系方式、问卷、报告、密钥、网页全文或未经授权的数据。程序使用 MIT；事实整理贡献须有权按 CC0-1.0 提供，来源网页版权不随之转移。无法确认授权先提 Issue。

## 标准格式

顶层字段：`schema_version=1`、`contribution_id`、`license=CC0-1.0`、`changes`。
每项：`program_id`、`field`、`expected_sha256`、`value`、`scope`、`evidence`。
来源：`id/url/publisher/source_type/checked_on/data_period/scope/summary`，均非空。
费用 value 至少包括 `amount`（非负数字）、`currency`、`period`、`student_status`。
checked_on 必须是真实阅读日期；data_period 是政策年份，两者不能混淆。旧年份不得升级为未来年。

允许字段列表见 `scripts/community_data.py` 的 FIELDS。资格、先修、英语可执行规则需单独代码及路径回归评审，本工具不会直接导入外部可执行规则。
允许的说明型字段保留现有结构；维护者须核对渲染契约。v1不宣称已覆盖每种字段的全部语义校验。

## 本地测试

`python -m unittest discover -s tests -v`

网页服务原有回归另运行：进入 webapp 后 `python -m unittest discover -s tests -v`。
新增故障与修复必须追加 test_record.md。
