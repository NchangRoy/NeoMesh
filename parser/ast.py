class ASTNode:
    pass

class NodePattern(ASTNode):
    def __init__(self, variable: str = None, label: str = None, properties: dict = None):
        self.variable = variable
        self.label = label
        self.properties = properties or {}

    def __repr__(self):
        return f"NodePattern(variable={self.variable!r}, label={self.label!r}, properties={self.properties!r})"


class RelationshipPattern(ASTNode):
    def __init__(self, rel_type: str = None, variable: str = None):
        self.rel_type = rel_type
        self.variable = variable

    def __repr__(self):
        return f"RelationshipPattern(variable={self.variable!r}, rel_type={self.rel_type!r})"


class PatternPath(ASTNode):
    def __init__(self, elements: list):
        self.elements = elements  # alternating NodePattern and RelationshipPattern

    @property
    def nodes(self):
        return [el for el in self.elements if isinstance(el, NodePattern)]

    @property
    def relationships(self):
        return [el for el in self.elements if isinstance(el, RelationshipPattern)]

    def __repr__(self):
        return f"PatternPath({self.elements!r})"


class MatchClause(ASTNode):
    def __init__(self, paths: list[PatternPath]):
        self.paths = paths

    def __repr__(self):
        return f"MatchClause({self.paths!r})"


class CreateClause(ASTNode):
    def __init__(self, paths: list[PatternPath]):
        self.paths = paths

    def __repr__(self):
        return f"CreateClause({self.paths!r})"


class DeleteClause(ASTNode):
    def __init__(self, variables: list[str], detach: bool):
        self.variables = variables
        self.detach = detach

    def __repr__(self):
        return f"DeleteClause(variables={self.variables!r}, detach={self.detach!r})"


class Expression(ASTNode):
    pass

class PropertyAccess(Expression):
    def __init__(self, variable: str, property_name: str):
        self.variable = variable
        self.property_name = property_name

    def __repr__(self):
        return f"PropertyAccess({self.variable}.{self.property_name})"


class Variable(Expression):
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Variable({self.name})"


class Literal(Expression):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"Literal({self.value!r})"


class BinaryOpCondition(ASTNode):
    def __init__(self, op: str, left: Expression, right: Expression):
        self.op = op
        self.left = left
        self.right = right

    def __repr__(self):
        return f"BinaryOpCondition({self.left} {self.op} {self.right})"


class WhereClause(ASTNode):
    def __init__(self, conditions: list[BinaryOpCondition]):
        self.conditions = conditions

    def __repr__(self):
        return f"WhereClause({self.conditions!r})"


class ReturnItem(ASTNode):
    def __init__(self, expression: Expression, alias: str = None):
        self.expression = expression
        self.alias = alias

    def __repr__(self):
        alias_str = f" AS {self.alias}" if self.alias else ""
        return f"ReturnItem({self.expression!r}{alias_str})"


class ReturnClause(ASTNode):
    def __init__(self, items: list[ReturnItem]):
        self.items = items

    def __repr__(self):
        return f"ReturnClause({self.items!r})"


class LimitClause(ASTNode):
    def __init__(self, value: int):
        self.value = value

    def __repr__(self):
        return f"LimitClause({self.value})"


class QueryAST(ASTNode):
    def __init__(self, match: MatchClause = None, where: WhereClause = None, return_clause: ReturnClause = None, limit: LimitClause = None, ddl=None, create: CreateClause = None, delete: DeleteClause = None):
        self.match = match
        self.where = where
        self.return_clause = return_clause
        self.limit = limit
        self.ddl = ddl  # Used for DDL commands like CREATE DATABASE
        self.create = create
        self.delete = delete

    def __repr__(self):
        if self.ddl:
            return f"QueryAST(ddl={self.ddl})"
        return (
            f"QueryAST(\n"
            f"  match={self.match},\n"
            f"  create={self.create},\n"
            f"  delete={self.delete},\n"
            f"  where={self.where},\n"
            f"  return={self.return_clause},\n"
            f"  limit={self.limit}\n"
            f")"
        )


class CreateDatabaseNode(ASTNode):
    def __init__(self, db_name: str, shard_name: str, tables: list[str], relations: list[str]):
        self.db_name = db_name
        self.shard_name = shard_name
        self.tables = tables
        self.relations = relations

    def __repr__(self):
        return f"CreateDatabaseNode(db={self.db_name!r}, shard={self.shard_name!r}, tables={self.tables!r}, relations={self.relations!r})"
