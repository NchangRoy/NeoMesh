import sys
import os
sys.path.insert(0, os.path.abspath('../..'))
from distributed_neo4j.parser.cypher_parser import CypherParser
from distributed_neo4j.planner.logical_planner import LogicalPlanner
from distributed_neo4j.metadata.shard_manager import MetadataManager
parser = CypherParser()
mgr = MetadataManager()
planner = LogicalPlanner(mgr)
ast = parser.parse('MATCH (a:User), (b:User) WHERE a.name = "Alice" AND b.name = "Bob" CREATE (a)-[:FOLLOWS]->(b)')
print(ast)
try:
    plan = planner.plan(ast)
    print("Plan filters:", plan.filters)
except Exception as e:
    print("Error:", e)
