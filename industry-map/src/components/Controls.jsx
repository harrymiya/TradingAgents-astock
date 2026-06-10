import React from 'react';
import './Controls.css';

export default function Controls({
  colorMetric, onColorMetricChange,
  onRefresh, loading, lastUpdate
}) {
  return (
    <div className="controls">
      <label>着色/大小:</label>
      <select value={colorMetric} onChange={e => onColorMetricChange(e.target.value)}>
        <option value="chg">今日涨跌幅</option>
        <option value="yearChg">年度涨跌幅</option>
        <option value="volume">成交量</option>
        <option value="amplitude">振幅</option>
      </select>

      <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
        {loading ? '⏳ 刷新中...' : '🔄 刷新'}
      </button>

      <div className="legend">
        <span className="legend-item">
          <span className="legend-color" style={{background: '#1a6bff'}}></span>跌
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#ffb320'}}></span>平
        </span>
        <span className="legend-item">
          <span className="legend-color" style={{background: '#ff2d2d'}}></span>涨
        </span>
      </div>

      <div className="update-time">🕐 {lastUpdate}</div>
    </div>
  );
}
