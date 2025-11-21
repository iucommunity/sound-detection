import React from 'react';

const PointsHistory = ({ points }) => {
  return (
    <div className="h-full flex flex-col p-6 space-y-4 overflow-y-auto">
      {/* Header */}
      <div className="pb-4 border-b border-radar-grid/30">
        <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-radar-primary to-radar-secondary">
          Points History
        </h2>
        <p className="text-xs text-gray-500 mt-1">Detected Sound Sources</p>
      </div>

      {/* Points List */}
      <div className="space-y-2 flex-1 overflow-y-auto pr-2 custom-scrollbar">
        {points.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            No points detected
          </div>
        ) : (
          // Show all points - no filtering
          points.map((point, index) => (
            <div
              key={point.id || `point-${index}`}
              className="p-4 bg-gradient-to-br from-radar-surface/60 to-radar-surface/40 rounded-xl border border-radar-grid/40 hover:border-radar-primary/50 transition-all duration-300 shadow-md hover:shadow-lg hover:shadow-radar-primary/10 group"
            >
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div
                      className="w-4 h-4 rounded-full animate-pulse"
                      style={{
                        backgroundColor: point.color || `rgba(0, 255, 136, ${point.intensity})`,
                        boxShadow: `0 0 12px ${point.color || `rgba(0, 255, 136, ${point.intensity * 0.9})`}`,
                      }}
                    />
                    <div className="absolute inset-0 w-4 h-4 rounded-full bg-radar-primary animate-ping opacity-75"></div>
                  </div>
                  <span className="text-sm font-semibold text-gray-300 group-hover:text-radar-primary transition-colors">
                    Point #{point.id}
                    {point.classLabel && (
                      <span className="ml-2 text-xs text-gray-500">({point.classLabel})</span>
                    )}
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

