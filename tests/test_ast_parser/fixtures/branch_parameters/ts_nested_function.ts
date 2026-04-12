// Fixture: nested function declarations inside a function body.
// The inner function should be emitted as a separate symbol with its own branch_parameters.

function outer(data: string): string {
    function inner(flag: boolean): string {
        if (flag) {
            return data.toUpperCase();
        }
        return data;
    }
    return inner(true);
}
