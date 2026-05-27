from distributed_neo4j.metadata.shard_manager import MetadataManager
from distributed_neo4j.parser.ast import PropertyAccess, Variable
from .logical_planner import LogicalPlan, LogicalCreateDatabase
from .operators import PlanNode, RemoteScan, HashJoin, Projection, Limit, Union

class PhysicalPlanner:
    def __init__(self, metadata_mgr: MetadataManager):
        self.metadata_mgr = metadata_mgr

    def plan(self, logical_plan, original_query: str) -> PlanNode:
        if isinstance(logical_plan, LogicalCreateDatabase):
            query = f"CREATE DATABASE {logical_plan.db_name}"
            return RemoteScan(logical_plan.shard_name, query)

        # ── NeoMesh Virtual DB: Distributed Query Planning ──
        if self.metadata_mgr.current_db == "NeoMesh":
            return self._plan_neomesh(logical_plan, original_query)

        # ── Non-NeoMesh: route the full query to the current DB's shard ──
        target_db = self.metadata_mgr.current_db
        shard = self.metadata_mgr.shard_manager.get_shard_for_db(target_db) if target_db else "shard_1"
        if not shard:
            shard = "shard_1"
        return RemoteScan(shard, original_query, database=target_db)

    # ─────────────────────────────────────────────────────────────
    #  NeoMesh Distributed Planning
    # ─────────────────────────────────────────────────────────────
    def _plan_neomesh(self, logical_plan, original_query: str) -> PlanNode:
        """
        Decides between Horizontal (Union) and Vertical (HashJoin)
        fragmentation based on which *databases* the query's variables
        belong to.
        """
        # Step 1: Build  var -> set[database]  mapping
        var_dbs = {}
        for var, label in logical_plan.variables.items():
            if label is None:
                continue
            dbs = self.metadata_mgr.schema_manager.get_dbs_for_label(label)
            if not dbs:
                # Could be a relationship variable (e.g., r -> FOLLOWS)
                dbs = self.metadata_mgr.schema_manager.get_dbs_for_relationship(label)
            var_dbs[var] = set(dbs) if dbs else set()

        # Step 2: Compute the intersection of all variable DB sets
        all_db_sets = [dbs for dbs in var_dbs.values() if dbs]

        if not all_db_sets:
            # No labeled variables (e.g., MATCH (n) DETACH DELETE n)
            # Broadcast to every known database
            all_dbs = set(self.metadata_mgr.db_to_shard.keys())
            if len(all_dbs) > 1:
                return self._plan_horizontal(all_dbs, original_query)
            elif all_dbs:
                db = list(all_dbs)[0]
                shard = self.metadata_mgr.shard_manager.get_shard_for_db(db) or "shard_1"
                return RemoteScan(shard, original_query, database=db)
            else:
                return RemoteScan("shard_1", original_query)

        common_dbs = all_db_sets[0].copy()
        for s in all_db_sets[1:]:
            common_dbs = common_dbs.intersection(s)

        # Also factor in relationship types
        for rel in logical_plan.relationships:
            rel_dbs = set(self.metadata_mgr.schema_manager.get_dbs_for_relationship(rel["type"]))
            if rel_dbs:
                common_dbs = common_dbs.intersection(rel_dbs)

        # Step 3: Route based on the intersection result
        if len(common_dbs) > 1:
            # ═══ HORIZONTAL FRAGMENTATION ═══
            # All variables exist in the same multiple DBs → broadcast + Union
            return self._plan_horizontal(common_dbs, original_query)

        elif len(common_dbs) == 1:
            # Single common DB → route directly
            db = list(common_dbs)[0]
            shard = self.metadata_mgr.shard_manager.get_shard_for_db(db) or "shard_1"
            return RemoteScan(shard, original_query, database=db)

        else:
            # ═══ VERTICAL FRAGMENTATION ═══
            # Intersection is empty: variables live in different DBs
            # → split query per database, execute fragments, HashJoin results
            return self._plan_vertical(logical_plan, original_query, var_dbs)

    # ─────────────────────────────────────────────────────────────
    #  Horizontal Fragmentation  (Union)
    # ─────────────────────────────────────────────────────────────
    def _plan_horizontal(self, dbs: set, original_query: str) -> PlanNode:
        """Broadcast the *same* query to every database, Union the results."""
        scans = []
        for db in sorted(list(dbs)):
            shard = self.metadata_mgr.shard_manager.get_shard_for_db(db)
            if shard:
                scans.append(RemoteScan(shard, original_query, database=db))
        if len(scans) == 1:
            return scans[0]
        return Union(scans)

    # ─────────────────────────────────────────────────────────────
    #  Vertical Fragmentation  (HashJoin)
    # ─────────────────────────────────────────────────────────────
    def _plan_vertical(self, logical_plan, original_query: str, var_dbs: dict) -> PlanNode:
        """
        Variables live in *different* databases.
        Split the query into per-database sub-queries, execute each
        against its own database, then HashJoin the results in memory.
        """
        # ── Group variables by their primary database ──
        var_to_db = {}   # var -> db_name
        db_vars  = {}    # db_name -> {var: label}
        for var, dbs in var_dbs.items():
            if not dbs:
                continue
            primary_db = sorted(list(dbs))[0]
            var_to_db[var] = primary_db
            if primary_db not in db_vars:
                db_vars[primary_db] = {}
            db_vars[primary_db][var] = logical_plan.variables[var]

        db_names = sorted(db_vars.keys())

        if len(db_names) < 2:
            # Fallback: shouldn't happen if intersection was truly empty
            db = db_names[0] if db_names else "shard_1"
            shard = self.metadata_mgr.shard_manager.get_shard_for_db(db) or "shard_1"
            return RemoteScan(shard, original_query, database=db)

        if len(db_names) > 2:
            raise NotImplementedError(
                "Multi-way cross-database joins (>2 databases) not yet supported"
            )

        # ── Find the join condition from WHERE filters ──
        if not logical_plan.filters:
            raise NotImplementedError(
                "Cross-database vertical joins require a WHERE filter "
                "(e.g. WHERE a.id = b.userId)"
            )

        join_cond = logical_plan.filters[0]
        left_expr = join_cond.left
        right_expr = join_cond.right

        if not isinstance(left_expr, PropertyAccess) or not isinstance(right_expr, PropertyAccess):
            raise NotImplementedError(
                "Cross-database join must be on property access equality "
                "(e.g. u.id = o.userId)"
            )

        left_var = left_expr.variable
        right_var = right_expr.variable
        left_db = var_to_db.get(left_var)
        right_db = var_to_db.get(right_var)

        if left_db == right_db:
            # Both join keys in the same DB → treat as single-DB
            shard = self.metadata_mgr.shard_manager.get_shard_for_db(left_db) or "shard_1"
            return RemoteScan(shard, original_query, database=left_db)

        # ── Split relationships by database ──
        db_rels = {db: [] for db in db_names}
        for rel in logical_plan.relationships:
            start_db = var_to_db.get(rel["start"])
            if start_db and start_db in db_rels:
                db_rels[start_db].append(rel)

        # ── Determine which variables each database must return ──
        def get_required_vars(db_name):
            req = set()
            # Join keys
            if left_db == db_name:
                req.add(left_var)
            if right_db == db_name:
                req.add(right_var)
            # Variables referenced in RETURN
            for item in logical_plan.returns:
                expr = item.expression
                if isinstance(expr, PropertyAccess) and var_to_db.get(expr.variable) == db_name:
                    req.add(expr.variable)
                elif isinstance(expr, Variable) and var_to_db.get(expr.name) == db_name:
                    req.add(expr.name)
            return sorted(list(req))

        left_return_vars = get_required_vars(left_db)
        right_return_vars = get_required_vars(right_db)

        # ── Generate per-database sub-queries ──
        def generate_sub_query(db_name, vars_dict, rels_list, return_vars):
            match_parts = []
            visited = set()
            for r in rels_list:
                start_v = r["start"]
                end_v = r["end"]
                match_parts.append(
                    f"({start_v}:{vars_dict[start_v]})-[:{r['type']}]->({end_v}:{vars_dict[end_v]})"
                )
                visited.add(start_v)
                visited.add(end_v)
            for var, label in vars_dict.items():
                if var not in visited:
                    match_parts.append(f"({var}:{label})")
            match_clause = "MATCH " + ", ".join(match_parts)
            return_clause = "RETURN " + ", ".join(return_vars)
            return f"{match_clause} {return_clause}"

        left_query = generate_sub_query(left_db, db_vars[left_db], db_rels[left_db], left_return_vars)
        right_query = generate_sub_query(right_db, db_vars[right_db], db_rels[right_db], right_return_vars)

        left_shard = self.metadata_mgr.shard_manager.get_shard_for_db(left_db) or "shard_1"
        right_shard = self.metadata_mgr.shard_manager.get_shard_for_db(right_db) or "shard_1"

        left_scan = RemoteScan(left_shard, left_query, database=left_db)
        right_scan = RemoteScan(right_shard, right_query, database=right_db)

        # ── Assemble the plan tree ──
        left_key = f"{left_expr.variable}.{left_expr.property_name}"
        right_key = f"{right_expr.variable}.{right_expr.property_name}"
        root = HashJoin(left_scan, right_scan, left_key, right_key)

        # Projection
        if logical_plan.returns:
            root = Projection(root, logical_plan.returns)

        # Limit
        if logical_plan.limit is not None:
            root = Limit(root, logical_plan.limit)

        return root
