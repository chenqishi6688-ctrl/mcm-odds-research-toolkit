# MCM v1.6.3+evidence1 完整能力报告

> 能力完整版不等于强制满级结论。每场仍按证据自动分为 FULL-MCM、MCM-DEGRADED、MARKET-STRUCTURE-ONLY 或 BLOCKED。

## 接受状态

- FULL-MCM：0；MCM-DEGRADED：1；MARKET-STRUCTURE-ONLY：0；BLOCKED：0。
- 历史规则：observe_only；稳定权重已改变：False。观察规则不得改变概率。

## 批次总表

> 硬门禁：体彩已展示的每条整数让球，其让胜、让平、让负必须与普通胜、平、负六项（或多让球时更多项）进入同一完整候选池后，才能截取前两项。

| 赛事 | 状态 | 第一候选 | 第二候选 | 0–1 | 2–3 | 4–6 | 7+ | 比分前三 | 半全场前二 | CI/资本标签 |
|---|---|---|---|---:|---:|---:|---:|---|---|---|
| Synthetic Home vs Synthetic Away | MCM-DEGRADED | home 59.1%（90m_home） | home_-1_side_loss 40.9%（主队90分钟净胜球 -1 < 0） | 23.0% | 46.1% | 28.4% | 2.5% | 1-0 11.5%；2-0 10.4%；1-1 10.4% | home/home 37.3%；draw/home 18.8% | CI-2 / straight_support_candidate |

## Synthetic Home vs Synthetic Away

- 状态：**MCM-DEGRADED**；原因：meaningful cross-book coverage incomplete；late observation missing；declared monitoring checkpoints incomplete；monitoring configuration and snapshot proofs absent
- 三层概率：市场=available；独立基线=available；MCM调整=available。 调整状态=applied。
- 前二结算覆盖：无论赛果均至少命中一项，不能作为预测命中率。旧版value_grade仅表示证据完整度，不表示正向投注价值。
- 报价成本（各市场分开计算）：普通胜平负 4.2%–4.6%；精确总进球 22.2%。赔率价值未证实；不把去水后的市场概率当作独立预测。
- 监测凭证：unverified；有效检查点 0/0；末次不同bookmaker ID 0。不同ID本身不证明来源经济独立。
- 资本卡：吸引={'direction': 'home', 'evidence': ['home-favourite narrative is visible; funded crowding is unknown']}；保护={'direction': 'home', 'evidence': ['two independent synthetic books retain home-side resistance']}；可行性={'direction': 'home', 'evidence': ['independent score matrix remains home-leading']}；闭环=partial；CI-2；标签=straight_support_candidate；含/不含资本=home/home；增量=strengthened。
- 排序反事实：不含资本第一=home 59.1%（90m_home）；含资本第一=home 59.1%（90m_home）；近同概率决胜=未应用；概率未改写=True。
- 诱导假设状态：explicit_card_unscored。这是一项可证伪假设，不是对操纵行为的事实认定。
- 非意图替代解释：ordinary repricing, model disagreement, liquidity or stale quotes。
- 反大众证据：narrative_only_or_unavailable。没有直接投注占比或成交量时，只能称为叙事吸引，不能称为大众资金拥挤。
- 情景排序：主流=home 59.1%（90m_home）；逆向=draw 21.9%（90m_draw）；尾部=7+ 2.5%。
- 最强反证：draw probability remains material。重排条件：two independent evidence groups reverse before kickoff。
- 历史影子层：observe_only；只显示触发与反例，不改变本场概率。
- v1.8研究影子层：unavailable；稳定权重已改变=False；正式概率增量=0。

## 验证与边界

- 验证器：MCM fixture validator v1.6.3+evidence1；通过 1/1 份机器记录。
- 独立基线覆盖：1/1。
- 资本层改变第一方向：0 场。
- 历史研究仅以 observe-only 影子层接入，未通过新冻结留出验证前不改变稳定权重。
- 本报告用于结构化研究，不保证赛果或收益。

