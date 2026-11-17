import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/** Root component: only hosts the router. Layout lives in layout/shell. */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class App {}
