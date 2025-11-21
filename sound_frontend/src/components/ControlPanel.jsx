import React from 'react';
import { polarToCartesian } from '../data/radarPoints';

const ControlPanel = ({ points, isRunning, onToggleRunning }) => {
  return (
    <div className="h-full flex flex-col p-6 space-y-6 overflow-y-auto">
      {/* Controls */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-radar-primary text-shadow">
          Controls
        </h2>
        
        <button
          onClick={onToggleRunning}
          className={`w-full px-4 py-3 rounded-lg font-medium transition-all duration-200 ${
            isRunning
              ? 'bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30'
              : 'bg-radar-primary/20 text-radar-primary border border-radar-primary/30 hover:bg-radar-primary/30'
          }`}
        >
          {isRunning ? '⏸ Pause' : '▶ Resume'}
        </button>
      </div>

      {/* Statistics */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-radar-primary text-shadow">
          Statistics
        </h2>
        
        <div className="space-y-2">
          <div className="flex justify-between items-center p-3 bg-radar-surface/50 rounded-lg border border-radar-grid/30">
            <span className="text-gray-400 text-sm">Active Points</span>
            <span className="text-radar-primary font-bold">{points.length}</span>
          </div>
          
          <div className="flex justify-between items-center p-3 bg-radar-surface/50 rounded-lg border border-radar-grid/30">
            <span className="text-gray-400 text-sm">Avg Distance</span>
            <span className="text-radar-secondary font-bold">
              {(points.reduce((sum, p) => sum + p.distance, 0) / points.length || 0).toFixed(2)}
            </span>
          </div>
          
          <div className="flex justify-between items-center p-3 bg-radar-surface/50 rounded-lg border border-radar-grid/30">
            <span className="text-gray-400 text-sm">Avg Intensity</span>
            <span className="text-radar-secondary font-bold">
              {(points.reduce((sum, p) => sum + p.intensity, 0) / points.length || 0).toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Detected Points */}
      <div className="space-y-4 flex-1">
        <h2 className="text-lg font-semibold text-radar-primary text-shadow">
          Detected Points
        </h2>
        
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {points.map((point) => (
            <div
              key={point.id}
              className="p-3 bg-radar-surface/50 rounded-lg border border-radar-grid/30 hover:border-radar-primary/50 transition-colors"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{
                      backgroundColor: `rgba(0, 255, 136, ${point.intensity})`,
                      boxShadow: `0 0 8px rgba(0, 255, 136, ${point.intensity * 0.8})`,
                    }}
                  />
                  <span className="text-sm font-medium text-gray-300">
                    Point #{point.id}
                  </span>
                </div>
                <span className="text-xs text-gray-500">
                  {new Date(point.timestamp).toLocaleTimeString()}
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-gray-500">Direction:</span>
                  <span className="ml-2 text-radar-primary font-mono">
                    {point.direction.toFixed(1)}°
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Distance:</span>
                  <span className="ml-2 text-radar-secondary font-mono">
                    {point.distance.toFixed(2)}
                  </span>
                </div>
                <div className="col-span-2">
                  <span className="text-gray-500">Intensity:</span>
                  <div className="mt-1 h-1.5 bg-radar-grid rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-radar-primary to-radar-secondary transition-all"
                      style={{ width: `${point.intensity * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="space-y-2 pt-4 border-t border-radar-grid/30">
        <h3 className="text-sm font-semibold text-gray-400">Legend</h3>
        <div className="space-y-1 text-xs text-gray-500">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-radar-primary" />
            <span>Detected Sound Source</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-radar-secondary" />
            <span>Radar Sweep</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;

