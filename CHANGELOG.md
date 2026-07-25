# Changelog

## [Unreleased] - 2026-07-25

### Added
- **LAC Downloader**: New tool that takes a pasted Library and Archives Canada / Heritage Canadiana URL and
  batch-downloads all high-resolution page images for that microfilm roll, organized into their own folder.
- **License**: The project is now licensed under the PolyForm Noncommercial License 1.0.0, free to use and
  modify for any noncommercial purpose, not for building or selling a commercial product or service.
- **Prompt Template selection**: The Register Transcriber tab now has a dropdown to pick which transcription
  prompt to use for a given register, and supports adding your own custom prompt templates.

### Changed
- **Settings now save per tool**: Global settings (API key, base folders, etc.) still save to the main
  settings file, but each tool's own settings now save inside that tool's own folder, so every tool stays
  fully self-contained.
