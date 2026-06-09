import React from 'react';
import './Tooltip.css';

export default function Tooltip({ data, onClose }) {
  if (!data) return null;

  const { node, x, y } = data;

  return (
    <div className="tooltip" style={{ left: x + 14, top: y - 10 }}>
      <div className="tooltip-close" onClick={onClose}>✕</div>
      {node.type === 'link' ? (
        <>
          <h3>{node.name}</h3>
          <div className="row">
            <span className="label">壁垒评分</span>
            <span className="value">{'🛡️'.repeat(node.barrier)} ({node.barrier}/5)</span>
          </div>
          <div className="row">
            <span className="label">国产化率</span>
            <span className="value">{node.localRate}%</span>
          </div>
          <div className="row">
            <span className="label">股票数量</span>
            <span className="value">{node.stockCount}只</span>
          </div>
          <div className="row">
            <span className="label">上游</span>
            <span className="value">{node.upstream?.join(' → ') || '无'}</span>
          </div>
          <div className="row">
            <span className="label">下游</span>
            <span className="value">{node.downstream?.join(' → ') || '无'}</span>
          </div>
          {node.desc && <p className="desc">{node.desc}</p>}
        </>
      ) : (
        <>
          <h3>{node.name} ({node.code})</h3>
          <div className="row">
            <span className="label">价格</span>
            <span className="value">{node.price.toFixed(2)}</span>
          </div>
          <div className="row">
            <span className="label">今日涨幅</span>
            <span className={`value ${(node.chg || 0) >= 0 ? 'up' : 'down'}`}>
              {node.chg > 0 ? '+' : ''}{node.chg?.toFixed(2)}%
            </span>
          </div>
          <div className="row">
            <span className="label">年度涨幅</span>
            <span className={`value ${(node.yearChg || 0) >= 0 ? 'up' : 'down'}`}>
              {node.yearChg > 0 ? '+' : ''}{node.yearChg?.toFixed(2)}%
            </span>
          </div>
          <div className="row">
            <span className="label">成交量</span>
            <span className="value">{(node.volume / 10000)?.toFixed(1)}万手</span>
          </div>
          {node.linkName && (
            <p className="desc">属于: {node.linkName}</p>
          )}
        </>
      )}
    </div>
  );
}
