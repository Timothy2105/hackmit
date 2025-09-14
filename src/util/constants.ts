// Regex patterns for extracting scene and object from voice commands
export const START_RECORDING_REGEX = /dexter.*start.*recording.*for.*scene\s+([^for]+).*for.*object\s+(.+)/i;
export const STOP_RECORDING_REGEX = /dexter.*stop.*recording/i;

// Hint commands
export const FIRST_HINT_REGEX = /dexter.*give.*me.*the.*first.*hint/i;
export const SECOND_HINT_REGEX = /dexter.*give.*me.*the.*second.*hint/i;
export const SAY_HI_REGEX = /\bhi\s+dexter\b/;

// Hint responses from environment variables
export const FIRST_HINT_RESPONSE = process.env.FIRST_HINT;
export const SECOND_HINT_RESPONSE = process.env.SECOND_HINT;
