import React, { useState, useEffect, useRef } from 'react';
import { CLASS_LIST } from '../data/classColors';
import { getClassId, getClassNameFromId } from '../data/classIds';

const SettingsDialog = ({ isOpen, onClose, onSave, sendSettingsData, isConnected, distanceParams, showNotification }) => {
  const [settings, setSettings] = useState({});
  const hasInitializedRef = useRef(false); // Track if we've initialized from distanceParams

  // Debug: Log when dialog opens
  useEffect(() => {
    if (isOpen) {
      console.log('[SettingsDialog] ========== Dialog opened ==========');
      console.log('[SettingsDialog] sendSettingsData function:', typeof sendSettingsData);
      console.log('[SettingsDialog] isConnected prop:', isConnected);
      console.log('[SettingsDialog] distanceParams:', distanceParams);
      console.log('[SettingsDialog] ====================================');
    }
  }, [isOpen, sendSettingsData, isConnected, distanceParams]);

  // Initialize settings state from distanceParams when dialog opens
  // Only initialize if settings are empty (preserve user changes)
  useEffect(() => {
    if (isOpen) {
      // If settings already exist (user has made changes), preserve them
      if (Object.keys(settings).length > 0) {
        console.log('[SettingsDialog] Settings already exist, preserving user changes');
        return;
      }
      
      // If distanceParams exist, use them as initial values
      if (distanceParams) {
        console.log('[SettingsDialog] Initializing settings from distanceParams:', distanceParams);
        const initialSettings = {};
        
        CLASS_LIST.forEach((classItem) => {
          const classId = getClassId(classItem.name);
          
          // Check if we have distance params for this class
          if (classId && distanceParams[classId]) {
            // Use received distance params as initial values
            const params = distanceParams[classId];
            initialSettings[classItem.name] = {
              L0_db: params.L0_db !== undefined && params.L0_db !== null ? String(params.L0_db) : '',
              sigma_L0_db: params.sigma_L0_db !== undefined && params.sigma_L0_db !== null ? String(params.sigma_L0_db) : '',
              r0_m: params.r0_m !== undefined && params.r0_m !== null ? String(params.r0_m) : '',
              a_db_per_m: params.a_db_per_m !== undefined && params.a_db_per_m !== null ? String(params.a_db_per_m) : '',
            };
            console.log(`[SettingsDialog] ✓ Initialized ${classItem.name} (${classId}):`, initialSettings[classItem.name]);
          } else {
            // Use empty values if no distance params available
            initialSettings[classItem.name] = {
              L0_db: '',
              sigma_L0_db: '',
              r0_m: '',
              a_db_per_m: '',
            };
          }
        });
        
        setSettings(initialSettings);
        hasInitializedRef.current = true; // Mark as initialized
        console.log('[SettingsDialog] Settings initialized from distanceParams:', initialSettings);
      } else {
        // If no distanceParams and settings are empty, initialize with empty values
        console.log('[SettingsDialog] No distanceParams, initializing with empty values');
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
    }
  }, [isOpen, distanceParams]); // Re-initialize when dialog opens or distanceParams change

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

  const handleSet = async (e) => {
    // Prevent any default behavior and event bubbling
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    console.log('[SettingsDialog] ========== Set button clicked ==========');
    
    // Build the data object with only classes that have all 4 fields filled
    const dataToSend = {};
    let hasValidData = false;

    CLASS_LIST.forEach((classItem) => {
      const classSettings = settings[classItem.name];
      if (
        classSettings &&
        classSettings.L0_db !== '' &&
        classSettings.L0_db !== null &&
        classSettings.sigma_L0_db !== '' &&
        classSettings.sigma_L0_db !== null &&
        classSettings.r0_m !== '' &&
        classSettings.r0_m !== null &&
        classSettings.a_db_per_m !== '' &&
        classSettings.a_db_per_m !== null
      ) {
        const classId = getClassId(classItem.name);
        if (classId) {
          // Parse and validate values
          const L0_db = parseFloat(classSettings.L0_db);
          const sigma_L0_db = parseFloat(classSettings.sigma_L0_db);
          const r0_m = parseFloat(classSettings.r0_m);
          const a_db_per_m = parseFloat(classSettings.a_db_per_m);
          
          // Check if values are valid numbers
          if (!isNaN(L0_db) && !isNaN(sigma_L0_db) && !isNaN(r0_m) && !isNaN(a_db_per_m)) {
            dataToSend[classId] = {
              L0_db: L0_db,
              sigma_L0_db: sigma_L0_db,
              r0_m: r0_m,
              a_db_per_m: a_db_per_m,
            };
            hasValidData = true;
            console.log(`[SettingsDialog] ✓ Added ${classItem.name} (${classId}):`, dataToSend[classId]);
          } else {
            console.warn(`[SettingsDialog] ⚠ Invalid numbers for ${classItem.name}, skipping`);
          }
        } else {
          console.warn(`[SettingsDialog] ⚠ No class ID found for ${classItem.name}, skipping`);
        }
      }
    });

    if (!hasValidData) {
      if (showNotification) {
        showNotification('Please fill all 4 fields with valid numbers for at least one class.', 'warning');
      } else {
        alert('Please fill all 4 fields with valid numbers for at least one class.');
      }
      return;
    }

    // Check if sendSettingsData function is available
    if (!sendSettingsData || typeof sendSettingsData !== 'function') {
      console.error('[SettingsDialog] ✗ sendSettingsData function is not available');
      if (showNotification) {
        showNotification('WebSocket send function is not available. Please check the connection.', 'error');
      } else {
        alert('WebSocket send function is not available. Please check the connection.');
      }
      return;
    }

    console.log('[SettingsDialog] Data to send:', dataToSend);
    console.log('[SettingsDialog] Calling sendSettingsData...');
    
    // Close dialog immediately when Set is pressed
    onSave();
    
    // Send asynchronously and show notification
    sendSettingsData(dataToSend)
      .then((success) => {
        if (success) {
          console.log('[SettingsDialog] ✓ Settings sent successfully');
          if (showNotification) {
            showNotification('Settings saved successfully!', 'success');
          }
        } else {
          console.error('[SettingsDialog] ✗ Failed to send settings after all retries');
          console.error('[SettingsDialog] Check console above for WebSocket state details');
          if (showNotification) {
            showNotification('Failed to send settings. The WebSocket may not be connected. Please check the browser console for details.', 'error');
          }
        }
      })
      .catch((error) => {
        console.error('[SettingsDialog] ✗ Exception in send promise:', error);
        console.error('[SettingsDialog] Error details:', error.message, error.stack);
        if (showNotification) {
          showNotification(`Error sending settings: ${error.message}. Please check the console for details.`, 'error');
        }
      });
    
    console.log('[SettingsDialog] ======================================');
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
                        onChange={(e) => {
                          e.stopPropagation();
                          handleInputChange(classItem.name, 'L0_db', e.target.value);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        onMouseDown={(e) => e.stopPropagation()}
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
                        onChange={(e) => {
                          e.stopPropagation();
                          handleInputChange(classItem.name, 'sigma_L0_db', e.target.value);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        onMouseDown={(e) => e.stopPropagation()}
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
                        onChange={(e) => {
                          e.stopPropagation();
                          handleInputChange(classItem.name, 'r0_m', e.target.value);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        onMouseDown={(e) => e.stopPropagation()}
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
                        onChange={(e) => {
                          e.stopPropagation();
                          handleInputChange(classItem.name, 'a_db_per_m', e.target.value);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        onFocus={(e) => e.stopPropagation()}
                        onMouseDown={(e) => e.stopPropagation()}
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
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleSet(e);
            }}
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

