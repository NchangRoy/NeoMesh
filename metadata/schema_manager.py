from .config_loader import ConfigLoader

class SchemaManager:
    def __init__(self, config_loader: ConfigLoader):
        self.config_loader = config_loader
        self.label_to_db = {}
        self.relationship_to_db = {}
        self.load_schema()

    def load_schema(self):
        try:
            tables_parser = self.config_loader.load_config("tables.config")
            if "tables" in tables_parser:
                for label, db_str in tables_parser["tables"].items():
                    dbs = [db.strip() for db in db_str.split(",") if db.strip()]
                    self.label_to_db[label] = dbs
        except FileNotFoundError:
            pass

        try:
            relations_parser = self.config_loader.load_config("relations.config")
            if "relations" in relations_parser:
                for rel, db_str in relations_parser["relations"].items():
                    dbs = [db.strip() for db in db_str.split(",") if db.strip()]
                    self.relationship_to_db[rel] = dbs
        except FileNotFoundError:
            pass

    def get_dbs_for_label(self, label: str) -> list[str]:
        if label in self.label_to_db:
            return self.label_to_db[label]
        for l, dbs in self.label_to_db.items():
            if l.lower() == label.lower():
                return dbs
        return []

    def get_dbs_for_relationship(self, rel_type: str) -> list[str]:
        if rel_type in self.relationship_to_db:
            return self.relationship_to_db[rel_type]
        for r, dbs in self.relationship_to_db.items():
            if r.lower() == rel_type.lower():
                return dbs
        return []

    def add_database_schema(self, db_name: str, tables: list[str], relations: list[str]):
        tables_parser = self.config_loader.load_config("tables.config")
        if "tables" not in tables_parser:
            tables_parser.add_section("tables")
            
        for table in tables:
            actual_key = table
            # Find matching case-insensitive key if it exists
            for k in self.label_to_db.keys():
                if k.lower() == table.lower():
                    actual_key = k
                    break
                    
            dbs = self.label_to_db.get(actual_key, [])
            if db_name not in dbs:
                dbs.append(db_name)
            self.label_to_db[actual_key] = dbs
            tables_parser["tables"][actual_key] = ", ".join(dbs)
            
        self.config_loader.save_config("tables.config", tables_parser)
        
        relations_parser = self.config_loader.load_config("relations.config")
        if "relations" not in relations_parser:
            relations_parser.add_section("relations")
            
        for rel in relations:
            actual_key = rel
            # Find matching case-insensitive key if it exists
            for k in self.relationship_to_db.keys():
                if k.lower() == rel.lower():
                    actual_key = k
                    break
                    
            dbs = self.relationship_to_db.get(actual_key, [])
            if db_name not in dbs:
                dbs.append(db_name)
            self.relationship_to_db[actual_key] = dbs
            relations_parser["relations"][actual_key] = ", ".join(dbs)
            
        self.config_loader.save_config("relations.config", relations_parser)
