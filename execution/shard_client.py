import logging
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

# Mock database records
MOCK_USERS = [
    {"gid": "user-1", "id": "u1", "name": "Alice", "email": "alice@example.com"},
    {"gid": "user-2", "id": "u2", "name": "Bob", "email": "bob@example.com"},
]

MOCK_POSTS = [
    {"gid": "post-1", "id": "p1", "title": "Hello World", "content": "First post!"},
    {"gid": "post-2", "id": "p2", "title": "Distributed Systems", "content": "Python is great for orchestration."},
]

# User -> Post relations
MOCK_POSTED_RELATIONS = [
    {"u": MOCK_USERS[0], "p": MOCK_POSTS[0]},
    {"u": MOCK_USERS[1], "p": MOCK_POSTS[1]},
]

MOCK_ORDERS = [
    {"gid": "order-1", "id": "o1", "userId": "u1", "amount": 99.99, "product": "Laptop"},
    {"gid": "order-2", "id": "o2", "userId": "u2", "amount": 49.50, "product": "Keyboard"},
    {"gid": "order-3", "id": "o3", "userId": "u1", "amount": 15.00, "product": "Mouse"},
]


class ShardClient:
    def __init__(self, uri: str, user: str, password: str, mock: bool = False):
        self.uri = uri
        self.user = user
        self.password = password
        self.mock = mock
        self.driver = None

        if not self.mock:
            try:
                self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j database at {self.uri}: {e}")

    def execute(self, query: str, database: str = None) -> list[dict]:
        if self.mock:
            return self._execute_mock(query)

        if not self.driver:
            raise ConnectionError(f"No driver connection established for {self.uri}")

        kwargs = {"database": database} if database else {}
        try:
            with self.driver.session(**kwargs) as session:
                result = session.run(query)
                return [record.data() for record in result]
        except Exception as e:
            if "DatabaseNotFound" in str(e):
                logger.warning(f"Database '{database}' not found on {self.uri}, falling back to default db.")
                with self.driver.session() as session:
                    result = session.run(query)
                    return [record.data() for record in result]
            raise

    def _execute_mock(self, query: str) -> list[dict]:
        query_upper = query.upper()
        # Parse query type based on substring matching to simulate Neo4j return values
        
        # 1. MATCH (u:User)-[:POSTED]->(p:Post)
        if "USER" in query_upper and "POST" in query_upper and "POSTED" in query_upper:
            # Return joined node objects
            return [{"u": r["u"], "p": r["p"]} for r in MOCK_POSTED_RELATIONS]

        # 2. MATCH (u:User)
        elif "USER" in query_upper:
            return [{"u": u} for u in MOCK_USERS]

        # 3. MATCH (p:Post)
        elif "POST" in query_upper:
            return [{"p": p} for p in MOCK_POSTS]

        # 4. MATCH (o:Order)
        elif "ORDER" in query_upper:
            return [{"o": o} for o in MOCK_ORDERS]

        # Unknown query for mock
        return []

    def close(self):
        if self.driver:
            self.driver.close()
