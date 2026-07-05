import * as vscode from 'vscode';

export enum LogLevel {
  Trace = 0,
  Debug = 1,
  Info = 2,
  Warn = 3,
  Error = 4,
}

export class Logger {
  private static channel: vscode.OutputChannel | undefined;
  private static cachedLevel: LogLevel = LogLevel.Info;

  public static initialize(): void {
    if (!this.channel) {
      this.channel = vscode.window.createOutputChannel('Repo Intelligence Log');
    }
    this.updateLogLevel();
  }

  public static updateLogLevel(): void {
    const configLevel = vscode.workspace
      .getConfiguration('repoIntelligence')
      .get<string>('logLevel', 'info')
      .toLowerCase();

    switch (configLevel) {
      case 'trace':
        this.cachedLevel = LogLevel.Trace;
        break;
      case 'debug':
        this.cachedLevel = LogLevel.Debug;
        break;
      case 'info':
        this.cachedLevel = LogLevel.Info;
        break;
      case 'warn':
        this.cachedLevel = LogLevel.Warn;
        break;
      case 'error':
        this.cachedLevel = LogLevel.Error;
        break;
      default:
        this.cachedLevel = LogLevel.Info;
    }
  }

  private static log(level: LogLevel, levelStr: string, message: string, error?: any): void {
    if (level < this.cachedLevel) {
      return;
    }
    const timestamp = new Date().toISOString();
    const errorSuffix = error ? ` | Error: ${error.message || error}` : '';
    const line = `[${timestamp}] [${levelStr}] ${message}${errorSuffix}`;
    if (this.channel) {
      this.channel.appendLine(line);
    }
    // Copy to console for debugging/development
    if (levelStr === 'ERROR') {
      console.error(line);
    } else if (levelStr === 'WARN') {
      console.warn(line);
    } else {
      console.log(line);
    }
  }

  public static trace(message: string): void {
    this.log(LogLevel.Trace, 'TRACE', message);
  }

  public static debug(message: string): void {
    this.log(LogLevel.Debug, 'DEBUG', message);
  }

  public static info(message: string): void {
    this.log(LogLevel.Info, 'INFO', message);
  }

  public static warn(message: string): void {
    this.log(LogLevel.Warn, 'WARN', message);
  }

  public static error(message: string, error?: any): void {
    this.log(LogLevel.Error, 'ERROR', message, error);
  }

  public static dispose(): void {
    if (this.channel) {
      this.channel.dispose();
      this.channel = undefined;
    }
  }
}
