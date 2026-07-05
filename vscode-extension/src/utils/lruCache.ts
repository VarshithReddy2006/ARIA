export interface CacheEntry<T> {
  value: T;
  version: number;
}

export class DocumentLruCache<T> {
  private cache = new Map<string, CacheEntry<T>>();
  private keys: string[] = [];

  constructor(private readonly maxSize: number = 50) {}

  public get(uriStr: string): CacheEntry<T> | undefined {
    const entry = this.cache.get(uriStr);
    if (entry) {
      this.touch(uriStr);
    }
    return entry;
  }

  public set(uriStr: string, entry: CacheEntry<T>): void {
    if (this.cache.has(uriStr)) {
      this.cache.set(uriStr, entry);
      this.touch(uriStr);
      return;
    }

    if (this.keys.length >= this.maxSize) {
      const oldestKey = this.keys.shift();
      if (oldestKey) {
        this.cache.delete(oldestKey);
      }
    }

    this.cache.set(uriStr, entry);
    this.keys.push(uriStr);
  }

  public delete(uriStr: string): void {
    this.cache.delete(uriStr);
    const index = this.keys.indexOf(uriStr);
    if (index !== -1) {
      this.keys.splice(index, 1);
    }
  }

  public clear(): void {
    this.cache.clear();
    this.keys = [];
  }

  private touch(key: string): void {
    const index = this.keys.indexOf(key);
    if (index !== -1) {
      this.keys.splice(index, 1);
    }
    this.keys.push(key);
  }
}
