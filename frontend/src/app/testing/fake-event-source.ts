/**
 * Stand-in for the browser's EventSource in tests (jsdom has none). Tests install it with
 * vi.stubGlobal('EventSource', FakeEventSource), then push events with emit().
 */
export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.OPEN;
  onerror: (() => void) | null = null;
  private readonly listeners = new Map<string, Set<(event: Event) => void>>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  /** The newest connection that hasn't been closed. */
  static open(): FakeEventSource[] {
    return FakeEventSource.instances.filter((s) => s.readyState !== FakeEventSource.CLOSED);
  }

  addEventListener(type: string, listener: (event: Event) => void): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: (event: Event) => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED;
  }

  /** Simulates the server sending `event: <type>` with JSON data. */
  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}
