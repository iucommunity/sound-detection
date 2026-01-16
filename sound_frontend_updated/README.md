# Sound Detection Radar - Electron App

A beautiful, modern Electron application for visualizing sound detection with a stunning radar interface.

## Features

- 🎯 **Beautiful Radar Visualization** - Animated expanding circle radar sweep
- 📊 **Real-time Point Tracking** - Visualize sound sources with direction and distance
- 🎨 **Modern UI** - Built with Tailwind CSS and React
- ⚡ **Fast Performance** - Powered by Vite for lightning-fast development
- 🖥️ **Cross-platform** - Works on Windows, macOS, and Linux

## Tech Stack

- **Electron** - Desktop application framework
- **Vite** - Next-generation frontend build tool
- **React** - UI library
- **Tailwind CSS** - Utility-first CSS framework

## Getting Started

### Prerequisites

- Node.js (v18 or higher)
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

### Development

Run the app in development mode:
```bash
npm run electron:dev
```

This will:
- Start the Vite dev server on `http://localhost:5173`
- Launch Electron when the server is ready
- Enable hot module replacement for fast development

### Build

Build the app for production:
```bash
npm run build
```

Build Electron app:
```bash
npm run electron:build
```

## Project Structure

```
sound_frontend/
├── electron/
│   └── main.js          # Electron main process
├── src/
│   ├── components/
│   │   ├── Radar.jsx    # Radar visualization component
│   │   └── ControlPanel.jsx  # Control panel component
│   ├── data/
│   │   └── radarPoints.js    # Radar points data structure
│   ├── App.jsx          # Main app component
│   ├── main.jsx         # React entry point
│   └── index.css        # Global styles
├── index.html           # HTML entry point
├── package.json         # Dependencies and scripts
├── vite.config.js       # Vite configuration
└── tailwind.config.js   # Tailwind CSS configuration
```

## Radar Data Format

Radar points are stored in `src/data/radarPoints.js` with the following structure:

```javascript
{
  id: number,           // Unique identifier
  direction: number,    // Direction in degrees (0-360)
  distance: number,     // Distance from center (0-1)
  intensity: number,    // Signal intensity (0-1)
  timestamp: number     // Timestamp in milliseconds
}
```

## Customization

### Colors

Edit `tailwind.config.js` to customize the color scheme:

```javascript
colors: {
  radar: {
    primary: '#00ff88',    // Primary green
    secondary: '#00d4ff',  // Secondary cyan
    grid: '#1a3a52',       // Grid lines
    background: '#0a1628', // Background
    surface: '#0f1e35',    // Surface elements
  },
}
```

### Radar Animation Speed

Modify the sweep speed in `src/components/Radar.jsx`:

```javascript
sweepProgressRef.current += 0.02; // Increase for faster, decrease for slower
```

## License

MIT

