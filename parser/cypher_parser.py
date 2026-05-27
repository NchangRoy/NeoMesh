from lark import Lark, Transformer
from .ast import (
    QueryAST, MatchClause, CreateClause, PatternPath, NodePattern, RelationshipPattern,
    WhereClause, BinaryOpCondition, PropertyAccess, Variable, Literal,
    ReturnClause, ReturnItem, CreateDatabaseNode, DeleteClause, LimitClause
)

CYPHER_GRAMMAR = """
?start: query

query: match_clause [where_clause] [create_clause] [delete_clause] [return_clause] [limit_clause] [";"]
     | create_clause [return_clause] [limit_clause] [";"]
     | delete_clause [return_clause] [limit_clause] [";"]
     | create_database_clause [";"]

create_database_clause: "CREATE"i "DATABASE"i CNAME "IN"i CNAME [with_tables] [with_relations]
with_tables: "WITH"i "TABLES"i "(" CNAME ("," CNAME)* ")"
with_relations: "RELATIONS"i "(" CNAME ("," CNAME)* ")"

match_clause: "MATCH"i pattern ("," pattern)*
create_clause: "CREATE"i pattern ("," pattern)*
delete_clause: ["DETACH"i] "DELETE"i CNAME ("," CNAME)*

pattern: node (rel_pattern node)*
node: "(" [CNAME] [":" CNAME] [properties] ")"
properties: "{" property ("," property)* "}"
property: CNAME ":" expr

rel_pattern: "-" "[" [CNAME] [":" CNAME] "]" "->"

where_clause: "WHERE"i comparison ("AND"i comparison)*
comparison: expr OP expr
OP: "=" | "!=" | "<" | ">" | "<=" | ">="

expr: CNAME "." CNAME -> prop_access
    | CNAME           -> var_access
    | NUMBER          -> number_literal
    | ESCAPED_STRING  -> string_literal

return_clause: "RETURN"i return_item ("," return_item)*
return_item: expr ["AS"i CNAME]

limit_clause: "LIMIT"i NUMBER

%import common.CNAME
%import common.INT -> NUMBER
%import common.ESCAPED_STRING
%import common.WS
%ignore WS
"""

class CypherTransformer(Transformer):
    def query(self, args):
        match = None
        create = None
        delete = None
        where = None
        return_clause = None
        limit = None
        
        for arg in args:
            if isinstance(arg, MatchClause):
                match = arg
            elif isinstance(arg, CreateClause):
                create = arg
            elif isinstance(arg, DeleteClause):
                delete = arg
            elif isinstance(arg, WhereClause):
                where = arg
            elif isinstance(arg, ReturnClause):
                return_clause = arg
            elif isinstance(arg, LimitClause):
                limit = arg
            elif isinstance(arg, CreateDatabaseNode):
                return QueryAST(ddl=arg)
                
        return QueryAST(match=match, create=create, delete=delete, where=where, return_clause=return_clause, limit=limit)

    def with_tables(self, args):
        return {"tables": [str(arg) for arg in args]}
        
    def with_relations(self, args):
        return {"relations": [str(arg) for arg in args]}

    def create_database_clause(self, args):
        db_name = str(args[0])
        shard_name = str(args[1])
        tables = []
        relations = []
        
        for arg in args[2:]:
            if isinstance(arg, dict):
                if "tables" in arg:
                    tables = arg["tables"]
                elif "relations" in arg:
                    relations = arg["relations"]
                    
        return CreateDatabaseNode(db_name, shard_name, tables, relations)

    def match_clause(self, args):
        return MatchClause(args)

    def create_clause(self, args):
        paths = [arg for arg in args if isinstance(arg, PatternPath)]
        return CreateClause(paths)

    def delete_clause(self, args):
        detach = False
        variables = []
        for arg in args:
            if hasattr(arg, 'type') and getattr(arg, 'type').upper() == 'DETACH':
                detach = True
            elif hasattr(arg, 'type') and getattr(arg, 'type') == 'CNAME':
                variables.append(str(arg))
        return DeleteClause(variables, detach)

    def pattern(self, args):
        return PatternPath(args)

    def node(self, args):
        var_name = str(args[0]) if args[0] is not None else None
        label = str(args[1]) if args[1] is not None else None
        props = args[2] if len(args) > 2 and args[2] is not None else {}
        return NodePattern(var_name, label, props)

    def properties(self, args):
        props = {}
        for prop in args:
            props[prop[0]] = prop[1]
        return props

    def property(self, args):
        return (str(args[0]), args[1])

    def rel_pattern(self, args):
        var_name = str(args[0]) if args[0] is not None else None
        rel_type = str(args[1]) if args[1] is not None else None
        return RelationshipPattern(rel_type=rel_type, variable=var_name)

    def where_clause(self, args):
        conditions = [arg for arg in args if isinstance(arg, BinaryOpCondition)]
        return WhereClause(conditions)

    def comparison(self, args):
        left, op_token, right = args
        op = str(op_token)
        return BinaryOpCondition(op, left, right)

    def prop_access(self, args):
        var_name, prop_name = args
        return PropertyAccess(str(var_name), str(prop_name))

    def var_access(self, args):
        return Variable(str(args[0]))

    def number_literal(self, args):
        return Literal(int(args[0]))

    def string_literal(self, args):
        val = str(args[0])
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        return Literal(val)

    def return_clause(self, args):
        return ReturnClause(args)

    def return_item(self, args):
        expr = args[0]
        alias = str(args[1]) if len(args) > 1 and args[1] is not None else None
        return ReturnItem(expr, alias)

    def limit_clause(self, args):
        # args[0] is Token('NUMBER', '...')
        return int(args[0])


class CypherParser:
    def __init__(self):
        self.parser = Lark(CYPHER_GRAMMAR, parser='lalr')
        self.transformer = CypherTransformer()

    def parse(self, query_str: str) -> QueryAST:
        tree = self.parser.parse(query_str)
        return self.transformer.transform(tree)
