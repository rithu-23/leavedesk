import { Observable } from 'rxjs';

/**
 * Wraps the browser's EventSource (Server-Sent Events) in an RxJS Observable.
 * - Each SSE message of type `eventName` is parsed as JSON and emitted.
 * - Unsubscribing closes the connection, so the stream never outlives its subscriber.
 * - EventSource reconnects by itself after a dropped connection; if the browser gives up
 *   (readyState CLOSED, e.g. the server answered 401), the Observable errors so the caller
 *   can decide whether to retry.
 * Keep-alive comments from the server (": keep-alive") are ignored by EventSource itself.
 */
export function fromEventSource<T>(url: string, eventName: string): Observable<T> {
  return new Observable<T>((subscriber) => {
    const source = new EventSource(url);

    const onEvent = (event: Event) => {
      try {
        subscriber.next(JSON.parse((event as MessageEvent<string>).data) as T);
      } catch {
        // A malformed message is skipped; it must not break the stream.
      }
    };
    source.addEventListener(eventName, onEvent);
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        subscriber.error(new Error('Notification stream closed'));
      }
    };

    return () => {
      source.removeEventListener(eventName, onEvent);
      source.close();
    };
  });
}
