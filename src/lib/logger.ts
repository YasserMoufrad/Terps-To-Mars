// Small structured logger for the browser app (CLAUDE.md section 16).
// Every event is one JSON-friendly object: UTC timestamp, level, the run_id shared
// by every event in this page load, a stage (which part of the app) and an event name.
// It has no dependencies, so it can also be loaded by the Node test runner.

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEvent {
  ts: string;
  level: LogLevel;
  run_id: string;
  stage: string;
  event: string;
  [field: string]: unknown;
}

export type LogSink = (entry: LogEvent) => void;

export interface Logger {
  readonly runId: string;
  debug(stage: string, event: string, fields?: Record<string, unknown>): void;
  info(stage: string, event: string, fields?: Record<string, unknown>): void;
  warn(stage: string, event: string, fields?: Record<string, unknown>): void;
  error(stage: string, event: string, fields?: Record<string, unknown>): void;
}

export interface LoggerOptions {
  runId?: string;
  debug?: boolean; // DEBUG events are dropped unless this is true
  sink?: LogSink;
}

// Field names that must never reach a log, whatever their value.
const SECRET_KEY = /(token|secret|password|passwd|api[-_]?key|authorization|cookie)/i;

function newRunId(): string {
  // Purpose: one random ID per page load, shared by every event it emits.
  // Uses crypto.randomUUID when available, otherwise a time + random fallback.
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function redact(fields: Record<string, unknown>): Record<string, unknown> {
  // Purpose: copy `fields`, replacing the value of any secret-looking key
  // (matched by SECRET_KEY) with "[redacted]".
  const clean: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(fields)) {
    clean[key] = SECRET_KEY.test(key) ? '[redacted]' : value;
  }
  return clean;
}

const consoleSink: LogSink = (entry) => {
  // Purpose: default sink; writes to the browser console at the event's level
  // so DevTools level filters work.
  const method = entry.level === 'debug' ? 'debug' : entry.level;
  console[method](`[${entry.stage}] ${entry.event}`, entry);
};

export function createLogger(options: LoggerOptions = {}): Logger {
  // Purpose: build a logger. options.runId fixes the correlation ID (tests),
  // options.debug enables DEBUG events, options.sink replaces the console.
  const runId = options.runId ?? newRunId();
  const sink = options.sink ?? consoleSink;
  const debugEnabled = options.debug ?? false;

  const emit = (level: LogLevel, stage: string, event: string, fields: Record<string, unknown> = {}) => {
    // Purpose: send one event to the sink. `stage` names the app area ("data",
    // "ui", "safety"); `event` names what happened; `fields` adds context.
    if (level === 'debug' && !debugEnabled) return;
    try {
      // Standard fields go last so a caller can never overwrite ts, level, run_id or stage.
      sink({ ...redact(fields), ts: new Date().toISOString(), level, run_id: runId, stage, event });
    } catch {
      // A broken log sink must never break the app or change what it shows.
    }
  };

  const at = (level: LogLevel) => (stage: string, event: string, fields?: Record<string, unknown>) => {
    // Purpose: the public method for one `level`; forwards to emit.
    emit(level, stage, event, fields);
  };

  return { runId, debug: at('debug'), info: at('info'), warn: at('warn'), error: at('error') };
}

// A logger that discards everything; the default where logging is optional.
export const silentLogger: Logger = createLogger({ runId: 'silent', sink: () => {} });
