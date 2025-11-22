import React from 'react';
import { getClassColor } from '../data/classColors';

const PointsHistory = ({ points, onClear }) => {
  // Sort points by timestamp (newest first) to ensure latest points are at the top
  const sortedPoints = [...points].sort((a, b) => {
    const timeA = new Date(a.timestamp || 0).getTime();
    const timeB = new Date(b.timestamp || 0).getTime();
    return timeB - timeA; // Newest first
  });

  const handleClear = () => {
    if (onClear) {
      onClear();
    }
  };

  return (
    <div className="h-full flex flex-col p-6 space-y-4 overflow-y-auto">
      {/* Header */}
      <div className="pb-4 border-b border-radar-grid/30">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-radar-primary to-radar-secondary">
              Points History
            </h2>
            <p className="text-xs text-gray-500 mt-1">Detected Sound Sources</p>
          </div>
          {sortedPoints.length > 0 && (
            <button
              onClick={handleClear}
              className="group relative px-4 py-2 bg-gradient-to-r from-red-500/20 to-orange-500/20 hover:from-red-500/30 hover:to-orange-500/30 border border-red-500/40 hover:border-red-500/60 rounded-lg transition-all duration-300 shadow-md hover:shadow-lg hover:shadow-red-500/20 flex items-center gap-2"
            >
              {/* Animated background glow */}
              <div className="absolute inset-0 rounded-lg bg-gradient-to-r from-red-500/0 via-red-500/20 to-red-500/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 blur-sm"></div>
              
              {/* Icon */}
              <svg 
                className="w-4 h-4 text-red-400 group-hover:text-red-300 transition-colors relative z-10" 
                fill="none" 
                viewBox="0 0 24 24" 
                stroke="currentColor"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={2} 
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" 
                />
              </svg>
              
              {/* Text */}
              <span className="text-sm font-semibold text-red-400 group-hover:text-red-300 transition-colors relative z-10">
                Clear
              </span>
              
              {/* Pulse effect */}
              <div className="absolute inset-0 rounded-lg bg-red-500/20 animate-ping opacity-0 group-hover:opacity-100"></div>
            </button>
          )}
        </div>
      </div>

      {/* Points List */}
      <div className="space-y-2 flex-1 overflow-y-auto pr-2 custom-scrollbar">
        {sortedPoints.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            No points detected
          </div>
        ) : (
          // Show all points sorted by time (newest first)
          sortedPoints.map((point, index) => (
            <div
              key={point.id || `point-${index}`}
              className="p-4 bg-gradient-to-br from-radar-surface/60 to-radar-surface/40 rounded-xl border border-radar-grid/40 hover:border-radar-primary/50 transition-all duration-300 shadow-md hover:shadow-lg hover:shadow-radar-primary/10 group"
            >
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    {(() => {
                      // Use getClassColor to ensure color matches radar and legend
                      // Always use getClassColor - never fall back to point.color to ensure colors stay updated
                      const pointColor = getClassColor(point.classLabel);
                      
                      return (
                        <div
                          className="w-4 h-4 rounded-full animate-pulse"
                          style={{
                            backgroundColor: pointColor,
                            boxShadow: `0 0 12px ${pointColor}80`,
                          }}
                        />
                      );
                    })()}
                    <div className="absolute inset-0 w-4 h-4 rounded-full bg-radar-primary animate-ping opacity-75"></div>
                  </div>
                  <span className="text-sm font-semibold text-gray-300 group-hover:text-radar-primary transition-colors">
                    {point.classLabel || `Point #${point.id}`}
                  </span>
                </div>
                <span className="text-xs text-gray-500 font-mono">
                  {new Date(point.timestamp).toLocaleTimeString()}
                </span>
              </div>
              
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-2 bg-radar-surface/40 rounded-lg">
                  <div className="text-gray-500 mb-1">Direction</div>
                  <div className="text-radar-primary font-mono font-bold text-base">
                    {point.direction.toFixed(1)}°
                  </div>
                </div>
                <div className="p-2 bg-radar-surface/40 rounded-lg">
                  <div className="text-gray-500 mb-1">Distance</div>
                  <div className="text-radar-secondary font-mono font-bold text-base">
                    {point.distance.toFixed(2)}
                  </div>
                </div>
                <div className="col-span-2">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-gray-500">Intensity</span>
                    <span className="text-radar-primary font-mono font-semibold">
                      {(point.intensity * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2 bg-radar-grid rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-radar-primary via-radar-secondary to-radar-primary transition-all duration-500"
                      style={{ width: `${point.intensity * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default PointsHistory;

