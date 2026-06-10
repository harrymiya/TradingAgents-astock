import React, { useState } from 'react';
import './DetailPanel.css';
import './ReportModal.css';
import RevealPanel from './RevealPanel';

// 涨用红色，跌用绿色（A股习惯）
function getChgColor(chg) {
  if (chg > 5) return '#ff2d2d';
  if (chg > 3) return '#ff5252';
  if (chg > 0) return '#ff6b6b';
  if (chg === 0) return '#8b949e';
  if (chg > -3) return '#51cf66';
  if (chg > -5) return '#2ea043';
  return '#00c853';
}

export default function DetailPanel({
  selectedNode,
  stockPrices,
  stockIndustry,
  industryName,
  industryData,
  onClose,
  onSelectStock,
  onBack,
  history,
  screeningInfo,
}) {
  // 没有选中任何节点时，显示产业链概览
  if (!selectedNode) {
    return (
      <div className="detail-panel">
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
  const isStock = node.type === 'stock';
  const isLink = node.type === 'link';
  const code = node.code;
  const price = stockPrices[code] || {};
  const industry = stockIndustry[code] || {};

  // 环节详情中点击公司后，实际显示的公司来自 history 最顶层
  const detailCode = history?.length > 0 ? history[history.length - 1].code : null;
  const detailPrice = detailCode ? stockPrices[detailCode] || {} : null;

  // 公司详情 — 直接选中的stock或从history点进来的
  const showCompany = isStock || detailCode;

  // 当前显示的公司信息
  const displayCode = showCompany ? (detailCode || code) : null;
  const displayPrice = detailCode ? detailPrice : price;
  const displayHistory = showCompany && history?.length > 0 ? history : null;

  return (
    <div className="detail-panel">
      <RevealPanel info={screeningInfo} onClose={() => {}} />
      <div className="detail-header">
        <h3>{isStock ? '📈 公司详情' : isLink ? '🏗️ 环节详情' : '🏭 产业链'}</h3>
        <button className="close-btn" onClick={onClose}>✕</button>
      </div>

      {/* 环节详情 */}
      {isLink && !detailCode && (
        <div className="detail-body">
          <LinkDetail
            node={node}
            stockPrices={stockPrices}
            stockIndustry={stockIndustry}
            onSelectStock={onSelectStock}
          />
        </div>
      )}

      {/* 公司详情 */}
      {displayCode && (
        <div className="detail-body">
          <CompanyDetail
            code={displayCode}
            price={displayPrice}
            industry={industry}
            linkName={node.linkName || (history?.[history.length - 1]?.linkName)}
            industryName={industryName}
            stockPrices={stockPrices}
            stockIndustry={stockIndustry}
            onBack={detailCode ? onBack : null}
            selectedNode={selectedNode}
          />
        </div>
      )}
    </div>
  );
}

/* ===== 产业链概览 ===== */
function IndustryOverview({ industryName, industryData }) {
  const links = industryData['环节'] || {};
  const desc = industryData['描述'] || '';
  const linkNames = Object.keys(links);
  const totalStocks = new Set();
  for (const ln of Object.values(links)) {
    for (const c of (ln['股票'] || [])) totalStocks.add(c);
  }

  return (
    <>
      <div className="detail-section">
        <h4 className="section-title">📋 产业链概况</h4>
        <div className="ind-overview-header">
          <span className="ind-name-large">{industryName}</span>
          <span className="ind-stats">{linkNames.length}个环节 · {totalStocks.size}家公司</span>
        </div>
        <p className="ind-desc">{desc}</p>
      </div>
      <div className="detail-section">
        <h4 className="section-title">🔗 各环节一览</h4>
        <div className="link-summary-list">
          {linkNames.map(name => {
            const ln = links[name];
            return (
              <div key={name} className="link-summary-item">
                <div className="ls-item-header">
                  <span className="ls-name">{name}</span>
                  <span className="ls-count">{ln['股票'].length}家</span>
                  <span className="ls-barrier">{'⭐'.repeat(ln['壁垒'] || 3)}</span>
                </div>
                <div className="ls-desc">{ln['描述'] || ''}</div>
                <div className="ls-tags">
                  {ln['上游']?.length > 0 && <span className="ls-tag upstream-tag">⬆{ln['上游'].join(', ')}</span>}
                  {ln['下游']?.length > 0 && <span className="ls-tag downstream-tag">⬇{ln['下游'].join(', ')}</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

/* ===== 环节详情 ===== */
function LinkDetail({ node, stockPrices, stockIndustry, onSelectStock }) {
  return (
    <>
      <div className="detail-section">
        <h4 className="link-name">{node.name}</h4>
        <p className="link-desc">{node.desc || '无描述'}</p>
        <div className="link-stats">
          <span className="stat">壁垒等级: {'⭐'.repeat(node.barrier || 3)}</span>
          <span className="stat">国产化率: {node.localRate || 50}%</span>
          <span className="stat">公司数: {node.stockCount}家</span>
        </div>
      </div>
      {node.upstream?.length > 0 && (
        <div className="detail-section">
          <h4 className="section-title flow-up">⬆️ 上游供应</h4>
          <div className="link-tags">
            {node.upstream.map(u => (<span key={u} className="flow-tag upstream">{u}</span>))}
          </div>
        </div>
      )}
      {node.downstream?.length > 0 && (
        <div className="detail-section">
          <h4 className="section-title flow-down">⬇️ 下游应用</h4>
          <div className="link-tags">
            {node.downstream.map(d => (<span key={d} className="flow-tag downstream">{d}</span>))}
          </div>
        </div>
      )}
      <div className="detail-section">
        <h4 className="section-title">🏢 所属公司 ({node.stockCount}家)</h4>
        <div className="stock-list">
          {(node.stocks || []).map(s => {
            const p = stockPrices[s.code] || {};
            const ind = stockIndustry[s.code] || {};
            const chg = p.chg || 0;
            return (
              <div key={s.code} className="stock-item clickable"
                onClick={() => onSelectStock({ code: s.code, name: p.name || s.code, linkName: node.name })}>
                <div className="stock-main">
                  <span className="stock-name">{p.name || s.code}</span>
                  <span className="stock-code">{s.code}</span>
                  <span className={`stock-chg ${chg >= 0 ? 'up' : 'down'}`}>{chg > 0 ? '+' : ''}{chg.toFixed(2)}%</span>
                </div>
                <div className="stock-sub">
                  <span className="stock-ind">{ind.l1 || ind.l2 || '未分类'}</span>
                  <span className="stock-link">{node.name}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

/* ===== 公司详情 ===== */
function CompanyDetail({ code, price, industry, linkName, industryName, stockPrices, stockIndustry, onBack, selectedNode }) {
  const chg = price.chg || 0;
  const chgColor = getChgColor(chg);
  const pe = price.pe || 0;
  const amplitude = price.amplitude || 0;
  const yearChg = price.yearChg || 0;
  const volume = price.volume || 0;

  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState(null);
  const [showReport, setShowReport] = useState(false);
  const [error, setError] = useState(null);

  const handleAnalyze = async () => {
    if (report) {
      setShowReport(true);
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const resp = await fetch(`/api/analyze?code=${code}`);
      const data = await resp.json();
      if (data.error) {
        setError(data.error);
      } else {
        setReport(data);
        setShowReport(true);
      }
    } catch (e) {
      setError('无法连接到分析服务，请确认 analyze_stock_api.py 已启动');
    }
    setAnalyzing(false);
  };

  return (
    <>
      {onBack && (<button className="back-btn" onClick={onBack}>← 返回</button>)}

      <div className="detail-section company-header">
        <h4 className="company-name">{price.name || code}</h4>
        <div className="company-code">{code}</div>
      </div>

      <div className="detail-section price-section">
        <div className="price-row">
          <span className="price-big" style={{ color: chgColor }}>{price.price ? price.price.toFixed(2) : '--'}</span>
          <span className="price-chg" style={{ color: chgColor }}>{chg > 0 ? '+' : ''}{chg.toFixed(2)}%</span>
        </div>
        <div className="price-detail">
          <div className="price-item"><span className="label">PE</span><span className="value">{pe > 0 ? pe.toFixed(1) : '--'}</span></div>
          <div className="price-item"><span className="label">振幅</span><span className="value">{amplitude.toFixed(1)}%</span></div>
          <div className="price-item"><span className="label">年涨跌</span><span className="value" style={{ color: getChgColor(yearChg) }}>{yearChg > 0 ? '+' : ''}{yearChg.toFixed(1)}%</span></div>
          <div className="price-item"><span className="label">成交量</span><span className="value">{(volume / 10000).toFixed(0)}万</span></div>
        </div>
      </div>

      <div className="detail-section">
        <h4 className="section-title">📂 所属行业</h4>
        <div className="industry-tags">
          {industry.l1 && <span className="ind-tag l1">{industry.l1}</span>}
          {industry.l2 && <span className="ind-tag l2">{industry.l2}</span>}
          {!industry.l1 && <span className="ind-tag muted">未分类</span>}
        </div>
      </div>

      <div className="detail-section">
        <h4 className="section-title">🔗 产业链环节</h4>
        <div className="link-badge">
          <span className="industry-name">{industryName}</span>
          <span className="arrow">→</span>
          <span className="link-name-badge">{linkName}</span>
        </div>
      </div>

      <div className="detail-section">
        <button className="analyze-btn" onClick={handleAnalyze} disabled={analyzing}>
          {analyzing ? '⏳ 分析中...' : report ? '📋 查看报告' : '🤖 AI深度分析'}
        </button>
        {analyzing && (
          <div className="analyze-progress">
            <div className="progress-bar"><div className="progress-fill"></div></div>
            <span>正在分析 {price.name || code}，请等待（约1-3分钟）...</span>
          </div>
        )}
      </div>

      {error && (
        <div className="detail-section error-section">
          <h4 className="section-title">❌ 分析失败</h4>
          <p className="error-text">{error}</p>
          <p className="error-hint">请在终端运行: <code>python3 analyze_stock_api.py</code></p>
        </div>
      )}

      {showReport && report && (
        <ReportModal report={report} onClose={() => setShowReport(false)} />
      )}
    </>
  );
}

/* ====== 报告弹窗 ====== */
function ReportModal({ report, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>📋 AI深度分析报告 — {report.name} ({report.code})</h3>
          <div className="modal-header-right">
            <span className="report-elapsed">⏱ {report.elapsed}秒</span>
            <button className="close-btn" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="modal-body">
          {report.market_report && (
            <div className="report-block">
              <h5>📈 市场分析师</h5><p>{report.market_report.substring(0, 800)}</p>
            </div>
          )}
          {report.news_report && (
            <div className="report-block">
              <h5>📰 新闻分析师</h5><p>{report.news_report.substring(0, 800)}</p>
            </div>
          )}
          {report.fundamentals_report && (
            <div className="report-block">
              <h5>📊 基本面分析师</h5><p>{report.fundamentals_report.substring(0, 800)}</p>
            </div>
          )}
          {report.hot_money_report && (
            <div className="report-block">
              <h5>💰 游资追踪</h5><p>{report.hot_money_report.substring(0, 800)}</p>
            </div>
          )}
          {(report.bull_history || report.bear_history) && (
            <div className="report-block debate-block">
              <h5>⚔️ Bull/Bear 辩论</h5>
              {report.bull_history && (
                <div className="debate-side bull">
                  <strong>🟢 BULL:</strong>
                  <p>{report.bull_history.substring(0, 1000)}</p>
                </div>
              )}
              {report.bear_history && (
                <div className="debate-side bear">
                  <strong>🔴 BEAR:</strong>
                  <p>{report.bear_history.substring(0, 1000)}</p>
                </div>
              )}
            </div>
          )}
          {report.judge_decision && (
            <div className="report-block judge-block">
              <h5>⚖️ 裁判判决</h5>
              <p>{report.judge_decision.substring(0, 1200)}</p>
            </div>
          )}
          {(report.risk_conservative || report.risk_aggressive || report.risk_neutral) && (
            <div className="report-block risk-block">
              <h5>🛡️ 风险评估</h5>
              {report.risk_conservative && (
                <div className="risk-side conservative">
                  <strong>🟦 保守:</strong>
                  <p>{report.risk_conservative.substring(0, 600)}</p>
                </div>
              )}
              {report.risk_aggressive && (
                <div className="risk-side aggressive">
                  <strong>🟥 激进:</strong>
                  <p>{report.risk_aggressive.substring(0, 600)}</p>
                </div>
              )}
              {report.risk_neutral && (
                <div className="risk-side neutral">
                  <strong>🟨 中性:</strong>
                  <p>{report.risk_neutral.substring(0, 600)}</p>
                </div>
              )}
            </div>
          )}
          {report.risk_judge && (
            <div className="report-block judge-block">
              <h5>⚖️ 风险裁判</h5>
              <p>{report.risk_judge.substring(0, 800)}</p>
            </div>
          )}
          {report.trader_plan && (
            <div className="report-block trader-block">
              <h5>📝 交易计划</h5>
              <p>{report.trader_plan.substring(0, 1200)}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
