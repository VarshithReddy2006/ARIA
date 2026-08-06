import { ConfigurationManager } from './configuration';

/**
 * Telemetry Service tracking command execution metrics, selection sync, and latencies.
 */
export class TelemetryService {
  private static instance: TelemetryService;
  private metrics: Record<string, number> = {};

  public static getInstance(): TelemetryService {
    if (!TelemetryService.instance) {
      TelemetryService.instance = new TelemetryService();
    }
    return TelemetryService.instance;
  }

  public trackCommand(commandId: string, durationMs: number): void {
    if (!ConfigurationManager.telemetry) return;
    this.metrics[commandId] = durationMs;
  }

  public trackEvent(eventName: string, properties?: Record<string, any>): void {
    if (!ConfigurationManager.telemetry) return;
    // Log telemetry event for performance diagnostics
  }
}
