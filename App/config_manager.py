import os
import json
from pathlib import Path

class ConfigManager:
    """Manages application configuration settings"""
    
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config_file = os.path.join(base_dir, "config.json")
        self.config = self.load_config()
        
    def load_config(self):
        """Load configuration from file"""
        default_config = {
            "output_format": "png",  # Default format: png, alternative: jpg
            # Persist UI preferences
            "batch_size": 1,
            "headless": True,
            "incognito": True,
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                print(f"Error loading config: {e}")
                return default_config
        else:
            # Create default config file
            self.save_config(default_config)
            return default_config
    
    def save_config(self, config=None):
        """Save configuration to file"""
        if config is None:
            config = self.config
            
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    # New helpers for batch/headless/incognito
    def get_batch_size(self) -> int:
        try:
            return int(self.config.get("batch_size", 1))
        except Exception:
            return 1

    def set_batch_size(self, size: int):
        try:
            self.config["batch_size"] = int(size)
            self.save_config()
        except Exception:
            pass

    def get_headless(self):
        val = self.config.get("headless", True)
        # Return explicit boolean or None if not set
        if val is None:
            return None
        return bool(val)

    def set_headless(self, value):
        if value is None:
            self.config["headless"] = None
        else:
            self.config["headless"] = bool(value)
        self.save_config()

    def get_incognito(self):
        val = self.config.get("incognito", True)
        if val is None:
            return None
        return bool(val)

    def set_incognito(self, value):
        if value is None:
            self.config["incognito"] = None
        else:
            self.config["incognito"] = bool(value)
        self.save_config()
    
    def get_output_format(self):
        """Get the current output format (png or jpg)"""
        return self.config.get("output_format", "png")
    
    def set_output_format(self, format_type):
        """Set the output format"""
        if format_type.lower() not in ["png", "jpg"]:
            raise ValueError("Format must be 'png' or 'jpg'")
        
        self.config["output_format"] = format_type.lower()
        self.save_config()
