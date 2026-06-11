import React from 'react';
import './Controls.css';

export default function Controls({
  colorMetric, onColorMetricChange,
  layoutMode, onLayoutModeChange,
  onRefresh, loading, lastUpdate
}) {
  return (
    <div className="controls">
      <div className="controls-left">
        <div className="mode-switch">
          <button
            className={`mode-btn ${layoutMode === 'force' ? 'active' : ''}`}
            onClick={() => onLayoutModeChange('force')}
            title="力导向图"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="3" r="2.5" fill="currentColor"/>
              <circle cx="2" cy="11" r="2" fill="currentColor"/>
              <circle cx="12" cy="11" r="2" fill="currentColor"/>
              <line x1="7" y1="5.5" x2="2" y2="9" stroke="currentColor" strokeWidth="1"/>
              <line x1="7" y1="5.5" x2="12" y2="9" stroke="currentColor" strokeWidth="1"/>
            </svg>
            力导向
          </button>
          <button
            className={`mode-btn ${layoutMode === 'horizontal' ? 'active' : ''}`}
            onClick={() => onLayoutModeChange('horizontal')}
            title="横向产业链布局"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="3" width="3" height="8" rx="1" fill="currentColor"/>
              <rect x="5.5" y="3" width="3" height="8" rx="1" fill="currentColor"/>
              <rect x="10" y="3" width="3" height="8" rx="1" fill="currentColor"/>
              <line x1="4" y1="5" x2="5.5" y2="5" stroke="currentColor" strokeWidth="1"/>
              <line x1="4" y1="9" x2="5.5" y2="9" stroke="currentColor" strokeWidth="1"/>
              <line x1="8.5" y1="5" x2="10" y2="5" stroke="currentColor" strokeWidth="1"/>
              <line x1="8.5" y1="9" x2="10" y2="9" stroke="currentColor" strokeWidth="1"/>
              <polygon points="8,7 9,6 9,8" fill="currentColor"/>
              <polygon points="3.5,7 4.5,6 4.5,8" fill="currentColor"/>
            </svg>
            横向
          </button>
          <button
            className={`mode-btn ${layoutMode === 'star' ? 'active' : ''}`}
            onClick={() => onLayoutModeChange('star')}
            title="星形放射：一级节点为圆心，子环节四面放射"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="3" cy="3" r="2.5" fill="currentColor"/>
              <circle cx="7" cy="3" r="2.5" fill="currentColor"/>
              <circle cx="11" cy="3" r="2.5" fill="currentColor"/>
              <line x1="5.5" y1="3" x2="4.5" y2="3" stroke="currentColor" strokeWidth="1"/>
              <line x1="9.5" y1="3" x2="8.5" y2="3" stroke="currentColor" strokeWidth="1"/>
              <polygon points="6,2.5 6.5,3 6,3.5" fill="currentColor"/>
              <polygon points="10,2.5 10.5,3 10,3.5" fill="currentColor"/>
              <circle cx="3" cy="9" r="1.2" fill="currentColor" opacity="0.6"/>
              <circle cx="3" cy="11.5" r="1.2" fill="currentColor" opacity="0.6"/>
              <circle cx="1.5" cy="10.5" r="1.2" fill="currentColor" opacity="0.6"/>
              <circle cx="4.5" cy="10.5" r="1.2" fill="currentColor" opacity="0.6"/>
              <circle cx="7" cy="9" r="1.2" fill="currentColor" opacity="0.6"/>
              <circle cx="11" cy="9" r="1.2" fill="currentColor" opacity="0.6"/>
            </svg>
            星形
          </button>
        </div>
      </div>
      <div className="controls-center">
        <label>着色:</label>
        <select value={colorMetric} onChange={e => onColorMetricChange(e.target.value)}>
          <option value="chg">今日涨跌</option>
          <option value="yearChg">年度涨跌</option>
          <option value="volume">成交量</option>
          <option value="amplitude">振幅</option>
        </select>
      </div>
      <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
        {loading ? '⏳ 刷新中...' : '🔄 刷新'}
      </button>
      <div className="legend">
        <span className="legend-item">
          <span className="legend-color" style={{background: '#1a6bff'}}></span>低/卖
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#ffb320'}}></span>中
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#ff2d2d'}}></span>高/买
        </span>
      </div>
      <div className="update-time">🕐 {lastUpdate}</div>
    </div>
  );
}
