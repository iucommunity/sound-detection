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
    <div className="w-full h-full flex flex-col bg-gradient-to-br from-radar-background via-radar-surface to-radar-background relative overflow-hidden" style={{ minHeight: '100vh' }}>
      {/* Animated background particles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {[...Array(20)].map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full bg-radar-primary/10"
            style={{
              width: Math.random() * 4 + 2 + 'px',
              height: Math.random() * 4 + 2 + 'px',
              left: Math.random() * 100 + '%',
              top: Math.random() * 100 + '%',
              animation: `float ${15 + Math.random() * 10}s infinite ease-in-out`,
              animationDelay: Math.random() * 5 + 's',
            }}
          />
        ))}
      </div>
      
      {/* Header */}
      <header className="px-8 py-5 border-b border-radar-grid/50 bg-radar-surface/40 backdrop-blur-md flex-shrink-0 relative z-10 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-radar-primary/20 to-radar-secondary/20 border border-radar-primary/30 flex items-center justify-center">
              <svg className="w-6 h-6 text-radar-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div>
              <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-radar-primary to-radar-secondary text-shadow-strong">
                Sound Detection Radar
              </h1>
              <p className="text-sm text-gray-400 mt-1 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-radar-primary animate-pulse"></span>
                Real-time Direction of Arrival Visualization
              </p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3 px-4 py-2 bg-radar-surface/50 rounded-lg border border-radar-grid/30">
              <div className="relative">
                <div className="w-3 h-3 rounded-full bg-radar-primary animate-pulse shadow-lg shadow-radar-primary/50"></div>
                <div className="absolute inset-0 w-3 h-3 rounded-full bg-radar-primary animate-ping opacity-75"></div>
              </div>
              <span className="text-sm font-medium text-gray-300">Active</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden min-h-0 relative z-10">
        {/* Radar View */}
        <div className="flex-1 flex items-center justify-center p-8 min-h-0 relative">
          <Radar points={points} />
        </div>

        {/* Control Panel */}
        <div className="w-80 border-l border-radar-grid/50 bg-radar-surface/30 backdrop-blur-md shadow-2xl">
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

