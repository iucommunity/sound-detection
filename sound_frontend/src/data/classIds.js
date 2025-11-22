// Class ID mapping for settings
// Maps class names to their IDs (used in backend)
export const CLASS_IDS = {
  'Human voice': '/m/09l8g',
  'Locomotion': '/m/0jbk', // Generic locomotion ID
  'Vehicle': '/m/07yv9',
  'Car': '/m/0k4j', // Car ID
  'Truck': '/m/07jdr', // Truck ID
  'Aircraft': '/m/0fly', // Aircraft ID
  'Helicopter': '/m/0h8x', // Helicopter ID
  'Gunshot': '/m/0jbk', // Gunshot ID (may need adjustment)
};

// Get class ID for a class name
export const getClassId = (className) => {
  return CLASS_IDS[className] || null;
};

// Get class name from class ID (reverse lookup)
export const getClassNameFromId = (classId) => {
  for (const [className, id] of Object.entries(CLASS_IDS)) {
    if (id === classId) {
      return className;
    }
  }
  return null;
};

