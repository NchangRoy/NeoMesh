from distributed_neo4j.metadata.shard_manager import MetadataManager
from distributed_neo4j.parser.ast import PropertyAccess, Variable
from .logical_planner import LogicalPlan, LogicalCreateDatabase
from .operators import PlanNode, RemoteScan, HashJoin, Projection, Limit, Union

class PhysicalPlanner:
    def __init__(self, metadata_mgr: MetadataManager):
        self.metadata_mgr = metadata_mgr

    def plan(self, logical_plan, original_query: str) -> PlanNode:
        if isinstance(logical_plan, LogicalCreateDatabase):
            # For Neo4j cluster/fabric:
            query = f"CREATE DATABASE {logical_plan.db_name}"
            return RemoteScan(logical_plan.shard_name, query)

        # Horizontal Fragmentation Check (NeoMesh Virtual DB)
        if self.metadata_mgr.current_db == "NeoMesh":
            common_dbs = None
            for var, label in logical_plan.variables.items():
                if label is None:
                    continue
                dbs = set(self.metadata_mgr.get_table_dbs(label))
                if not dbs:
                    # Could be a relationship variable (e.g., r -> FOLLOWS)
                    dbs = set(self.metadata_mgr.get_relationship_dbs(label))
                if common_dbs is None:
                    common_dbs = dbs
                else:
                    common_dbs = common_dbs.intersection(dbs)
                    
            for rel in logical_plan.relationships:
                dbs = set(self.metadata_mgr.get_relationship_dbs(rel["type"]))
                if common_dbs is None:
                    common_dbs = dbs
                else:
                    common_dbs = common_dbs.intersection(dbs)
                    
            if common_dbs is None:
                common_dbs = set(self.metadata_mgr.db_to_shard.keys())
                
            if common_dbs and len(common_dbs) > 1:
                # Horizontal fragmentation across multiple DBs
                scans = []
                for db in sorted(list(common_dbs)):
                    shard = self.metadata_mgr.shard_manager.get_shard_for_db(db)
                    if shard:
                        scans.append(RemoteScan(shard, original_query, database=db))
                if scans:
                    return Union(scans)

        # 1. Identify which shards are involved (Vertical Joins / Single Shard)
        shards_involved = set()
        var_shards = {}  # var_name -> shard_name
        
        for var, label in logical_plan.variables.items():
            if label is None:
                continue
            shards = self.metadata_mgr.get_shards_for_table(label)
            shard = shards[0] if shards else None
            var_shards[var] = shard
            if shard:
                shards_involved.add(shard)

        for rel in logical_plan.relationships:
            shards = self.metadata_mgr.get_shards_for_relationship(rel["type"])
            shard = shards[0] if shards else None
            if shard:
                shards_involved.add(shard)

        # 2. Check if single-shard optimization applies
        if len(shards_involved) <= 1:
            shard = list(shards_involved)[0] if shards_involved else "shard_1"
            # Route the original query directly
            # If current_db is NeoMesh, we still need to know which actual DB it targets if it's single-shard.
            # We can find the db from one of the variables.
            target_db = self.metadata_mgr.current_db
            if target_db == "NeoMesh" and logical_plan.variables:
                first_var_label = list(logical_plan.variables.values())[0]
                dbs = self.metadata_mgr.get_table_dbs(first_var_label)
                if dbs:
                    target_db = dbs[0]
            
            return RemoteScan(shard, original_query, database=target_db)

        # 3. Cross-shard query execution planning
        # Currently, MVP supports joining exactly 2 shards.
        if len(shards_involved) > 2:
            raise NotImplementedError("Multi-way cross-shard joins (>2 shards) not supported in MVP")

        # Split variables and relationships by shard
        shard_vars = {s: {} for s in shards_involved}
        for var, label in logical_plan.variables.items():
            shard = var_shards[var]
            shard_vars[shard][var] = label

        shard_rels = {s: [] for s in shards_involved}
        for rel in logical_plan.relationships:
            # For simplicity, assign relationship to the shard of its start node
            shard = var_shards[rel["start"]]
            shard_rels[shard].append(rel)

        # Find the join condition
        if not logical_plan.filters:
            raise NotImplementedError("Cross-shard cartesian products without join filters not supported in MVP")

        join_cond = logical_plan.filters[0]
        # Identify left and right join keys and match them to shards
        left_expr = join_cond.left
        right_expr = join_cond.right

        if not isinstance(left_expr, PropertyAccess) or not isinstance(right_expr, PropertyAccess):
            raise NotImplementedError("Cross-shard join must be on property access equality (e.g. u.id = o.userId)")

        left_var = left_expr.variable
        right_var = right_expr.variable
        left_shard = var_shards[left_var]
        right_shard = var_shards[right_var]

        if left_shard == right_shard:
            raise ValueError("Join keys map to the same shard; logical planner should have handled this as single-shard.")

        # Determine which variables each shard needs to return.
        # Each shard needs to return any of its variables that are used in:
        # a) the global return clause
        # b) the join key
        def get_required_vars(shard_name):
            req = set()
            # Check join keys
            if left_shard == shard_name:
                req.add(left_var)
            if right_shard == shard_name:
                req.add(right_var)
            # Check returns
            for item in logical_plan.returns:
                expr = item.expression
                if isinstance(expr, PropertyAccess) and var_shards[expr.variable] == shard_name:
                    req.add(expr.variable)
                elif isinstance(expr, Variable) and var_shards[expr.name] == shard_name:
                    req.add(expr.name)
            return sorted(list(req))

        left_return_vars = get_required_vars(left_shard)
        right_return_vars = get_required_vars(right_shard)

        # Helper to generate local queries
        def generate_query(shard_name, vars_dict, rels_list, return_vars):
            match_parts = []
            visited = set()
            for r in rels_list:
                start_var = r["start"]
                end_var = r["end"]
                match_parts.append(
                    f"({start_var}:{vars_dict[start_var]})-[:{r['type']}]->({end_var}:{vars_dict[end_var]})"
                )
                visited.add(start_var)
                visited.add(end_var)

            for var, label in vars_dict.items():
                if var not in visited:
                    match_parts.append(f"({var}:{label})")

            match_clause = "MATCH " + ", ".join(match_parts)
            return_clause = "RETURN " + ", ".join(return_vars)
            return f"{match_clause} {return_clause}"

        left_query = generate_query(left_shard, shard_vars[left_shard], shard_rels[left_shard], left_return_vars)
        right_query = generate_query(right_shard, shard_vars[right_shard], shard_rels[right_shard], right_return_vars)

        left_scan = RemoteScan(left_shard, left_query, database=self.metadata_mgr.current_db)
        right_scan = RemoteScan(right_shard, right_query, database=self.metadata_mgr.current_db)

        # Create HashJoin operator
        left_key_str = f"{left_expr.variable}.{left_expr.property_name}"
        right_key_str = f"{right_expr.variable}.{right_expr.property_name}"
        
        root = HashJoin(left_scan, right_scan, left_key_str, right_key_str)

        # Wrap in Projection if needed
        root = Projection(root, logical_plan.returns)


        # Wrap in Limit if needed
        if logical_plan.limit is not None:
            root = Limit(root, logical_plan.limit)

        return root
