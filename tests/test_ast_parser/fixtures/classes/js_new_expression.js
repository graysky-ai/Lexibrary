// JavaScript instantiation fixture.
// Expect two instantiates edges (A, B).

class A {}
class B {}

function main() {
  const a = new A();
  const b = new B();
  return [a, b];
}
