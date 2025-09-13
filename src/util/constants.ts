// Regex patterns for extracting scene and object from voice commands
export const START_RECORDING_REGEX = /dexter.*start.*recording.*for.*scene\s+([^for]+).*for.*object\s+(.+)/i;
export const STOP_RECORDING_REGEX = /dexter.*stop.*recording/i;
