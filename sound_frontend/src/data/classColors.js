// ⚠️ SINGLE SOURCE OF TRUTH FOR ALL CLASS COLORS ⚠️
// Change colors here and they will update everywhere:
// - Radar points
// - Radar legend
// - Points history
// All components use getClassColor() which reads from this object
export const CLASS_COLORS = {
  'Human': '#9333ea', // Purple color for Human (distinct from Aircraft cyan)
  'Human voice': '#9333ea', // Same as Human - backend sends this
  'Locomotion': '#8c564b',
  'Vehicle': '#e377c2',
  'Car': '#7f7f7f',
  'Truck': '#bcbd22',
  'Aircraft': '#17becf', // Cyan color
  'Helicopter': '#aec7e8',
  'Gunshot': '#ff9896',
  'Unknown': '#00d9ff', // Default color (cyan/turquoise)
  'unknown': '#00d9ff', // Fallback for lowercase
};

// Get color for a class label
// This is the SINGLE SOURCE OF TRUTH for all colors - used by radar, history, and legend
export const getClassColor = (classLabel) => {
  if (!classLabel) {
    return CLASS_COLORS.Unknown;
  }
  
  // Try exact match first (handles multi-word labels like "Human voice")
  if (CLASS_COLORS[classLabel]) {
    return CLASS_COLORS[classLabel];
  }
  
  // Normalize: capitalize first letter, lowercase rest (e.g., "human" -> "Human", "HUMAN" -> "Human")
  const normalizedLabel = classLabel.charAt(0).toUpperCase() + classLabel.slice(1).toLowerCase();
  
  // Direct lookup with normalized label (this should work for all cases)
  const color = CLASS_COLORS[normalizedLabel];
  
  // If found, return it. Otherwise try other variations, then default
  if (color) return color;
  
  // Fallback strategies (shouldn't be needed if normalization works)
  return CLASS_COLORS[classLabel.toLowerCase()] || 
         CLASS_COLORS[classLabel.toUpperCase()] ||
         CLASS_COLORS.Unknown;
};

// Class list for legend display
// Note: The 'color' property here is for reference only - the legend uses getClassColor() directly
// This ensures colors are always up-to-date even if CLASS_COLORS changes
export const CLASS_LIST = [
  { name: 'Human voice' }, // Backend sends "Human voice" not just "Human"
  { name: 'Locomotion' },
  { name: 'Vehicle' },
  { name: 'Car' },
  { name: 'Truck' },
  { name: 'Aircraft' },
  { name: 'Helicopter' },
  { name: 'Gunshot' },
];

