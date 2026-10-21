# 维护者审核、发布及回滚

## 信任边界

贡献文件是未信任输入；校验器不访问其URL。HTTPS和source_type不是官方身份或事实真实性证明。
PR内自带的approval/review文件一律不能作为授权。review命令只允许受信任维护者在私有受控环境使用；它不实现用户认证，审核文件也不是数字签名。
CI不得保存生产密钥，不得从外部PR直接发布数据。

## 审核与暂存

```sh
python scripts/community_data.py hash-field /private/catalog/programs.json PROGRAM_ID FIELD
python scripts/community_data.py validate contributions/FILE.json
# 维护者实际核对来源及适用范围后才执行：
python scripts/community_data.py review contributions/FILE.json --reviewer MAINTAINER --note "逐项核验结论" --out /private/reviews/REVIEW.json
python scripts/community_data.py stage contributions/FILE.json --approval /private/reviews/REVIEW.json --base /private/catalog --out /private/releases/v1
```

stage核对旧值hash和审核时的提交hash，不改基础库；新版本含programs/evidence、前后差异、审核和SHA256清单。已有目录拒绝覆盖。新版本仍是staged_not_deployed，不能据此宣布已上线。

传输前后执行 `python scripts/community_data.py verify-release /private/releases/v1`，核验文件集合、文件hash及审核绑定；篡改、缺失、额外文件和清单路径越界均拒绝。清单须由受信任维护者渠道获取：这是传输完整性校验，不是签名认证，也不替代生产回归。

## 同步服务器的验收顺序

1. 在完整数据库的隔离副本中替换两个暂存文件，保留taxonomy、学校库等关联资料；运行已有数据库校验器。
2. 使用既有标准问卷跑成绩/预算/地区/缺失输入、两学生隔离与完整HTML回归。记录代码版本、数据库hash及耗时。不能用本仓库空数据库假装通过生产回归。
3. 通过SSH/SCP上传到服务器新的版本目录，核对manifest全部hash；不得同步问卷和密钥到GitHub。
4. 发布前确认工作队列已排空，保留旧完整库和代码版本；应用停写后切换完整数据库版本，避免只切换一个JSON。
5. 重新启动服务，实际提交合成问卷并打开本人结果；失败即恢复旧完整版本。更新矩阵和本地/云端版本记录。

本提交实现离线校验与暂存工具。真实服务器的自动切换适配、队列排空和端到端发布演练仍待部署环境验收；此文档不冒称已经实现自动同步。
