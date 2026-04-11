// TypeScript extends/implements fixture.
// Expect two inherits edges (Animal, Walker).

interface Walker {
  walk(): void;
}

class Animal {}

class Dog extends Animal implements Walker {
  walk(): void {}
}
