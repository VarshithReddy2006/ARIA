import * as vscode from 'vscode';

export class OutputChannelService {
  private static channels = new Map<string, vscode.OutputChannel>();

  public static getChannel(name: string): vscode.OutputChannel {
    let channel = this.channels.get(name);
    if (!channel) {
      channel = vscode.window.createOutputChannel(`Repo Intelligence — ${name}`);
      this.channels.set(name, channel);
    }
    return channel;
  }

  public static showAndClear(name: string): vscode.OutputChannel {
    const channel = this.getChannel(name);
    channel.clear();
    channel.show(true);
    return channel;
  }

  public static dispose(): void {
    for (const channel of this.channels.values()) {
      channel.dispose();
    }
    this.channels.clear();
  }
}
