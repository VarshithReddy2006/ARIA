type EventCallback = (data: any) => void;

export class WorkspaceEvents {
  private listeners: Map<string, Set<EventCallback>> = new Map();

  public on(event: string, callback: EventCallback): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  public off(event: string, callback: EventCallback): void {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.delete(callback);
    }
  }

  public emit(event: string, data?: any): void {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.forEach((cb) => cb(data));
    }
  }
}
