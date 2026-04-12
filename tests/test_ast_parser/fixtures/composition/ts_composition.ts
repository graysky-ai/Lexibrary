// Fixture: TypeScript class field composition annotations.

class Logger {
  level: string;
}

class Database {
  connectionString: string;
}

class Cache {
  ttl: number;
}

class Service {
  db: Database;
  cache: Cache;
  name: string;
  count: number;
  logger: Logger;
  items: Array<Cache>;
}
