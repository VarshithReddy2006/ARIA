/**
 * TypeScript SDK Error definitions for RIA Platform.
 */

export class RIAClientErrorTS extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RIAClientErrorTS';
  }
}
