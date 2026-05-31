import asyncio
import logging
from distributed_neo4j.metadata.shard_manager import MetadataManager
from distributed_neo4j.planner.operators import PlanNode, RemoteScan, HashJoin, Projection, Limit, Union
from .shard_client import ShardClient
from .join_engine import hash_join, resolve_key_path
from distributed_neo4j.parser.ast import PropertyAccess, Variable

logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, metadata_mgr: MetadataManager, mock: bool = False):
        self.metadata_mgr = metadata_mgr
        self.mock = mock
        self.clients = {}

    def get_client(self, shard_name: str) -> ShardClient:
        if shard_name not in self.clients:
            config = self.metadata_mgr.get_shard_config(shard_name)
            if not config and not self.mock:
                raise ValueError(f"No configuration found for shard: {shard_name}")
            
            host = config.get("host", "127.0.0.1") if config else "127.0.0.1"
            bolt = config.get("bolt", 7687) if config else 7687
            user = config.get("user", "neo4j") if config else "neo4j"
            password = config.get("password", "password") if config else "password"
            
            uri = f"bolt://{host}:{bolt}"
            self.clients[shard_name] = ShardClient(uri, user, password, mock=self.mock)
        return self.clients[shard_name]

    async def execute(self, node: PlanNode) -> list[dict]:
        if isinstance(node, RemoteScan):
            try:
                client = self.get_client(node.shard)
                logger.info(f"Routing query to {node.shard}: {node.query}")
                # Run blocking driver call in an asyncio thread pool
                return await asyncio.to_thread(client.execute, node.query, node.database)
            except Exception as e:
                logger.warning(f"Failed to execute on shard '{node.shard}': {e}. Returning empty results for this shard.")
                return []


        elif isinstance(node, HashJoin):
            # Run both branches concurrently
            left_task = self.execute(node.left)
            right_task = self.execute(node.right)
            
            left_results, right_results = await asyncio.gather(left_task, right_task)
            
            logger.info(f"Merging results from left and right branches using HashJoin")
            return hash_join(left_results, right_results, node.left_key, node.right_key)

        elif isinstance(node, Union):
            logger.info(f"Executing Union across {len(node.children)} shards concurrently")
            tasks = [self.execute(child) for child in node.children]
            results_list = await asyncio.gather(*tasks)
            
            # Concatenate all results
            final_results = []
            for res in results_list:
                final_results.extend(res)
            return final_results

        elif isinstance(node, Projection):
            child_results = await self.execute(node.child)
            logger.info(f"Applying Projection of items: {node.items}")
            projected = []
            for row in child_results:
                new_row = {}
                for item in node.items:
                    expr = item.expression
                    alias = item.alias
                    
                    # Target field name
                    if alias:
                        field_name = alias
                    elif isinstance(expr, PropertyAccess):
                        field_name = f"{expr.variable}.{expr.property_name}"
                    elif isinstance(expr, Variable):
                        field_name = expr.name
                    else:
                        field_name = "result"

                    # Resolve value
                    if isinstance(expr, PropertyAccess):
                        val = resolve_key_path(row, f"{expr.variable}.{expr.property_name}")
                    elif isinstance(expr, Variable):
                        val = row.get(expr.name)
                    else:
                        val = None
                        
                    new_row[field_name] = val
                projected.append(new_row)
            return projected

        elif isinstance(node, Limit):
            child_results = await self.execute(node.child)
            logger.info(f"Applying Limit of {node.limit} records")
            return child_results[:node.limit]

        else:
            raise TypeError(f"Unknown PlanNode type: {type(node)}")

    def close(self):
        for client in self.clients.values():
            client.close()
        self.clients.clear()
