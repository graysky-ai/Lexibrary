// Fixture: switch statement with a parameter as the subject.

function dispatch(action: string): number {
    switch (action) {
        case "start":
            return 1;
        case "stop":
            return 0;
        default:
            return -1;
    }
}
