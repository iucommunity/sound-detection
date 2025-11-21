import React from 'react';
import { polarToCartesian } from '../data/radarPoints';

const ControlPanel = ({ points, isRunning, onToggleRunning }) => {
  const avgDistance = points.reduce((sum, p) => sum + p.distance, 0) / points.length || 0;
  const avgIntensity = points.reduce((sum, p) => sum + p.intensity, 0) / points.length || 0;
  
  return (
    <div className="h-full flex flex-col p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div className="pb-4 border-b border-radar-grid/30">
        <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-radar-primary to-radar-secondary">
          Control Panel
        </h2>
        <p className="text-xs text-gray-500 mt-1">System Status & Monitoring</p>
      </div>
      
      {/* Controls */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Controls
        </h3>
        
        <button
          onClick={onToggleRunning}
          className={`w-full px-4 py-3.5 rounded-xl font-semibold transition-all duration-300 transform hover:scale-105 shadow-lg ${
            isRunning
              ? 'bg-gradient-to-r from-red-500/20 to-red-600/20 text-red-400 border-2 border-red-500/40 hover:border-red-500/60 hover:shadow-red-500/20'
              : 'bg-gradient-to-r from-radar-primary/20 to-radar-secondary/20 text-radar-primary border-2 border-radar-primary/40 hover:border-radar-primary/60 hover:shadow-radar-primary/20'
          }`}
        >
          <div className="flex items-center justify-center gap-2">
            {isRunning ? (
              <>
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <span>Pause</span>
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                </svg>
                <span>Resume</span>
              </>
            )}
          </div>
        </button>
      </div>

      {/* Statistics */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Statistics
        </h3>
        
        <div className="space-y-3">
          <div className="p-4 bg-gradient-to-br from-radar-surface/60 to-radar-surface/40 rounded-xl border border-radar-grid/40 shadow-lg hover:border-radar-primary/30 transition-all">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-radar-primary/20 flex items-center justify-center">
                  <svg className="w-5 h-5 text-radar-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                  </svg>
                </div>
                <div>
                  <div className="text-xs text-gray-500">Active Points</div>
                  <div className="text-2xl font-bold text-radar-primary">{points.length}</div>
                </div>
              </div>
            </div>
          </div>
          
          <div className="p-4 bg-gradient-to-br from-radar-surface/60 to-radar-surface/40 rounded-xl border border-radar-grid/40 shadow-lg hover:border-radar-secondary/30 transition-all">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-gray-500">Average Distance</span>
              <span className="text-lg font-bold text-radar-secondary font-mono">
                {avgDistance.toFixed(2)}
              </span>
            </div>
            <div className="h-2 bg-radar-grid rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-radar-secondary to-radar-primary transition-all duration-500"
                style={{ width: `${Math.min(100, avgDistance * 100)}%` }}
              />
            </div>
          </div>
          
          <div className="p-4 bg-gradient-to-br from-radar-surface/60 to-radar-surface/40 rounded-xl border border-radar-grid/40 shadow-lg hover:border-radar-primary/30 transition-all">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-gray-500">Average Intensity</span>
              <span className="text-lg font-bold text-radar-primary font-mono">
                {avgIntensity.toFixed(2)}
              </span>
            </div>
            <div className="h-2 bg-radar-grid rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-radar-primary to-radar-secondary transition-all duration-500"
                style={{ width: `${avgIntensity * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="space-y-3 pt-4 border-t border-radar-grid/30">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Legend</h3>
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-3 p-2 bg-radar-surface/40 rounded-lg">
            <div className="w-3 h-3 rounded-full bg-radar-primary shadow-lg shadow-radar-primary/50" />
            <span className="text-gray-300">Detected Sound Source</span>
          </div>
          <div className="flex items-center gap-3 p-2 bg-radar-surface/40 rounded-lg">
            <div className="w-3 h-3 rounded-full bg-radar-secondary shadow-lg shadow-radar-secondary/50" />
            <span className="text-gray-300">Radar Sweep</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;

