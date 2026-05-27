from .config_loader import ConfigLoader
from .schema_manager import SchemaManager

class ShardManager:
    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.db_to_shard = {}
        self.shard_configs = {}
        self.load_shards()

    def load_shards(self):
        # Load db mappings
        try:
            db_parser = self.config_loader.load_config("db.config")
            for db_name in db_parser.sections():
                if "shard" in db_parser[db_name]:
                    self.db_to_shard[db_name] = db_parser[db_name]["shard"]
        except FileNotFoundError:
            pass

        # Load shard connections
        try:
            shard_parser = self.config_loader.load_config("shard.config")
            for shard_name in shard_parser.sections():
                section = shard_parser[shard_name]
                self.shard_configs[shard_name] = {
                    "host": section.get("host", "127.0.0.1"),
                    "bolt": section.getint("bolt", 7687),
                    "user": section.get("user", "neo4j"),
                    "password": section.get("password", "password"),
                }
        except FileNotFoundError:
            pass

    def get_shard_for_db(self, db_name: str) -> str:
        return self.db_to_shard.get(db_name)

    def get_shard_config(self, shard_name: str) -> dict:
        return self.shard_configs.get(shard_name)

    def assign_database(self, db_name: str, shard_name: str):
        db_parser = self.config_loader.load_config("db.config")
        if db_name not in db_parser:
            db_parser.add_section(db_name)
        
        self.db_to_shard[db_name] = shard_name
        db_parser[db_name]["shard"] = shard_name
        self.config_loader.save_config("db.config", db_parser)


class MetadataManager:
    def __init__(self, config_dir=None):
        self.config_loader = ConfigLoader(config_dir)
        self.schema_manager = SchemaManager(self.config_loader)
        self.shard_manager = ShardManager(self.config_loader)
        self.current_db = None

        # Mirror variables for compatibility with prompt examples
        self.table_to_db = self.schema_manager.label_to_db
        self.db_to_shard = self.shard_manager.db_to_shard
        self.relationship_to_db = self.schema_manager.relationship_to_db

    def set_current_db(self, db_name: str):
        self.current_db = db_name

    def get_table_dbs(self, table):
        if self.current_db and self.current_db != "NeoMesh":
            return [self.current_db]
        dbs = self.schema_manager.get_dbs_for_label(table)
        if self.current_db == "NeoMesh":
            return dbs
        return dbs

    def get_shards_for_table(self, table):
        dbs = self.get_table_dbs(table)
        return [self.shard_manager.get_shard_for_db(db) for db in dbs if self.shard_manager.get_shard_for_db(db)]

    def get_relationship_dbs(self, rel_type):
        if self.current_db and self.current_db != "NeoMesh":
            return [self.current_db]
        dbs = self.schema_manager.get_dbs_for_relationship(rel_type)
        if self.current_db == "NeoMesh":
            return dbs
        return dbs

    def get_shards_for_relationship(self, rel_type):
        dbs = self.get_relationship_dbs(rel_type)
        return [self.shard_manager.get_shard_for_db(db) for db in dbs if self.shard_manager.get_shard_for_db(db)]

    def get_shard_config(self, shard_name):
        return self.shard_manager.get_shard_config(shard_name)

    def create_database(self, db_name: str, shard_name: str, tables: list[str] = None, relations: list[str] = None):
        tables = tables or []
        relations = relations or []
        self.shard_manager.assign_database(db_name, shard_name)
        self.schema_manager.add_database_schema(db_name, tables, relations)
