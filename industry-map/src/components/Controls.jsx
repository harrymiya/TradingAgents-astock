import React from 'react';
import './Controls.css';

export default function Controls({
  colorMetric, onColorMetricChange,
  onRefresh, loading, lastUpdate
}) {
  return (
    <div className="controls">
      <label>着色:</label>
      <select value={colorMetric} onChange={e => onColorMetricChange(e.target.value)}>
        <option value="chg">今日涨跌</option>
        <option value="yearChg">年度涨跌</option>
        <option value="volume">成交量</option>
        <option value="amplitude">振幅</option>
        <option value="rsi">超买超卖</option>
        <option value="s3_score">S3评分</option>
        <option value="composite">综合评分</option>
        <option value="pos_20d">20日位置</option>
        <option value="ma20_pct">均线偏离</option>
      </select>

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
