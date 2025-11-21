import React, { useState, useEffect, useRef } from 'react';
import Radar from './components/Radar';
import ControlPanel from './components/ControlPanel';
import PointsHistory from './components/PointsHistory';

function App() {
  const [points, setPoints] = useState([]); // Current points for radar display
  const [pointsHistory, setPointsHistory] = useState([]); // All points ever detected
  const [isRunning, setIsRunning] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // WebSocket connection
  useEffect(() => {
    if (!isRunning) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    const connectWebSocket = () => {
        // Try multiple ports in case 22222 is in use
        const ports = [22222, 22223, 22224, 22225, 22226, 22227];
      let currentPortIndex = 0;
      
      const tryConnect = (portIndex) => {
        if (portIndex >= ports.length) {
          console.error('✗ All ports tried, none available');
          setIsConnected(false);
          // Retry from beginning after 5 seconds
          if (isRunning) {
            reconnectTimeoutRef.current = setTimeout(() => {
              connectWebSocket();
            }, 5000);
          }
          return;
        }
        
        const port = ports[portIndex];
        const wsUrl = `ws://localhost:${port}`;
        console.log(`Attempting to connect to ${wsUrl}...`);
        
        try {
          const ws = new WebSocket(wsUrl);

          ws.onopen = () => {
            console.log(`✓ WebSocket connected to ${wsUrl}`);
            setIsConnected(true);
            currentPortIndex = portIndex; // Remember successful port
            if (reconnectTimeoutRef.current) {
              clearTimeout(reconnectTimeoutRef.current);
              reconnectTimeoutRef.current = null;
            }
          };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('📡 WebSocket message received:', data);
            console.log('  - Timestamp:', data.timestamp);
            console.log('  - Points count:', data.points ? data.points.length : 0);
            
            if (data.points && Array.isArray(data.points)) {
              // Log each point
              if (data.points.length > 0) {
                console.log('  - Points details:');
                data.points.forEach((point, index) => {
                  console.log(`    Point ${index + 1}:`, {
                    id: point.id,
                    direction: point.direction || point.theta_deg,
                    distance: point.distance,
                    intensity: point.intensity || point.confidence,
                    class_label: point.class_label,
                    color: point.color,
                    timestamp: point.timestamp,
                  });
                });
              }
              
              // Transform received data to match radar point format
              const transformedPoints = data.points.map((point, index) => ({
                id: point.id || index + 1,
                direction: point.direction || point.theta_deg || 0,
                distance: point.distance || 0.5,
                intensity: point.intensity || point.confidence || 0.5,
                timestamp: point.timestamp || Date.now(),
                classLabel: point.class_label || 'unknown',
                color: point.color || '#00d9ff',
              }));
              
              // Update current points for radar display
              setPoints(transformedPoints);
              
              // Update points history - add all new points that haven't been seen before
              // Once a point appears on radar, it stays in history forever
              if (transformedPoints.length > 0) {
                setPointsHistory(prevHistory => {
                  const existingIds = new Set(prevHistory.map(p => p.id));
                  const newPoints = transformedPoints.filter(p => !existingIds.has(p.id));
                  
                  // Update existing points in history with latest data (position, intensity, etc.)
                  const updatedHistory = prevHistory.map(histPoint => {
                    const currentPoint = transformedPoints.find(p => p.id === histPoint.id);
                    // If point is in current data, update it; otherwise keep the historical data
                    return currentPoint ? { ...currentPoint, timestamp: currentPoint.timestamp } : histPoint;
                  });
                  
                  // Add new points that have never been seen before
                  if (newPoints.length > 0) {
                    // Combine updated history with new points, sorted by timestamp (newest first)
                    const combinedHistory = [...newPoints, ...updatedHistory].sort((a, b) => 
                      new Date(b.timestamp) - new Date(a.timestamp)
                    );
                    console.log(`✓ Added ${newPoints.length} new point(s) to history (total: ${combinedHistory.length})`);
                    return combinedHistory;
                  }
                  
                  // No new points, just return updated history
                  return updatedHistory;
                });
                
                console.log(`✓ Processed ${transformedPoints.length} point(s) and updated radar display`);
              } else {
                console.log('  - No points to display (empty array)');
              }
            } else {
              // No points, but keep radar visible (empty array is fine)
              console.log('  - No points in message, clearing radar display');
              setPoints([]);
            }
          } catch (error) {
            console.error('✗ Error parsing WebSocket message:', error);
            console.error('  Raw message:', event.data);
          }
        };

          ws.onerror = (error) => {
            console.error(`✗ WebSocket error on port ${port}:`, error);
            setIsConnected(false);
          };

          ws.onclose = (event) => {
            console.log(`WebSocket disconnected from port ${port}`, event.code, event.reason);
            setIsConnected(false);
            wsRef.current = null;
            
            // If it was a successful connection that closed, try to reconnect to the same port
            // Otherwise, try next port
            if (event.code === 1006 && portIndex === currentPortIndex) {
              // Connection was successful before, try same port
              if (isRunning) {
                console.log(`Attempting to reconnect to port ${port} in 2 seconds...`);
                reconnectTimeoutRef.current = setTimeout(() => {
                  tryConnect(portIndex);
                }, 2000);
              }
            } else if (event.code === 1006 || event.code === 1002) {
              // Connection failed, try next port
              if (isRunning) {
                console.log(`Trying next port...`);
                setTimeout(() => {
                  tryConnect(portIndex + 1);
                }, 1000);
              }
            } else if (isRunning) {
              // Other close codes, retry same port
              reconnectTimeoutRef.current = setTimeout(() => {
                tryConnect(portIndex);
              }, 2000);
            }
          };

          wsRef.current = ws;
        } catch (error) {
          console.error(`Error creating WebSocket on port ${port}:`, error);
          setIsConnected(false);
          // Try next port
          if (isRunning) {
            setTimeout(() => {
              tryConnect(portIndex + 1);
            }, 1000);
          }
        }
      };
      
      // Start trying ports
      tryConnect(currentPortIndex);
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
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
                <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-radar-primary animate-pulse' : 'bg-red-500'}`}></span>
                {isConnected ? 'Real-time Direction of Arrival Visualization' : 'Connecting to WebSocket server...'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3 px-4 py-2 bg-radar-surface/50 rounded-lg border border-radar-grid/30">
              <div className="relative">
                <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-radar-primary animate-pulse shadow-lg shadow-radar-primary/50' : 'bg-red-500'}`}></div>
                {isConnected && (
                  <div className="absolute inset-0 w-3 h-3 rounded-full bg-radar-primary animate-ping opacity-75"></div>
                )}
              </div>
              <span className="text-sm font-medium text-gray-300">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden min-h-0 relative z-10">
        {/* Left Panel - Points History */}
        <div className="w-80 border-r border-radar-grid/50 bg-radar-surface/30 backdrop-blur-md shadow-2xl">
          <PointsHistory points={pointsHistory} />
        </div>

        {/* Radar View */}
        <div className="flex-1 flex items-center justify-center p-8 min-h-0 relative">
          <Radar points={points} />
        </div>

        {/* Right Panel - Control Panel */}
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

