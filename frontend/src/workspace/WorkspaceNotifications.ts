export class WorkspaceNotifications {
  public notify(message: string, type: 'info' | 'success' | 'warn' = 'info'): void {
    console.log(`[WorkspaceNotification - ${type.toUpperCase()}] ${message}`);
  }
}
