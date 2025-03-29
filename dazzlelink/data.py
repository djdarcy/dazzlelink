"""
Data handling for Dazzlelink files.
"""

import os
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union

class DazzleLinkData:
    """
    Abstract Data Type (ADT) for working with dazzlelink data.
    
    This class provides a consistent interface for accessing dazzlelink data,
    handling different format versions and maintaining backward compatibility.
    """
    
    def __init__(self, data=None):
        """
        Initialize with existing data or create a new dazzlelink data structure.
        
        Args:
            data (dict, optional): Existing dazzlelink data. If None, creates a new structure.
        """
        if data is None:
            # Create new structure
            self.data = {
                "schema_version": 1,
                "created_by": "DazzleLink v1",
                "creation_timestamp": datetime.datetime.now().timestamp(),
                "creation_date": datetime.datetime.now().isoformat(),
                
                # New dazzlelink metadata section
                "dazzlelink_metadata": {
                    "last_updated_timestamp": datetime.datetime.now().timestamp(),
                    "last_updated_date": datetime.datetime.now().isoformat(),
                    "update_history": ["initial_creation"]
                },
                
                "link": {
                    "original_path": "",
                    "path_representations": {},
                    "target_path": "",
                    "target_representations": {},
                    "type": "unknown",
                    "relative_path": False,
                    "timestamps": {
                        "created": None,
                        "modified": None,
                        "accessed": None,
                        "created_iso": None,
                        "modified_iso": None,
                        "accessed_iso": None
                    },
                    "attributes": {
                        "hidden": False,
                        "system": False,
                        "readonly": False
                    }
                },
                
                "target": {
                    "exists": False,
                    "type": "unknown",
                    "size": None,
                    "checksum": None,
                    "extension": None,
                    "timestamps": {
                        "created": None,
                        "modified": None,
                        "accessed": None,
                        "created_iso": None,
                        "modified_iso": None,
                        "accessed_iso": None
                    }
                },
                
                "security": {
                    "permissions": None,
                    "owner": None,
                    "group": None
                },
                
                "config": {
                    "default_mode": "info",
                    "platform": "unknown"
                }
            }
        else:
            # Use existing data
            self.data = data
    
    # Schema information
    def get_schema_version(self):
        """Get the schema version of the dazzlelink data."""
        return self.data.get("schema_version", 1)
    
    def get_creator(self):
        """Get the creator string of the dazzlelink data."""
        return self.data.get("created_by", "Unknown")
    
    # Creation timestamps
    def get_creation_timestamp(self):
        """Get the creation timestamp of the dazzlelink."""
        return self.data.get("creation_timestamp")
    
    def get_creation_date(self):
        """Get the creation date of the dazzlelink as ISO format string."""
        return self.data.get("creation_date")
    
    # Dazzlelink metadata
    def get_last_updated_timestamp(self):
        """Get the last updated timestamp of the dazzlelink."""
        # Try new format first, fall back to creation timestamp
        dazzlelink_metadata = self.data.get("dazzlelink_metadata", {})
        return dazzlelink_metadata.get("last_updated_timestamp", self.get_creation_timestamp())
    
    def get_last_updated_date(self):
        """Get the last updated date of the dazzlelink as ISO format string."""
        # Try new format first, fall back to creation date
        dazzlelink_metadata = self.data.get("dazzlelink_metadata", {})
        return dazzlelink_metadata.get("last_updated_date", self.get_creation_date())
    
    def get_update_history(self):
        """Get the update history of the dazzlelink."""
        dazzlelink_metadata = self.data.get("dazzlelink_metadata", {})
        return dazzlelink_metadata.get("update_history", ["initial_creation"])
    
    def update_metadata(self, reason="manual_update"):
        """
        Update the dazzlelink metadata to reflect changes.
        
        Args:
            reason (str): Reason for the update.
        """
        now = datetime.datetime.now()
        timestamp = now.timestamp()
        date_str = now.isoformat()
        
        # Ensure dazzlelink_metadata exists
        if "dazzlelink_metadata" not in self.data:
            self.data["dazzlelink_metadata"] = {
                "last_updated_timestamp": timestamp,
                "last_updated_date": date_str,
                "update_history": ["initial_creation", reason]
            }
        else:
            self.data["dazzlelink_metadata"]["last_updated_timestamp"] = timestamp
            self.data["dazzlelink_metadata"]["last_updated_date"] = date_str
            if "update_history" not in self.data["dazzlelink_metadata"]:
                self.data["dazzlelink_metadata"]["update_history"] = ["initial_creation", reason]
            else:
                self.data["dazzlelink_metadata"]["update_history"].append(reason)
    
    # Link information
    def get_link_type(self):
        """Get the type of the link (symlink, file, etc.)."""
        link = self.data.get("link", {})
        return link.get("type", "unknown")
    
    def get_original_path(self):
        """Get the original path of the link."""
        link = self.data.get("link", {})
        return link.get("original_path", "")
    
    def set_original_path(self, path):
        """Set the original path of the link."""
        if "link" not in self.data:
            self.data["link"] = {}
        self.data["link"]["original_path"] = str(path)
    
    def get_target_path(self):
        """Get the target path of the link."""
        # Handle both old and new formats
        if "target_path" in self.data:
            # Old format
            return self.data["target_path"]
        else:
            # New format
            link = self.data.get("link", {})
            return link.get("target_path", "")
    
    def set_target_path(self, path):
        """Set the target path of the link."""
        if "link" not in self.data:
            self.data["link"] = {}
        self.data["link"]["target_path"] = str(path)
    
    def get_path_representations(self):
        """Get all path representations for the link."""
        link = self.data.get("link", {})
        return link.get("path_representations", {"original_path": self.get_original_path()})
    
    def get_target_representations(self):
        """Get all path representations for the target."""
        link = self.data.get("link", {})
        return link.get("target_representations", {"original_path": self.get_target_path()})
    
    # Link timestamps
    def get_link_timestamps(self):
        """Get all timestamps for the original link."""
        link = self.data.get("link", {})
        return link.get("timestamps", {
            "created": None,
            "modified": None,
            "accessed": None,
            "created_iso": None,
            "modified_iso": None,
            "accessed_iso": None
        })
    
    def set_link_timestamps(self, created=None, modified=None, accessed=None):
        """
        Set timestamps for the original link.
        
        Args:
            created (float, optional): Creation timestamp.
            modified (float, optional): Modification timestamp.
            accessed (float, optional): Access timestamp.
        """
        if "link" not in self.data:
            self.data["link"] = {}
        
        if "timestamps" not in self.data["link"]:
            self.data["link"]["timestamps"] = {}
        
        timestamps = self.data["link"]["timestamps"]
        
        if created is not None:
            timestamps["created"] = created
            timestamps["created_iso"] = datetime.datetime.fromtimestamp(created).isoformat() if created else None
        
        if modified is not None:
            timestamps["modified"] = modified
            timestamps["modified_iso"] = datetime.datetime.fromtimestamp(modified).isoformat() if modified else None
        
        if accessed is not None:
            timestamps["accessed"] = accessed
            timestamps["accessed_iso"] = datetime.datetime.fromtimestamp(accessed).isoformat() if accessed else None
    
    # Target information
    def get_target_exists(self):
        """Check if the target exists."""
        target = self.data.get("target", {})
        return target.get("exists", False)
    
    def get_target_type(self):
        """Get the type of the target (file, directory, etc.)."""
        target = self.data.get("target", {})
        return target.get("type", "unknown")
    
    def get_target_size(self):
        """Get the size of the target file."""
        target = self.data.get("target", {})
        return target.get("size")
    
    # Target timestamps
    def get_target_timestamps(self):
        """Get all timestamps for the target."""
        target = self.data.get("target", {})
        if "timestamps" in target:
            return target["timestamps"]
        else:
            # For backward compatibility, create empty timestamps
            return {
                "created": None,
                "modified": None,
                "accessed": None,
                "created_iso": None,
                "modified_iso": None,
                "accessed_iso": None
            }
    
    def set_target_timestamps(self, created=None, modified=None, accessed=None):
        """
        Set timestamps for the target.
        
        Args:
            created (float, optional): Creation timestamp.
            modified (float, optional): Modification timestamp.
            accessed (float, optional): Access timestamp.
        """
        if "target" not in self.data:
            self.data["target"] = {}
        
        if "timestamps" not in self.data["target"]:
            self.data["target"]["timestamps"] = {}
        
        timestamps = self.data["target"]["timestamps"]
        
        if created is not None:
            timestamps["created"] = created
            timestamps["created_iso"] = datetime.datetime.fromtimestamp(created).isoformat() if created else None
        
        if modified is not None:
            timestamps["modified"] = modified
            timestamps["modified_iso"] = datetime.datetime.fromtimestamp(modified).isoformat() if modified else None
        
        if accessed is not None:
            timestamps["accessed"] = accessed
            timestamps["accessed_iso"] = datetime.datetime.fromtimestamp(accessed).isoformat() if accessed else None
    
    # Configuration
    def get_default_mode(self):
        """Get the default execution mode."""
        config = self.data.get("config", {})
        return config.get("default_mode", "info")
    
    def set_default_mode(self, mode):
        """Set the default execution mode."""
        if "config" not in self.data:
            self.data["config"] = {}
        self.data["config"]["default_mode"] = mode
    
    def get_platform(self):
        """Get the platform the dazzlelink was created on."""
        config = self.data.get("config", {})
        return config.get("platform", "unknown")
    
    def set_platform(self, platform):
        """Set the platform the dazzlelink was created on."""
        if "config" not in self.data:
            self.data["config"] = {}
        self.data["config"]["platform"] = platform
    
    # I/O operations
    def to_dict(self):
        """
        Convert to a dictionary suitable for serialization.
        
        Returns:
            dict: The dazzlelink data as a dictionary.
        """
        return self.data
    
    @classmethod
    def from_file(cls, file_path):
        """
        Load dazzlelink data from a file.
        
        Args:
            file_path (str): Path to the dazzlelink file.
            
        Returns:
            DazzleLinkData: A new instance with the loaded data.
            
        Raises:
            ValueError: If the file is not a valid dazzlelink file.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    return cls(data)
                except json.JSONDecodeError:
                    # Try to handle script-embedded format
                    content = f.read()
                    json_start = content.find('# DAZZLELINK_DATA_BEGIN')
                    if json_start != -1:
                        json_text = content[json_start + len('# DAZZLELINK_DATA_BEGIN'):].strip()
                        data = json.loads(json_text)
                        return cls(data)
                    raise ValueError(f"Invalid dazzlelink file: {file_path}")
        except Exception as e:
            raise ValueError(f"Error reading dazzlelink file {file_path}: {str(e)}")
    
    def save_to_file(self, file_path, make_executable=False):
        """
        Save dazzlelink data to a file.
        
        Args:
            file_path (str): Path to save the dazzlelink file.
            make_executable (bool): Whether to make the file executable.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
                
            if make_executable:
                # TODO: Implement executable script generation
                pass
                
            return True
        except Exception as e:
            print(f"Error saving dazzlelink file {file_path}: {str(e)}")
            return False