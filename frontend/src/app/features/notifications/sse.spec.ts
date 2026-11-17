import { FakeEventSource } from '../../testing/fake-event-source';
import { fromEventSource } from './sse';

describe('fromEventSource', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('emits parsed JSON for the named event and skips malformed data', () => {
    const received: unknown[] = [];
    const sub = fromEventSource<{ id: string }>('/api/x', 'notification').subscribe((v) =>
      received.push(v),
    );
    const source = FakeEventSource.instances[0];
    expect(source.url).toBe('/api/x');

    source.emit('notification', { id: 'N-1' });
    source.emit('other', { id: 'ignored' });
    source.addEventListener('notification', () => undefined);
    sub.unsubscribe();

    expect(received).toEqual([{ id: 'N-1' }]);
  });

  it('closes the connection when unsubscribed', () => {
    const sub = fromEventSource('/api/x', 'notification').subscribe();
    sub.unsubscribe();
    expect(FakeEventSource.instances[0].readyState).toBe(FakeEventSource.CLOSED);
  });
});
