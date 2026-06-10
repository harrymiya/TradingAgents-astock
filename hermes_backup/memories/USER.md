用户是缠论（缠中说禅）+ 盛京剑客价值投资的深入研究者。在 ~/文档/缠论/ 下有系统整理的缠论资料库，在 ~/文档/tianya/ 下有盛京剑客等天涯投资经典。核心方法论：缠论笔段中枢+背驰+三类买卖点 + 盛京剑客 P=PE×E + ROE>12% + 国资刚需消费框架 + 市场心理研究。

他是 TradingAgents-Astock 项目（/home/harrydolly/code/TradingAgents-astock）拥有者，希望将缠论作为第8位分析师Agent集成进去，同时保留Hermes缠论skills。他是理解多Agent架构细节的技术用户，习惯：我先调研→汇报发现→提出方案→他决定方向。要求分析系统性、分层式（价值→缠论→产业→心理→决策），有清晰推理和风险提示，不要模糊/大概的回答。
§
TradingAgents-astock 项目配置：DeepSeek API key 可通过 DEEPSEEK_API_KEY 环境变量传入；_PROVIDER_CONFIG 已预配 deepseek 的 base_url 和 env var 名；default_config.py 已改为 provider=deepseek, model=deepseek-chat；项目目录 /home/harrydolly/code/TradingAgents-astock/，venv 在 .venv/
§
用户是A股投资者，使用通达信软件，有Windows版通达信。偏好严格对照通达信公式实现，不喜欢我自己"放宽"或"猜测"公式含义。如果公式实现有问题，用户会直接指出并要求逐行核对原公式。用户注重数据完整性和全市场覆盖，不只是龙头股。用户要求数据库增量存储，不要每次全量拉取。
§
系统全面的交易者画像，请参见 skill "user-profile"。
§
Demands 体系化(系统性)思考 — 选股策略、持仓策略、买卖频率必须三要素匹配，不能孤立设计。曾批评我"什么样的选股策略就有对应的持仓策略"，认为策略三要素匹配是核心。
§
极度贴近实战导向 — 会直接指出回测与实战的差距（"盘中信号你怎么抓？每分钟扫描？"），不接受学术化简化回测。每次回测必须模拟真实操作流程（买入时机、交易成本、持仓周期匹配策略频率），每一步都可落地执行。
§
用户对选股的逻辑严谨性要求极高，能一眼识破技术方案中的取巧/偷懒（如"只取前80只实时数据"、"按今日涨幅排序取前300"）。要求如实承认设计缺陷而不是辩解。注重系统的诚实性和全市场覆盖胜过速度。
§
工程偏好：数据库单一数据源(astock_data.db)，DB → Python导出JSON → React/D3前端三层架构。industry-map/项目在 ~/code/TradingAgents-astock/industry-map/（React + D3力导向图）。产业链地图用React App（Vite构建），非静态HTML。习惯MEDIA发截图。给指令简明直接（"先聚焦X再Y"），重视数据全、准确、可执行。偏好批处理Python脚本 > 手动单步操作。