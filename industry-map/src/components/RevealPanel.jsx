import React from 'react';
import './RevealPanel.css';

export default function RevealPanel({ info, onClose }) {
  if (!info) return null;

  const chg = parseFloat(info.chg) || 0;
  const close = parseFloat(info.close) || 0;

  return (
    <div className="reveal-panel">
      <div className="reveal-header">
        <span className="reveal-title">📋 选股信息</span>
        <button className="reveal-close" onClick={onClose}>✕</button>
      </div>
      <div className="reveal-body">
        <div className="reveal-row">
          <span className="reveal-label">代码</span>
          <span className="reveal-value">{info.code}</span>
        </div>
        <div className="reveal-row">
          <span className="reveal-label">名称</span>
          <span className="reveal-value">{info.name}</span>
        </div>
        <div className="reveal-row">
          <span className="reveal-label">策略</span>
          <span className="reveal-tag">{info.strategy}</span>
        </div>
        <div className="reveal-row">
          <span className="reveal-label">现价</span>
          <span className="reveal-value">{close.toFixed(2)}</span>
        </div>
        <div className="reveal-row">
          <span className="reveal-label">涨幅</span>
          <span className={`reveal-value chg-${chg >= 0 ? 'up' : 'down'}`}>
            {chg > 0 ? '+' : ''}{chg.toFixed(2)}%
          </span>
        </div>
        {info.detail && (
          <div className="reveal-detail">
            <span className="reveal-label">选股依据</span>
            <p className="reveal-detail-text">{info.detail}</p>
          </div>
        )}
      </div>
    </div>
  );
}
