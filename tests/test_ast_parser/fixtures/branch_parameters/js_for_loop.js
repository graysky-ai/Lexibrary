// Fixture: for loop with a parameter in the condition.

function processItems(items, limit) {
    const results = [];
    for (let i = 0; i < limit; i++) {
        results.push(items[i]);
    }
    return results;
}
