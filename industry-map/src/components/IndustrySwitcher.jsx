import React from 'react';
import './IndustrySwitcher.css';

export default function IndustrySwitcher({ chains, current, onSwitch }) {
  if (!chains || chains.length <= 1) return null;

  return (
    <div className="industry-switcher">
      <span className="switcher-label">所属产业链：</span>
      <div className="switcher-list">
        {chains.map((name) => (
          <button
            key={name}
            className={`switcher-btn ${name === current ? 'active' : ''}`}
            onClick={() => onSwitch(name)}
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}
