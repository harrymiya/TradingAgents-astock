import React, { useState } from 'react';
import './DetailPanel.css';

function getChgColor(chg) {
  if (chg > 5) return '#ff2d2d';
  if (chg > 3) return '#ff5252';
  if (chg > 0) return '#ff6b6b';
  if (chg === 0) return '#8b949e';
  if (chg > -3) return '#51cf66';
  if (chg > -5) return '#2ea043';
  return '#00c853';
}

function IndustryOverview({ industryName, industryData }) {
  if (!industryData || !industryData.sections) return null;
  return (
    <div className="overview">
      <h4>{industryName}</h4>
      <div className="overview-sections">
        {industryData.sections.map((sec, i) => (
          <div key={i} className="overview-sec">
            <div className="overview-sec-name">{sec.name}</div>
            <div className="overview-sec-links">
              {sec.links.map((link, j) => (
                <span key={j} className="overview-link">{link.name}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function getSignalEmoji(score) {
  if (score >= 15) return '⭐';
  if (score >= 10) return '✨';
  return '🔹';
}

function getSignalLabel(score) {
  if (score >= 15) return '1级';
  if (score >= 10) return '2级';
  return '3级';
}

/** 深度分析弹窗 */
function AnalysisModal({ analysis, onClose }) {
  if (!analysis) return null;
  const r = analysis.result;
  if (!r) return null;

  const renderAnalyst = (label, content, color) => {
    if (!content) return null;
    return (
      <div className="am-block" style={{borderLeftColor: color}}>
        <div className="am-block-title">{label}</div>
        <div className="am-block-body">{content}</div>
      </div>
    );
  };

  return (
    <div className="am-overlay" onClick={onClose}>
      <div className="am-modal" onClick={e => e.stopPropagation()}>
        <div className="am-header">
          <span className="am-title">🤖 TradingAgents 深度分析报告</span>
          <button className="am-close" onClick={onClose}>✕</button>
        </div>
        <div className="am-body">
          {r.elapsed && <div className="am-meta">分析耗时：{r.elapsed}秒</div>}

          {r.market_analyst && renderAnalyst('📊 市场分析师', r.market_analyst, '#58a6ff')}
          {r.sentiment_analyst && renderAnalyst('😊 情绪分析师', r.sentiment_analyst, '#d29922')}
          {r.news_analyst && renderAnalyst('📰 新闻分析师', r.news_analyst, '#3fb950')}
          {r.fundamental_analyst && renderAnalyst('📈 基本面分析师', r.fundamental_analyst, '#bc8cff')}
          {r.policy_analyst && renderAnalyst('🏛️ 政策分析师', r.policy_analyst, '#f0883e')}
          {r.youzi_analyst && renderAnalyst('💹 游资追踪分析师', r.youzi_analyst, '#ff6b6b')}
          {r.jiemi_analyst && renderAnalyst('🔓 解禁监控分析师', r.jiemi_analyst, '#ffb320')}

          {/* Bull/Bear辩论 */}
          {r.bull_debate && (
            <div className="am-block" style={{borderLeftColor: '#3fb950'}}>
              <div className="am-block-title">🐂 多方辩论（Bull）</div>
              {Array.isArray(r.bull_debate) ? r.bull_debate.map((d, i) => (
                <div key={i} className="am-debate-line">{d}</div>
              )) : <div className="am-block-body">{r.bull_debate}</div>}
            </div>
          )}
          {r.bear_debate && (
            <div className="am-block" style={{borderLeftColor: '#ff6b6b'}}>
              <div className="am-block-title">🐻 空方辩论（Bear）</div>
              {Array.isArray(r.bear_debate) ? r.bear_debate.map((d, i) => (
                <div key={i} className="am-debate-line">{d}</div>
              )) : <div className="am-block-body">{r.bear_debate}</div>}
            </div>
          )}

          {r.risk_debate && (
            <div className="am-block" style={{borderLeftColor: '#d29922'}}>
              <div className="am-block-title">⚠️ 风险辩论</div>
              <div className="am-block-body">{r.risk_debate}</div>
            </div>
          )}

          {r.judge_decision && (
            <div className="am-block am-judge-block">
              <div className="am-block-title">⚖️ 裁判判决</div>
              <div className="am-block-body">{r.judge_decision}</div>
            </div>
          )}

          {r.trader_plan && (
            <div className="am-block am-trader-block">
              <div className="am-block-title">📋 交易计划</div>
              <div className="am-block-body">{r.trader_plan}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** 公司详情面板 */
function StockDetail({ node, stockPrices, analysis, analyzing }) {
  const code = node.code;
  const price = stockPrices[code] || {};

  const chain = node.chain;
  const sd = node.score_detail || {};
  const totalScore = node.total_score;
  const xies = node.xies_comment;
  const macro = node.macro_comment;

  const displayChg = node.chg != null ? node.chg : (price.chg || 0);
  const displayPrice = node.price != null ? node.price : (price.price || 0);

  const [showAnalysis, setShowAnalysis] = useState(false);

  const analysisDone = analysis && analysis.result && analysis.result.status === 'ok';

  return (
    <div className="stock-detail">
      {/* 头部：名称+代码 */}
      <div className="stock-header">
        <span className="sd-name">{node.name || price.name || code}</span>
        <span className="sd-code">{code}</span>
      </div>

      {/* 黄金坑评分徽标 */}
      {totalScore != null && (
        <div className="sd-signal-badge" style={{
          color: totalScore >= 15 ? '#d29922' : totalScore >= 10 ? '#58a6ff' : '#8b949e',
          borderColor: totalScore >= 15 ? '#d29922' : totalScore >= 10 ? '#58a6ff' : '#30363d',
        }}>
          {getSignalEmoji(totalScore)} 黄金坑{getSignalLabel(totalScore)} — {totalScore}分
        </div>
      )}

      {/* ===== 基础行情 ===== */}
      <div className="sd-section">
        <div className="sd-section-title">📊 实时行情</div>
        <div className="sd-grid">
          <div className="sd-grid-item">
            <span className="sd-label">现价</span>
            <span className="sd-value" style={{color: getChgColor(displayChg)}}>{displayPrice.toFixed(2)}</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">涨跌幅</span>
            <span className="sd-value" style={{color: displayChg >= 0 ? '#ff6b6b' : '#51cf66'}}>
              {displayChg >= 0 ? '+' : ''}{displayChg.toFixed(1)}%
            </span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">年度涨跌</span>
            <span className="sd-value" style={{color: (price.yearChg || 0) >= 0 ? '#ff6b6b' : '#51cf66'}}>
              {(price.yearChg || 0) >= 0 ? '+' : ''}{(price.yearChg || 0).toFixed(1)}%
            </span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">成交量</span>
            <span className="sd-value">{(price.volume || 0) > 10000 ? Math.round(price.volume / 10000) + '万' : (price.volume || '--')}</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">振幅</span>
            <span className="sd-value">{(price.amplitude || 0).toFixed(1)}%</span>
          </div>
        </div>
      </div>

      {/* ===== 黄金坑技术指标 ===== */}
      <div className="sd-section">
        <div className="sd-section-title">🕳️ 黄金坑指标</div>
        <div className="sd-grid">
          <div className="sd-grid-item">
            <span className="sd-label">链</span>
            <span className="sd-value sd-chain-tag">{chain || '未归属'}</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">ma60</span>
            <span className="sd-value" style={{color: (node.ma60 || 0) <= -8 ? '#51cf66' : '#8b949e'}}>{node.ma60 ?? '--'}%</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">pos20</span>
            <span className="sd-value" style={{color: (node.pos20 || 0) < 10 ? '#51cf66' : '#ff6b6b'}}>{node.pos20 ?? '--'}%</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">ma20</span>
            <span className="sd-value" style={{color: (node.ma20 || 0) < 0 ? '#ff6b6b' : '#8b949e'}}>{node.ma20 ?? '--'}%</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">vr5</span>
            <span className="sd-value" style={{color: (node.vr5 || 0) <= 0.7 ? '#58a6ff' : '#8b949e'}}>{node.vr5?.toFixed(2) ?? '--'}x</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">市值</span>
            <span className="sd-value">{(node.mcap || 0) >= 100 ? `${(node.mcap / 100).toFixed(0)}百亿` : `${(node.mcap || 0).toFixed(0)}亿`}</span>
          </div>
          <div className="sd-grid-item">
            <span className="sd-label">连跌</span>
            <span className="sd-value" style={{color: (node.dd || 0) >= 3 ? '#ff6b6b' : '#8b949e'}}>{node.dd ?? '--'}天</span>
          </div>
        </div>
      </div>

      {/* ===== 7维评分详情 ===== */}
      <div className="sd-section">
        <div className="sd-section-title">📐 7维评分</div>
        <div className="sd-score-grid">
          <span className="sd-score-item" style={{color: '#d29922'}}>链{sd.chain ?? 0}</span>
          <span className="sd-score-sep">|</span>
          <span className="sd-score-item" style={{color: '#58a6ff'}}>60{sd.ma60 ?? 0}</span>
          <span className="sd-score-sep">|</span>
          <span className="sd-score-item" style={{color: '#3fb950'}}>量{sd.vr ?? 0}</span>
          <span className="sd-score-sep">|</span>
          <span className="sd-score-item" style={{color: '#d29922'}}>位{sd.pos ?? 0}</span>
          <span className="sd-score-sep">|</span>
          <span className="sd-score-item" style={{color: '#ff6b6b'}}>跌{sd.dd ?? 0}</span>
          <span className="sd-score-sep">|</span>
          <span className="sd-score-item" style={{color: '#f0883e'}}>实{sd.real ?? 0}</span>
          <span className="sd-score-sep">|</span>
          <span className="sd-score-item" style={{color: '#bc8cff'}}>盘{sd.market ?? 0}</span>
        </div>
      </div>

      {/* ===== 星球双圈评价 ===== */}
      {xies && (
        <div className="sd-section sd-xies-section">
          <div className="sd-section-title">📖 谢SS评价（股道价值投资）</div>
          <div className="sd-comment-body">
            {xies.split('|').map((line, j) => (
              <div key={j} className="sd-comment-line">{line}</div>
            ))}
          </div>
        </div>
      )}
      {macro && (
        <div className="sd-section sd-macro-section">
          <div className="sd-section-title">📖 Macro评价（Labubu产业链）</div>
          <div className="sd-comment-body">
            {macro.split('|').map((line, j) => (
              <div key={j} className="sd-comment-line">{line}</div>
            ))}
          </div>
        </div>
      )}

      {/* ===== 深度分析区块（按钮弹窗） ===== */}
      <div className="sd-section sd-analysis-section">
        <div className="sd-section-title">🤖 TradingAgents 深度分析</div>
        {analyzing ? (
          <div className="sd-analysis-status">
            <span className="sd-analysis-spin">⏳</span> 8位分析师辩论中（约3-5分钟）...
          </div>
        ) : analysisDone ? (
          <div>
            <div className="sd-analysis-summary">
              ✅ 分析完成
              {analysis.result.elapsed && <span className="sd-analysis-elapsed">（{analysis.result.elapsed}秒）</span>}
            </div>
            {analysis.result.judge_decision && (
              <div className="sd-analysis-preview">
                ⚖️ {analysis.result.judge_decision.slice(0, 120)}
                {analysis.result.judge_decision.length > 120 && '...'}
              </div>
            )}
            <button className="sd-analysis-btn" onClick={() => setShowAnalysis(true)}>
              📄 查看完整分析报告
            </button>
          </div>
        ) : analysis && analysis.error ? (
          <div className="sd-analysis-status sd-analysis-error">❌ 分析失败: {analysis.error}</div>
        ) : (
          <div className="sd-analysis-status sd-analysis-idle">点击选股列表中的公司自动启动分析</div>
        )}
      </div>

      {/* 深度分析弹窗 */}
      {showAnalysis && analysis && analysis.result && (
        <AnalysisModal analysis={analysis} onClose={() => setShowAnalysis(false)} />
      )}
    </div>
  );
}

function LinkDetail({ node, section, stockPrices }) {
  return (
    <div className="link-detail">
      <h4 className="link-name">{node.name || section.name}</h4>
      <div className="link-stocks">
        {section.links.map((link, i) => (
          <div key={i} className="link-stock-group">
            <div className="link-title">{link.name}</div>
            {link.stocks.map((stock, j) => {
              const code = typeof stock === 'string' ? stock : stock.code;
              const stockName = typeof stock === 'string' ? (stockPrices[code]?.name || code) : stock.name;
              const price = stockPrices[code] || {};
              return (
                <div key={code || j} className="stock-item">
                  <span className="stock-dot" style={{background: getChgColor(price.chg || 0)}}></span>
                  <span className="stock-name">{price.name || stockName}</span>
                  <span className="stock-chg" style={{color: price.chg >= 0 ? '#ff6b6b' : '#51cf66'}}>
                    {price.chg >= 0 ? '+' : ''}{price.chg?.toFixed(1) || '--'}%
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DetailPanel({
  selectedNode,
  stockPrices,
  industryName,
  industryData,
  analysisState,
  style,
}) {
  // 概览模式
  if (!selectedNode) {
    return (
      <div className="detail-panel" style={style}>
        <div className="detail-header">
          <h3>🏭 产业链概览</h3>
        </div>
        <div className="detail-body">
          {industryName && industryData?.[industryName] ? (
            <IndustryOverview
              industryName={industryName}
              industryData={industryData[industryName]}
            />
          ) : (
            <div className="empty-hint">请在左侧选择一个产业链</div>
          )}
        </div>
      </div>
    );
  }

  const node = selectedNode;
  const isLink = node.type === 'link';
  const isStock = node.type === 'stock';
  const code = node.code;

  // 获取该股票的分析状态
  const analysis = code && analysisState ? analysisState[code] : null;
  const analyzing = analysis?.analyzing;

  // 查找该公司所属的产业链环节
  let currentSection = null;
  const currentIndData = industryData[industryName];
  if (currentIndData && currentIndData.sections) {
    for (const sec of currentIndData.sections) {
      for (const link of sec.links) {
        if (isLink && link.name === node.name) {
          currentSection = sec;
          break;
        }
        if (isStock && link.stocks.some(s => (typeof s === 'string' ? s : s.code) === code)) {
          currentSection = sec;
          break;
        }
      }
      if (currentSection) break;
    }
    if (!currentSection && isStock) {
      currentSection = currentIndData.sections[0];
    }
  }

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <h3>{isStock ? '📈 公司详情' : isLink ? '🏗️ 环节详情' : '📋 详情'}</h3>
      </div>
      <div className="detail-body">
        {isStock && code && (
          <StockDetail node={node} stockPrices={stockPrices} analysis={analysis} analyzing={analyzing} />
        )}
        {isLink && currentSection && (
          <LinkDetail node={node} section={currentSection} stockPrices={stockPrices} />
        )}
        {!isStock && !isLink && (
          <div className="empty-hint">{node.name || '未选中'}</div>
        )}
      </div>
    </div>
  );
}
