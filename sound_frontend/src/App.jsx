import React, { useState, useEffect } from 'react';
import Radar from './components/Radar';
import ControlPanel from './components/ControlPanel';
import { radarPoints as initialPoints } from './data/radarPoints';

function App() {
  const [points, setPoints] = useState(initialPoints);
  const [isRunning, setIsRunning] = useState(true);

  // Simulate real-time updates
  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      setPoints((prevPoints) => {
        // Update existing points with slight variations
        return prevPoints.map((point) => ({
          ...point,
          distance: Math.max(0.1, Math.min(0.9, point.distance + (Math.random() - 0.5) * 0.05)),
          intensity: Math.max(0.3, Math.min(1.0, point.intensity + (Math.random() - 0.5) * 0.1)),
        }));
      });
    }, 100);

    return () => clearInterval(interval);
  }, [isRunning]);

  return (
    <div className="w-full h-full flex flex-col bg-gradient-to-br from-radar-background via-radar-surface to-radar-background" style={{ minHeight: '100vh' }}>
      {/* Header */}
      <header className="px-8 py-4 border-b border-radar-grid/50 bg-radar-surface/30 backdrop-blur-sm flex-shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-radar-primary text-shadow">
              Sound Detection Radar
            </h1>
            <p className="text-sm text-gray-400 mt-1">
              Real-time Direction of Arrival Visualization
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-radar-primary animate-pulse shadow-lg shadow-radar-primary/50"></div>
              <span className="text-sm text-gray-300">Active</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Radar View */}
        <div className="flex-1 flex items-center justify-center p-8 min-h-0">
          <Radar points={points} />
        </div>

        {/* Control Panel */}
        <div className="w-80 border-l border-radar-grid/50 bg-radar-surface/20 backdrop-blur-sm">
          <ControlPanel
            points={points}
            isRunning={isRunning}
            onToggleRunning={() => setIsRunning(!isRunning)}
          />
        </div>
      </div>
    </div>
  );
}

export default App;

