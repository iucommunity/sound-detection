import React, { useState, useEffect } from 'react';
import { CLASS_LIST } from '../data/classColors';
import { getClassId } from '../data/classIds';

const SettingsDialog = ({ isOpen, onClose, onSave, wsRef }) => {
  const [settings, setSettings] = useState({});

  // Initialize settings state when dialog opens
  useEffect(() => {
    if (isOpen) {
      // Initialize empty settings for all classes
      const initialSettings = {};
      CLASS_LIST.forEach((classItem) => {
        initialSettings[classItem.name] = {
          L0_db: '',
          sigma_L0_db: '',
          r0_m: '',
          a_db_per_m: '',
        };
      });
      setSettings(initialSettings);
    }
  }, [isOpen]);

  const handleInputChange = (className, field, value) => {
    setSettings((prev) => {
      const currentClassSettings = prev[className] || {
        L0_db: '',
        sigma_L0_db: '',
        r0_m: '',
        a_db_per_m: '',
      };
      return {
        ...prev,
        [className]: {
          ...currentClassSettings,
          [field]: value,
        },
      };
    });
  };

  const handleSet = () => {
    // Build the data object with only classes that have all 4 fields filled
    const dataToSend = {};
    let hasValidData = false;

    CLASS_LIST.forEach((classItem) => {
      const classSettings = settings[classItem.name];
      if (
        classSettings &&
        classSettings.L0_db !== '' &&
        classSettings.sigma_L0_db !== '' &&
        classSettings.r0_m !== '' &&
        classSettings.a_db_per_m !== ''
      ) {
        const classId = getClassId(classItem.name);
        if (classId) {
          dataToSend[classId] = {
            L0_db: parseFloat(classSettings.L0_db),
            sigma_L0_db: parseFloat(classSettings.sigma_L0_db),
            r0_m: parseFloat(classSettings.r0_m),
            a_db_per_m: parseFloat(classSettings.a_db_per_m),
          };
          hasValidData = true;
        }
      }
    });

    if (!hasValidData) {
      alert('Please fill all 4 fields for at least one class.');
      return;
    }

    // Check WebSocket connection - use the same WebSocket that receives points data
    console.log('[SettingsDialog] Checking WebSocket connection...');
    console.log('[SettingsDialog] wsRef:', wsRef);
    console.log('[SettingsDialog] wsRef.current:', wsRef?.current);
    
    if (!wsRef || !wsRef.current) {
      console.error('[SettingsDialog] WebSocket ref is not available');
      alert('WebSocket is not initialized. Please ensure the connection is established.');
      return;
    }

    const ws = wsRef.current;
    const readyState = ws.readyState;
    console.log('[SettingsDialog] WebSocket readyState:', readyState);
    console.log('[SettingsDialog] WebSocket.OPEN:', WebSocket.OPEN);

    if (readyState !== WebSocket.OPEN) {
      const stateNames = {
        0: 'CONNECTING',
        1: 'OPEN',
        2: 'CLOSING',
        3: 'CLOSED'
      };
      console.error(`[SettingsDialog] WebSocket is not OPEN. Current state: ${readyState} (${stateNames[readyState] || 'UNKNOWN'})`);
      alert(`WebSocket is not connected. Current state: ${stateNames[readyState] || readyState}. Please wait for the connection to be established.`);
      return;
    }

    try {
      // Send data as JSON via websocket - same connection that receives points
      console.log('[SettingsDialog] Sending settings via WebSocket:', dataToSend);
      ws.send(JSON.stringify(dataToSend));
      console.log('[SettingsDialog] Settings sent successfully');
      onSave();
    } catch (error) {
      console.error('[SettingsDialog] Error sending settings via WebSocket:', error);
      alert(`Error sending settings: ${error.message}`);
    }
  };

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div 
        className="bg-radar-surface/95 backdrop-blur-md rounded-2xl border border-radar-grid/50 shadow-2xl w-[90vw] max-w-4xl max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-radar-grid/50 bg-gradient-to-r from-radar-primary/10 to-radar-secondary/10">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-radar-primary to-radar-secondary">
              Settings
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-radar-primary transition-colors p-2 hover:bg-radar-surface/50 rounded-lg"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
          <div className="space-y-6">
            {CLASS_LIST.map((classItem) => {
              const classSettings = settings[classItem.name] || {
                L0_db: '',
                sigma_L0_db: '',
                r0_m: '',
                a_db_per_m: '',
              };

              return (
                <div
                  key={classItem.name}
                  className="bg-radar-surface/50 rounded-lg p-4 border border-radar-grid/30"
                >
                  <h3 className="text-lg font-semibold text-radar-primary mb-4">{classItem.name}</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">L0_db</label>
                      <input
                        type="number"
                        step="any"
                        value={classSettings.L0_db || ''}
                        onChange={(e) => handleInputChange(classItem.name, 'L0_db', e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        className="w-full px-3 py-2 bg-radar-surface/80 border border-radar-grid/50 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-radar-primary/50 focus:border-transparent"
                        placeholder="e.g., 95.0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">sigma_L0_db</label>
                      <input
                        type="number"
                        step="any"
                        value={classSettings.sigma_L0_db || ''}
                        onChange={(e) => handleInputChange(classItem.name, 'sigma_L0_db', e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        className="w-full px-3 py-2 bg-radar-surface/80 border border-radar-grid/50 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-radar-primary/50 focus:border-transparent"
                        placeholder="e.g., 5.0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">r0_m</label>
                      <input
                        type="number"
                        step="any"
                        value={classSettings.r0_m || ''}
                        onChange={(e) => handleInputChange(classItem.name, 'r0_m', e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        className="w-full px-3 py-2 bg-radar-surface/80 border border-radar-grid/50 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-radar-primary/50 focus:border-transparent"
                        placeholder="e.g., 50.0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">a_db_per_m</label>
                      <input
                        type="number"
                        step="any"
                        value={classSettings.a_db_per_m || ''}
                        onChange={(e) => handleInputChange(classItem.name, 'a_db_per_m', e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        className="w-full px-3 py-2 bg-radar-surface/80 border border-radar-grid/50 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-radar-primary/50 focus:border-transparent"
                        placeholder="e.g., 0.001"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-radar-grid/50 bg-radar-surface/50 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-6 py-2.5 bg-radar-surface/80 border border-radar-grid/50 rounded-lg text-gray-300 hover:bg-radar-surface hover:text-white transition-colors font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSet}
            className="px-6 py-2.5 bg-gradient-to-r from-radar-primary to-radar-secondary rounded-lg text-white hover:shadow-lg hover:shadow-radar-primary/50 transition-all font-medium"
          >
            Set
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsDialog;

