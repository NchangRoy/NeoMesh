import configparser
import os

class ConfigLoader:
    def __init__(self, config_dir=None):
        if config_dir is None:
            # Default to the sibling configs directory of metadata
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_dir = os.path.join(base_dir, "configs")
        self.config_dir = config_dir

    def load_config(self, filename):
        path = os.path.join(self.config_dir, filename)
        parser = configparser.ConfigParser()
        if os.path.exists(path):
            parser.read(path)
        return parser

    def save_config(self, filename, parser: configparser.ConfigParser):
        path = os.path.join(self.config_dir, filename)
        with open(path, 'w') as f:
            parser.write(f)
