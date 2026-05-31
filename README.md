# Distributed Neo4j Query Coordinator

This project implements a distributed coordinator for Neo4j databases, enabling you to treat multiple distinct physical databases (shards) as a single, cohesive distributed database cluster.

The core of the architecture lies in its ability to parse standard Cypher queries, interact with metadata configuration files, and dynamically route or broadcast operations depending on whether the data is vertically or horizontally partitioned.

## How Query Routing Works

When a query is submitted to the coordinator, it goes through a multi-stage compilation process:

1. **Cypher Parsing & AST Generation:** The query is parsed into an Abstract Syntax Tree (AST) using a custom grammar.
2. **Logical Planning:** The AST is evaluated to identify variables (nodes) and relationships. The planner checks the system's catalog (`tables.config` and `relations.config`) to validate that the requested labels exist in the current database context.
3. **Physical Planning & Distribution:** The physical planner calculates exactly *how* the query should be executed across the distributed shards.

This system supports two primary distribution strategies: **Horizontal Splitting** and **Vertical Splitting**.

---

### Horizontal Splitting (The `NeoMesh` Virtual Database)

Horizontal splitting occurs when the *same type of data* (e.g., `User` nodes) is distributed across multiple databases.

To trigger horizontal splitting logic, you operate under the **NeoMesh** virtual database context (`USE NeoMesh`).

**How it works:**
1. **Catalog Intersection:** When a query arrives (e.g., `MATCH (u:User) RETURN u`), the physical planner extracts all variables (`u -> User`) and relationships.
2. **Database Lookup:** It queries the metadata manager to find all databases that host the `User` label. If `User` is configured in `tables.config` as `User = myNewDatabase, social_db`, the planner determines the data is horizontally split.
3. **Broadcast Plan Generation:** The physical planner creates a `RemoteScan` node for *each* identified database.
4. **Union Operator:** It wraps these multiple `RemoteScan` operations inside a **`Union`** physical operator.
5. **Concurrent Execution:** The execution engine receives the `Union` tree, fires the exact same query concurrently to both `myNewDatabase` and `social_db`, aggregates the rows from both endpoints, and returns the unified dataset.

---

### Vertical Splitting (Cross-Shard Joins)

Vertical splitting occurs when *different types of data* (e.g., `User` nodes and `Order` nodes) are stored in completely distinct, mutually exclusive databases.

**How it works:**
1. **Catalog Validation:** When a query arrives (e.g., `MATCH (u:User)-[:PLACED]->(o:Order)`), the physical planner analyzes the variables.
2. **Database Disjointness:** It discovers that `User` exists purely on `social_db` (which might be on Shard 1), while `Order` exists purely on `commerce_db` (which might be on Shard 2, or even the *same* physical Shard 1).
3. **Fragmented Execution Trees:** Because the entities do not overlap on a single logical database, the query cannot be pushed down as a single query string. The planner breaks the query into localized fragments:
   - Fragment A: `MATCH (u:User) RETURN u` routed to `social_db`.
   - Fragment B: `MATCH (o:Order) RETURN o` routed to `commerce_db`.
4. **HashJoin Operator:** The planner constructs an in-memory **`HashJoin`** physical operator.
5. **Memory Aggregation:** The execution engine executes the fragments concurrently against their respective databases (regardless of which physical shard hosts them), pulls the raw objects back to the central coordinator node, and performs an in-memory Hash Join to stitch the related entities together before returning the finalized result set.

---

## Configuration Setup

The cluster topology is driven by three primary configuration files located in the `configs/` directory:

*   **`shard.config`**: Maps logical databases to physical server URIs and credentials.
*   **`db.config`**: Maps logical database names to the physical shards.
*   **`tables.config` / `relations.config`**: Maintains the global schema, mapping node labels and relationship types to their respective databases. (This supports comma-separated values for horizontal splitting).
