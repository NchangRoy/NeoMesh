import sys, os, asyncio
sys.path.insert(0, os.path.abspath('..'))

from distributed_neo4j.parser.cypher_parser import CypherParser
from distributed_neo4j.planner.logical_planner import LogicalPlanner
from distributed_neo4j.planner.physical_planner import PhysicalPlanner
from distributed_neo4j.metadata.shard_manager import MetadataManager

# Setup
mgr = MetadataManager()
mgr.set_current_db("NeoMesh")
parser = CypherParser()
planner = LogicalPlanner(mgr)
physical_planner = PhysicalPlanner(mgr)

print("=" * 60)
print("  TEST 1: HORIZONTAL (User exists in myNewDatabase + fureh)")
print("=" * 60)
q1 = 'MATCH (u:User) RETURN u'
ast1 = parser.parse(q1)
lp1 = planner.plan(ast1)
pp1 = physical_planner.plan(lp1, q1)
print(f"Query: {q1}")
print(f"Variables: {lp1.variables}")
pp1.print_tree()

print()
print("=" * 60)
print("  TEST 2: VERTICAL (Animal in myNewDatabase, Post in social_db)")
print("=" * 60)
q2 = 'MATCH (a:Animal), (p:Post) WHERE a.name = p.author RETURN a, p'
ast2 = parser.parse(q2)
lp2 = planner.plan(ast2)
pp2 = physical_planner.plan(lp2, q2)
print(f"Query: {q2}")
print(f"Variables: {lp2.variables}")
pp2.print_tree()

print()
print("=" * 60)
print("  TEST 3: SINGLE DB (Order + Product both in commerce_db)")
print("=" * 60)
q3 = 'MATCH (o:Order), (p:Product) WHERE o.pid = p.id RETURN o, p'
ast3 = parser.parse(q3)
lp3 = planner.plan(ast3)
pp3 = physical_planner.plan(lp3, q3)
print(f"Query: {q3}")
print(f"Variables: {lp3.variables}")
pp3.print_tree()
