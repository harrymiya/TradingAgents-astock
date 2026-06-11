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

function StockDetail({ code, stockPrices }) {
  const price = stockPrices[code] || {};
  return (
    <div className="stock-detail">
      <div className="stock-row">
        <span className="stock-name">{price.name || code}</span>
        <span className="stock-code">{code}</span>
      </div>
      <div className="stock-row">
        <span>现价</span>
        <span style={{color: getChgColor(price.chg || 0)}}>
          {price.price?.toFixed(2) || '--'}
        </span>
      </div>
      <div className="stock-row">
        <span>涨跌幅</span>
        <span style={{color: price.chg >= 0 ? '#ff6b6b' : '#51cf66'}}>
          {price.chg >= 0 ? '+' : ''}{price.chg?.toFixed(1) || '--'}%
        </span>
      </div>
      <div className="stock-row">
        <span>年度涨跌</span>
        <span style={{color: price.yearChg >= 0 ? '#ff6b6b' : '#51cf66'}}>
          {price.yearChg >= 0 ? '+' : ''}{price.yearChg?.toFixed(1) || '--'}%
        </span>
      </div>
      <div className="stock-row">
        <span>成交量</span>
        <span>{(price.volume || 0) > 10000 ? Math.round(price.volume / 10000) + '万' : price.volume || '--'}</span>
      </div>
      <div className="stock-row">
        <span>振幅</span>
        <span>{price.amplitude?.toFixed(1) || '--'}%</span>
      </div>
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
              const stockName = typeof stock === 'string' ? (stockNames[code] || code) : stock.name;
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
  onSelectStock,
  onBack,
  history,
}) {
  // 概览
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
  const isLink = node.type === 'link';
  const isStock = node.type === 'stock';
  const code = node.code;
  const displayCode = history?.length > 0 ? history[history.length - 1].code : code;

  // 查找该节点所属的section
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
      // 找不到所属section，用默认的第一个
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
          <StockDetail code={code} stockPrices={stockPrices} onSelectStock={onSelectStock} />
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
