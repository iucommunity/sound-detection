/**
 * Radar points data structure
 * Each point represents a detected sound source with direction and distance
 */

export const radarPoints = [
  { id: 1, direction: 45, distance: 0.3, intensity: 0.8, timestamp: Date.now() },
  { id: 2, direction: 120, distance: 0.5, intensity: 0.6, timestamp: Date.now() },
  { id: 3, direction: 200, distance: 0.7, intensity: 0.9, timestamp: Date.now() },
  { id: 4, direction: 280, distance: 0.4, intensity: 0.7, timestamp: Date.now() },
  { id: 5, direction: 15, distance: 0.6, intensity: 0.5, timestamp: Date.now() },
  { id: 6, direction: 90, distance: 0.8, intensity: 0.85, timestamp: Date.now() },
  { id: 7, direction: 180, distance: 0.5, intensity: 0.75, timestamp: Date.now() },
  { id: 8, direction: 270, distance: 0.3, intensity: 0.65, timestamp: Date.now() },
];

/**
 * Convert polar coordinates (direction, distance) to Cartesian (x, y)
 * @param {number} direction - Direction in degrees (0-360)
 * @param {number} distance - Distance from center (0-1)
 * @param {number} radius - Maximum radius of the radar
 * @returns {Object} {x, y} coordinates
 */
export function polarToCartesian(direction, distance, radius) {
  const angle = (direction * Math.PI) / 180;
  const r = distance * radius;
  return {
    x: r * Math.cos(angle),
    y: r * Math.sin(angle),
  };
}

/**
 * Generate random radar points for simulation
 * @param {number} count - Number of points to generate
 * @returns {Array} Array of radar points
 */
export function generateRandomPoints(count = 5) {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    direction: Math.random() * 360,
    distance: 0.2 + Math.random() * 0.6,
    intensity: 0.4 + Math.random() * 0.6,
    timestamp: Date.now(),
  }));
}

