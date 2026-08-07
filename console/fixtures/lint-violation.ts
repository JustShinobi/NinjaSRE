// Two rules at once: a floating promise, and an origin outside the deployment.
// Both are errors the console's lint configuration declares, and both are
// invisible to the type checker.
export function reach(): void {
  fetch('https://fonts.example.com/inter.woff2');
}
