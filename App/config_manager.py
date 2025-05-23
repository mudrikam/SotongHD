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
    
    def get_output_format(self):
        """Get the current output format (png or jpg)"""
        return self.config.get("output_format", "png")
    
    def set_output_format(self, format_type):
        """Set the output format"""
        if format_type.lower() not in ["png", "jpg"]:
            raise ValueError("Format must be 'png' or 'jpg'")
        
        self.config["output_format"] = format_type.lower()
        self.save_config()
