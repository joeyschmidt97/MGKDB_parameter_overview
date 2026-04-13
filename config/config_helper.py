"""
TPED Configuration Module

Provides centralized configuration management for TPED projects.
"""

import os
import yaml
import warnings
from typing import Optional, Dict, Any

# from TPED.projects.utils.git_helpers import get_git_root

# Use case
# config_path = Config().get_path('GENE_PATH')


class Config:
    """Configuration manager for TPED paths and settings."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize config manager.
        
        Args:
            config_path: Optional path to config file. If not provided,
                        will search in standard locations.
        """
        self._config_path = config_path or self._find_config_file()
        self._config_data = self._load_config()
    

    def _find_config_file(self) -> Optional[str]:
        """Find config file in standard locations.

        """

        # Directory where this Config module lives
        module_dir = os.path.dirname(os.path.realpath(__file__))
        config_path = os.path.join(module_dir, "user_config.yaml")

        print("Looking for config:", config_path)

        if os.path.isfile(config_path):
            return config_path

        return None
    
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or template."""

        #TODO: Add file check and throw error if path not found

        if self._config_path and os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r') as f:
                    config_data = yaml.safe_load(f) or {}

                    self._check_paths(config_data)
                    return config_data
            except Exception as e:
                warnings.warn(f"\nFailed to load config from:\n {self._config_path}: \n{e}")
                
        return {}
        


    def get_path(self, key: str) -> Optional[str]:
        """Get a path value from config.
        
        Args:
            key: Dot-separated key (e.g., 'external_tools.GENE_path')
            
        Returns:
            Path string or None if not found
        """
        config_dict = self._config_data
        
        try:
            path = config_dict.get(key, None)
            if path is None:
                raise ValueError(f'Incorrect config path key used "{key}", please select from the following keys: \n{list(config_dict.keys())}')
            return path
        
        except (KeyError, TypeError):
            raise ValueError('Problem reading config file.')
    

    def _check_paths(self, config_dict: Dict) -> None:
        """Validate all paths in config.

        Args:
            config_dict: Configuration dictionary to validate

        Raises:
            ValueError: If any required path (not a template placeholder) doesn't exist
        """
        def _is_path_like(value: str) -> bool:
            """Check if string looks like a file path."""
            return value.startswith(('/', './', '../'))

        def _is_template_placeholder(value: str) -> bool:
            """Check if path is a template placeholder."""
            return value.startswith('/path')

        for key, value in config_dict.items():
            # Skip empty strings, None, or non-string values
            if not value or not isinstance(value, str):
                continue

            if _is_path_like(value):
                if not _is_template_placeholder(value) and not os.path.exists(value):
                    raise ValueError(f"Path not found: {key} -> '{value}'")
        
