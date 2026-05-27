from distributed_neo4j.parser.ast import QueryAST, PropertyAccess, Variable, ReturnItem
from distributed_neo4j.metadata.shard_manager import MetadataManager

class SemanticError(Exception):
    pass


class LogicalPlan:
    def __init__(self, variables: dict[str, str], relationships: list[dict], filters: list, returns: list, limit: int = None, create_paths: list = None):
        self.variables = variables  # var_name -> label (e.g., 'u' -> 'User')
        self.relationships = relationships  # list of { 'start': var, 'type': rel_type, 'end': var }
        self.filters = filters  # list of BinaryOpCondition
        self.returns = returns  # list of ReturnItem
        self.limit = limit
        self.create_paths = create_paths or []  # list of PatternPath to create

    def __repr__(self):
        return (
            f"LogicalPlan(\n"
            f"  variables={self.variables},\n"
            f"  relationships={self.relationships},\n"
            f"  filters={self.filters},\n"
            f"  returns={self.returns},\n"
            f"  limit={self.limit},\n"
            f"  create_paths={self.create_paths}\n"
            f")"
        )


class LogicalCreateDatabase:
    def __init__(self, ddl_node):
        self.db_name = ddl_node.db_name
        self.shard_name = ddl_node.shard_name
        self.tables = ddl_node.tables
        self.relations = ddl_node.relations

    def __repr__(self):
        return f"LogicalCreateDatabase(db={self.db_name!r}, shard={self.shard_name!r}, tables={self.tables!r}, relations={self.relations!r})"


class LogicalPlanner:
    def __init__(self, metadata_mgr: MetadataManager):
        self.metadata_mgr = metadata_mgr

    def plan(self, ast: QueryAST):
        if ast.ddl:
            return LogicalCreateDatabase(ast.ddl)
            
        variables = {}
        relationships = []

        # 1. Parse MATCH patterns and extract variables & labels
        if ast.match:
            for path in ast.match.paths:
                # Alternating nodes and relationships: Node, Rel, Node, Rel, Node...
                elements = path.elements
                
                # Extract nodes
                for node in path.nodes:
                    if node.variable:
                        if node.variable in variables and node.label and variables[node.variable] != node.label:
                            raise SemanticError(
                                f"Variable '{node.variable}' re-declared with different label "
                                f"'{node.label}' (originally '{variables[node.variable]}')"
                            )
                        if node.label:
                            variables[node.variable] = node.label
                        elif node.variable not in variables:
                            variables[node.variable] = None
                    else:
                        # Anonymous node with label, we should assign an internal name
                        pass

                # Extract relationships
                for i in range(1, len(elements), 2):
                    left_node = elements[i - 1]
                    rel = elements[i]
                    right_node = elements[i + 1]
                    
                    # Check that both left and right have variables
                    if not left_node.variable or not right_node.variable:
                        raise SemanticError("Anonymous nodes in relationships are not supported in MVP")
                    
                    if rel.variable:
                        if rel.variable in variables and rel.rel_type and variables[rel.variable] != rel.rel_type:
                            raise SemanticError(
                                f"Variable '{rel.variable}' re-declared with different type "
                                f"'{rel.rel_type}' (originally '{variables[rel.variable]}')"
                            )
                        if rel.rel_type:
                            variables[rel.variable] = rel.rel_type
                        elif rel.variable not in variables:
                            raise SemanticError(f"Relationship variable '{rel.variable}' has no declared type")
                    
                    relationships.append({
                        "variable": rel.variable,
                        "start": left_node.variable,
                        "type": rel.rel_type,
                        "end": right_node.variable
                    })

        create_paths = []
        new_tables = set()
        new_relations = set()
        if ast.create:
            create_paths = ast.create.paths
            # We don't strictly require CREATE nodes to have variables or match existing ones,
            # but if they have variables, we might register their labels.
            for path in create_paths:
                for node in path.nodes:
                    if node.variable and node.label:
                        variables[node.variable] = node.label
                    if node.label:
                        new_tables.add(node.label)
                for rel in path.relationships:
                    if rel.variable and rel.rel_type:
                        variables[rel.variable] = rel.rel_type
                    if rel.rel_type:
                        new_relations.add(rel.rel_type)

        if new_tables or new_relations:
            current_db = self.metadata_mgr.current_db
            actual_new_tables = [t for t in new_tables if not current_db or current_db not in self.metadata_mgr.schema_manager.get_dbs_for_label(t)]
            actual_new_relations = [r for r in new_relations if not current_db or current_db not in self.metadata_mgr.schema_manager.get_dbs_for_relationship(r)]
            
            if actual_new_tables or actual_new_relations:
                if not current_db:
                    raise SemanticError("Cannot CREATE new labels or relationships without selecting a database (USE <db_name>)")
                
                self.metadata_mgr.schema_manager.add_database_schema(
                    self.metadata_mgr.current_db,
                    actual_new_tables,
                    actual_new_relations
                )

        # Validate that all labels and relationship types exist in the catalog
        for var_name, label in variables.items():
            if label is None:
                continue
            dbs = self.metadata_mgr.get_table_dbs(label)
            if not dbs:
                # Could be a relationship variable (e.g., r -> FOLLOWS), check relations too
                dbs = self.metadata_mgr.get_relationship_dbs(label)
                if not dbs:
                    raise SemanticError(f"'{label}' is not defined in tables.config or relations.config metadata")

        for rel in relationships:
            dbs = self.metadata_mgr.get_relationship_dbs(rel["type"])
            if not dbs:
                raise SemanticError(f"Relationship type '{rel['type']}' is not defined in relations.config metadata")

        # 2. Parse WHERE conditions
        filters = []
        if ast.where:
            # Helper to check if property variable is defined
            def validate_expr(expr):
                if isinstance(expr, PropertyAccess):
                    if expr.variable not in variables:
                        raise SemanticError(f"Variable '{expr.variable}' in WHERE clause is not defined in MATCH")
                elif isinstance(expr, Variable):
                    if expr.name not in variables:
                        raise SemanticError(f"Variable '{expr.name}' in WHERE clause is not defined in MATCH")

            for cond in ast.where.conditions:
                validate_expr(cond.left)
                validate_expr(cond.right)
                filters.append(cond)

        # 3. Parse RETURN items
        returns = []
        if ast.return_clause:
            for item in ast.return_clause.items:
                expr = item.expression
                if isinstance(expr, PropertyAccess):
                    if expr.variable not in variables:
                        raise SemanticError(f"Variable '{expr.variable}' in RETURN clause is not defined in MATCH")
                elif isinstance(expr, Variable):
                    if expr.name not in variables:
                        raise SemanticError(f"Variable '{expr.name}' in RETURN clause is not defined in MATCH/CREATE")
                returns.append(item)

        # 5. Build Final Plan
        if not ast.return_clause and not ast.create and not ast.delete:
            raise SemanticError("Query must have a RETURN clause, CREATE clause, or DELETE clause")

        # 4. Limit
        limit = ast.limit.value if ast.limit else None

        return LogicalPlan(variables, relationships, filters, returns, limit, create_paths=create_paths)
