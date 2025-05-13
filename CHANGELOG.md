# Changelog

## [0.1.1] - Unreleased

### Added
- Added recording control features:
  - `disable_recording()` and `enable_recording()` functions to control monitoring
  - `recording_context` context manager for cleaner control of monitoring
- Example demonstrating recording control in `examples/recording_control_demo.py`

### Changed
- Updated README with documentation on recording control features

## [0.1.0] - Initial Release

### Added
- Core monitoring functionality:
  - Function execution tracking
  - Line-by-line execution recording
  - Object tracking and storage
  - Stack snapshot recording
  - Session management
- Web interface for exploring execution data
- MCP protocol integration
- Reanimation for replaying function executions 