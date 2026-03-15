## ADDED Requirements

### Requirement: BTC and ETH price display
系统 SHALL 在日报中展示 BTC 和 ETH 的实时价格和日涨跌幅，使用 yfinance 的 BTC-USD 和 ETH-USD ticker。

#### Scenario: Crypto section in report
- **WHEN** BTC 和 ETH 数据拉取成功
- **THEN** 报告 SHALL 在外汇和债券之间新增"加密货币"小节，格式与其他行情一致

#### Scenario: Crypto data unavailable
- **WHEN** BTC 或 ETH 数据拉取失败
- **THEN** 跳过该小节，不影响其他板块
