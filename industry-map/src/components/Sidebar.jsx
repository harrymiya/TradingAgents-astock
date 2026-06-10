import React from 'react';
import './Sidebar.css';

export default function Sidebar({ industries, current, onSelect }) {
  const currentInfo = industries[current];

  // 计算每个产业链的环节数和股票数
  const stats = React.useMemo(() => {
    const s = {};
    for (const [name, info] of Object.entries(industries)) {
      if (name.startsWith('_')) continue;
      let stocks = 0;
      const links = Object.keys(info['环节']).length;
      for (const l of Object.values(info['环节'])) {
        stocks += l['股票'].length;
      }
      s[name] = { links, stocks };
    }
    return s;
  }, [industries]);

  return (
    <div className="sidebar">
      <h2>🏭 产业地图</h2>
      <div className="industry-list">
        {Object.entries(industries).filter(([n]) => !n.startsWith('_')).map(([name]) => (
          <button
            key={name}
            className={`industry-btn ${name === current ? 'active' : ''}`}
            onClick={() => onSelect(name)}
          >
            {name}
            <span className="badge">{stats[name].stocks}家</span>
          </button>
        ))}
      </div>
      {currentInfo && (
        <div className="industry-desc">
          <p>{currentInfo['描述']}</p>
          <div className="desc-stats">
            <span>🏗️ {Object.keys(currentInfo['环节']).length}个环节</span>
            <span>📈 {stats[current]?.stocks || 0}只股票</span>
          </div>
        </div>
      )}
    </div>
  );
}
