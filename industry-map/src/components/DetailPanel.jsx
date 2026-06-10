import React from 'react';
import './DetailPanel.css';

// 颜色映射（与GraphCanvas一致）
function getChgColor(chg) {
  if (chg > 5) return '#00c853';
  if (chg > 3) return '#2ea043';
  if (chg > 0) return '#58a6ff';
  if (chg === 0) return '#8b949e';
  if (chg > -3) return '#f85149';
  if (chg > -5) return '#d73a49';
  return '#7d1a2c';
}

export default function DetailPanel({
  selectedNode,
  stockPrices,
  stockIndustry,
  industryName,
  onClose,
  onSelectStock,
  onBack,
  history, // 二级导航栈
}) {
  if (!selectedNode) return null;

  // 获取节点数据
  const node = selectedNode;
  const isStock = node.type === 'stock';
  const code = node.code;
  const price = stockPrices[code] || {};
  const industry = stockIndustry[code] || {};

  // 当前显示的stock详情（二级导航）
  const detailCode = history?.length > 1 ? history[history.length - 1].code : null;
  const detailPrice = detailCode ? stockPrices[detailCode] || {} : null;
  const detailIndustry = detailCode ? stockIndustry[detailCode] || {} : null;

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <h3>
          {isStock ? '📈 公司详情' : '🏗️ 环节详情'}
        </h3>
        <button className="close-btn" onClick={onClose}>✕</button>
      </div>

      {/* ---- 环节节点 ---- */}
      {!isStock && (
        <div className="detail-body">
          <div className="detail-section">
            <h4 className="link-name">{node.name}</h4>
            <p className="link-desc">{node.desc || '无描述'}</p>
            <div className="link-stats">
              <span className="stat">壁垒等级: {'⭐'.repeat(node.barrier || 3)}</span>
              <span className="stat">国产化率: {node.localRate || 50}%</span>
              <span className="stat">公司数: {node.stockCount}家</span>
            </div>
          </div>

          {/* 上游 */}
          {node.upstream?.length > 0 && (
            <div className="detail-section">
              <h4 className="section-title flow-up">⬆️ 上游供应</h4>
              <div className="link-tags">
                {node.upstream.map(u => (
                  <span key={u} className="flow-tag upstream">{u}</span>
                ))}
              </div>
            </div>
          )}

          {/* 下游 */}
          {node.downstream?.length > 0 && (
            <div className="detail-section">
              <h4 className="section-title flow-down">⬇️ 下游应用</h4>
              <div className="link-tags">
                {node.downstream.map(d => (
                  <span key={d} className="flow-tag downstream">{d}</span>
                ))}
              </div>
            </div>
          )}

          {/* 所属公司列表 */}
          <div className="detail-section">
            <h4 className="section-title">🏢 所属公司 ({node.stockCount}家)</h4>
            <div className="stock-list">
              {(node.stocks || []).map(s => {
                const p = stockPrices[s.code] || {};
                const ind = stockIndustry[s.code] || {};
                const chg = p.chg || 0;
                return (
                  <div
                    key={s.code}
                    className="stock-item clickable"
                    onClick={() => onSelectStock({ code: s.code, name: p.name || s.code, linkName: node.name })}
                  >
                    <div className="stock-main">
                      <span className="stock-name">{p.name || s.code}</span>
                      <span className="stock-code">{s.code}</span>
                      <span className={`stock-chg ${chg >= 0 ? 'up' : 'down'}`}>
                        {chg > 0 ? '+' : ''}{chg.toFixed(2)}%
                      </span>
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
        </div>
      )}

      {/* ---- 公司节点（或二级详情） ---- */}
      {isStock && !detailCode && (
        <CompanyDetail
          code={code}
          price={price}
          industry={industry}
          linkName={node.linkName}
          industryName={industryName}
          stockPrices={stockPrices}
          stockIndustry={stockIndustry}
          onBack={onBack}
        />
      )}

      {/* ---- 二级：从环节点进来的公司详情 ---- */}
      {detailCode && (
        <CompanyDetail
          code={detailCode}
          price={detailPrice}
          industry={detailIndustry}
          linkName={history[history.length - 1].linkName}
          industryName={industryName}
          stockPrices={stockPrices}
          stockIndustry={stockIndustry}
          onBack={onBack}
        />
      )}
    </div>
  );
}

function CompanyDetail({ code, price, industry, linkName, industryName, stockPrices, stockIndustry, onBack }) {
  const chg = price.chg || 0;
  const chgColor = getChgColor(chg);
  const pe = price.pe || 0;
  const amplitude = price.amplitude || 0;
  const yearChg = price.yearChg || 0;
  const volume = price.volume || 0;

  return (
    <div className="detail-body">
      {/* 返回按钮（二级导航） */}
      {onBack && (
        <button className="back-btn" onClick={onBack}>← 返回</button>
      )}

      <div className="detail-section company-header">
        <h4 className="company-name">{price.name || code}</h4>
        <div className="company-code">{code}</div>
      </div>

      {/* 实时行情 */}
      <div className="detail-section price-section">
        <div className="price-row">
          <span className="price-big" style={{ color: chgColor }}>
            {price.price ? price.price.toFixed(2) : '--'}
          </span>
          <span className="price-chg" style={{ color: chgColor }}>
            {chg > 0 ? '+' : ''}{chg.toFixed(2)}%
          </span>
        </div>
        <div className="price-detail">
          <div className="price-item">
            <span className="label">PE</span>
            <span className="value">{pe > 0 ? pe.toFixed(1) : '--'}</span>
          </div>
          <div className="price-item">
            <span className="label">振幅</span>
            <span className="value">{amplitude.toFixed(1)}%</span>
          </div>
          <div className="price-item">
            <span className="label">年涨跌</span>
            <span className="value" style={{ color: getChgColor(yearChg) }}>
              {yearChg > 0 ? '+' : ''}{yearChg.toFixed(1)}%
            </span>
          </div>
          <div className="price-item">
            <span className="label">成交量</span>
            <span className="value">{(volume / 10000).toFixed(0)}万</span>
          </div>
        </div>
      </div>

      {/* 所属行业 */}
      <div className="detail-section">
        <h4 className="section-title">📂 所属行业</h4>
        <div className="industry-tags">
          {industry.l1 && <span className="ind-tag l1">{industry.l1}</span>}
          {industry.l2 && <span className="ind-tag l2">{industry.l2}</span>}
          {!industry.l1 && <span className="ind-tag muted">未分类</span>}
        </div>
      </div>

      {/* 所属产业链环节 */}
      <div className="detail-section">
        <h4 className="section-title">🔗 产业链环节</h4>
        <div className="link-badge">
          <span className="industry-name">{industryName}</span>
          <span className="arrow">→</span>
          <span className="link-name-badge">{linkName}</span>
        </div>
      </div>

      {/* 该环节下其他公司 */}
      <div className="detail-section">
        <h4 className="section-title">🏢 同环节公司</h4>
        <div className="stock-list">
          {(price._sameLinkStocks || []).map(s => {
            if (s.code === code) return null;
            const p = stockPrices[s.code] || {};
            const sc = p.chg || 0;
            return (
              <div key={s.code} className="stock-item" style={{ opacity: 0.7 }}>
                <div className="stock-main">
                  <span className="stock-name">{p.name || s.code}</span>
                  <span className="stock-code">{s.code}</span>
                  <span className={`stock-chg ${sc >= 0 ? 'up' : 'down'}`}>
                    {sc > 0 ? '+' : ''}{sc.toFixed(2)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
