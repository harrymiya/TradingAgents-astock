import React from 'react';
import './IndustrySwitcher.css';

export default function IndustrySwitcher({ chains, current, onSwitch }) {
  if (!chains || chains.length <= 1) return null;

  return (
    <div className="industry-switcher">
      <span className="switcher-label">所属产业链：</span>
      <select
        className="switcher-select"
        value={current}
        onChange={(e) => onSwitch(e.target.value)}
      >
        {chains.map((name) => (
          <option key={name} value={name}>{name}</option>
        ))}
      </select>
    </div>
  );
}
