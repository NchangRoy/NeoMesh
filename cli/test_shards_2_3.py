import sys, os
sys.path.insert(0, os.path.abspath('.'))

from distributed_neo4j.parser.cypher_parser import CypherParser
from distributed_neo4j.planner.logical_planner import LogicalPlanner
from distributed_neo4j.planner.physical_planner import PhysicalPlanner
from distributed_neo4j.metadata.shard_manager import MetadataManager

# Initialize standard components
mgr = MetadataManager()
parser = CypherParser()

# Manually configure the multi-shard topology
mgr.shard_manager.shard_configs["shard_2"] = {"host": "127.0.0.1", "bolt": 7688}
mgr.shard_manager.shard_configs["shard_3"] = {"host": "127.0.0.1", "bolt": 7689}

mgr.shard_manager.db_to_shard["db_alpha"] = "shard_2"
mgr.shard_manager.db_to_shard["db_beta"] = "shard_3"

mgr.schema_manager.label_to_db["driver"] = ["db_alpha"]
mgr.schema_manager.label_to_db["car"] = ["db_beta"]

# Switch context to NeoMesh
mgr.set_current_db("NeoMesh")

planner = LogicalPlanner(mgr)
physical_planner = PhysicalPlanner(mgr)

print("======================================================================")
print("  TEST: VERTICAL CROSS-SHARD (Driver on shard_2, Car on shard_3)")
print("======================================================================")
query = 'MATCH (d:Driver), (c:Car) WHERE d.id = c.ownerId RETURN d, c'
ast = parser.parse(query)
lp = planner.plan(ast)
pp = physical_planner.plan(lp, query)

print(f"Query: {query}")
print(f"Variables: {lp.variables}")
print(pp.print_tree())
